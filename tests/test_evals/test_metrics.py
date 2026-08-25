"""Tests for the calibration and variance numbers."""

from __future__ import annotations

import pytest

from nexis.evals.dataset import LabelledIdea, ScoreBand
from nexis.evals.metrics import calibration, gate, variance
from nexis.evals.runner import ReviewRecord
from nexis.state import BusinessIdea, ReviewerRole


def make_idea(idea_id: str) -> BusinessIdea:
    return BusinessIdea(
        id=idea_id,
        title="A title",
        problem_statement="A problem",
        target_market="A market",
        revenue_model="A model",
        confidence=0.6,
    )


def make_labelled(idea_id: str, **bands: tuple[int, int]) -> LabelledIdea:
    return LabelledIdea(
        idea=make_idea(idea_id),
        expected={
            ReviewerRole(role): ScoreBand(low=low, high=high)
            for role, (low, high) in bands.items()
        },
        label_rationale="a rationale",
    )


def make_record(
    idea_id: str,
    role: str,
    score: int | None,
    repeat: int = 1,
    failure_reason: str | None = None,
) -> ReviewRecord:
    return ReviewRecord(
        idea_id=idea_id,
        repeat=repeat,
        role=ReviewerRole(role),
        model="test/model",
        prompt_version="abc123",
        score=score,
        confidence=0.8 if score is not None else None,
        failure_reason=failure_reason,
    )


class TestCalibration:
    def test_a_score_inside_the_band_is_a_hit(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        report = calibration([make_record("a", "moat", 2)], labelled)
        assert report.in_band == 1
        assert report.hit_rate == 1.0
        assert report.mean_band_distance == 0.0
        assert report.misses == []

    def test_a_score_outside_the_band_is_a_miss_with_a_distance(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        report = calibration([make_record("a", "moat", 7)], labelled)
        assert report.in_band == 0
        assert report.hit_rate == 0.0
        assert report.mean_band_distance == 4.0
        assert len(report.misses) == 1
        miss = report.misses[0]
        assert (miss.idea_id, miss.role, miss.score, miss.distance) == (
            "a",
            ReviewerRole.moat,
            7,
            4,
        )

    def test_an_unlabelled_role_is_ignored(self):
        """The panel runs whole, but only labelled pairs can be scored."""
        labelled = [make_labelled("a", moat=(1, 3))]
        records = [make_record("a", "moat", 2), make_record("a", "market", 10)]
        report = calibration(records, labelled)
        assert report.labelled_scores == 1
        assert report.scored == 2
        assert [role.role for role in report.by_role] == [ReviewerRole.moat]

    def test_a_failed_review_is_dropped_not_counted_as_a_low_score(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        records = [
            make_record("a", "moat", 2),
            make_record("a", "moat", None, repeat=2, failure_reason="timeout"),
        ]
        report = calibration(records, labelled)
        assert report.failed == 1
        assert report.labelled_scores == 1
        assert report.hit_rate == 1.0

    def test_a_record_for_an_unknown_idea_is_ignored(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        report = calibration([make_record("ghost", "moat", 9)], labelled)
        assert report.labelled_scores == 0
        assert report.hit_rate == 0.0

    def test_per_role_rows_hold_their_own_numbers(self):
        labelled = [make_labelled("a", moat=(1, 3), market=(6, 9))]
        records = [make_record("a", "moat", 8), make_record("a", "market", 7)]
        report = calibration(records, labelled)
        rows = {row.role: row for row in report.by_role}
        assert rows[ReviewerRole.moat].hit_rate == 0.0
        assert rows[ReviewerRole.moat].mean_band_distance == 5.0
        assert rows[ReviewerRole.market].hit_rate == 1.0
        assert rows[ReviewerRole.market].mean_score == 7.0

    def test_rows_follow_the_role_order(self):
        labelled = [make_labelled("a", risk=(1, 3), market=(1, 3), moat=(1, 3))]
        records = [
            make_record("a", "risk", 2),
            make_record("a", "market", 2),
            make_record("a", "moat", 2),
        ]
        report = calibration(records, labelled)
        assert [row.role for row in report.by_role] == [
            ReviewerRole.market,
            ReviewerRole.moat,
            ReviewerRole.risk,
        ]

    def test_misses_are_ordered_worst_first(self):
        labelled = [make_labelled("a", moat=(1, 3)), make_labelled("b", moat=(1, 3))]
        records = [make_record("a", "moat", 5), make_record("b", "moat", 10)]
        report = calibration(records, labelled)
        assert [miss.idea_id for miss in report.misses] == ["b", "a"]

    def test_no_records_yields_an_empty_report(self):
        report = calibration([], [make_labelled("a", moat=(1, 3))])
        assert report.labelled_scores == 0
        assert report.by_role == []
        assert report.hit_rate == 0.0


class TestVariance:
    def test_repeated_identical_scores_have_no_spread(self):
        records = [make_record("a", "moat", 5, repeat=n) for n in (1, 2, 3)]
        report = variance(records)
        assert report.repeats == 3
        assert report.mean_stdev == 0.0
        assert report.by_role[0].mean_range == 0.0

    def test_spread_is_measured_per_idea_and_role(self):
        records = [
            make_record("a", "moat", 4, repeat=1),
            make_record("a", "moat", 8, repeat=2),
        ]
        report = variance(records)
        row = report.by_role[0]
        # Sample standard deviation of {4, 8}.
        assert row.mean_stdev == pytest.approx(2.8284, abs=1e-4)
        assert row.mean_range == 4.0
        assert row.worst_idea_id == "a"

    def test_a_single_repeat_measures_nothing(self):
        """One run cannot show spread, so the report must stay empty, not read 0."""
        report = variance([make_record("a", "moat", 5)])
        assert report.by_role == []
        assert report.pairs_measured == 0

    def test_ideas_are_not_pooled_together(self):
        """Two ideas that each answer consistently must not read as spread."""
        records = [
            make_record("a", "moat", 2, repeat=1),
            make_record("a", "moat", 2, repeat=2),
            make_record("b", "moat", 9, repeat=1),
            make_record("b", "moat", 9, repeat=2),
        ]
        report = variance(records)
        assert report.mean_stdev == 0.0
        assert report.by_role[0].ideas_measured == 2

    def test_the_worst_idea_is_named(self):
        records = [
            make_record("steady", "moat", 5, repeat=1),
            make_record("steady", "moat", 5, repeat=2),
            make_record("jumpy", "moat", 1, repeat=1),
            make_record("jumpy", "moat", 10, repeat=2),
        ]
        row = variance(records).by_role[0]
        assert row.worst_idea_id == "jumpy"
        assert row.worst_stdev > row.mean_stdev

    def test_failed_reviews_do_not_join_the_spread(self):
        records = [
            make_record("a", "moat", 5, repeat=1),
            make_record("a", "moat", 5, repeat=2),
            make_record("a", "moat", None, repeat=3, failure_reason="timeout"),
        ]
        assert variance(records).mean_stdev == 0.0


class TestGate:
    def test_a_role_above_the_rate_passes(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        report = calibration([make_record("a", "moat", 2)], labelled)
        assert gate(report, 0.7) == []

    def test_a_role_below_the_rate_is_named(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        report = calibration([make_record("a", "moat", 9)], labelled)
        failures = gate(report, 0.7)
        assert len(failures) == 1
        assert "moat" in failures[0]

    def test_an_empty_report_fails_rather_than_passes(self):
        """Nothing measured must never read as everything fine."""
        failures = gate(calibration([], []), 0.7)
        assert len(failures) == 1
        assert "nothing was checked" in failures[0]

    def test_a_role_whose_every_call_failed_fails_the_gate(self):
        """An outage that drops one reviewer must not read as a passing run."""
        labelled = [make_labelled("a", moat=(1, 3), financial=(5, 8))]
        records = [
            make_record("a", "moat", 2),
            make_record("a", "financial", None, failure_reason="provider timeout"),
        ]
        report = calibration(records, labelled)
        assert [role.value for role in report.unmeasured_roles] == ["financial"]

        failures = gate(report, 0.7)
        assert len(failures) == 1
        assert "financial" in failures[0]
        assert "never checked" in failures[0]

    def test_a_role_the_dataset_never_labels_does_not_fail_the_gate(self):
        """The panel runs whole, but only labelled roles can gate."""
        labelled = [make_labelled("a", moat=(1, 3))]
        records = [
            make_record("a", "moat", 2),
            make_record("a", "risk", None, failure_reason="provider timeout"),
        ]
        report = calibration(records, labelled)
        assert report.unmeasured_roles == []
        assert gate(report, 0.7) == []

    def test_the_gate_reads_the_band_and_not_the_exact_value(self):
        """Every score differs from every other, and all of them still pass."""
        labelled = [
            make_labelled("a", moat=(4, 7)),
            make_labelled("b", moat=(4, 7)),
            make_labelled("c", moat=(4, 7)),
        ]
        records = [
            make_record("a", "moat", 4),
            make_record("b", "moat", 6),
            make_record("c", "moat", 7),
        ]
        assert gate(calibration(records, labelled), 1.0) == []
