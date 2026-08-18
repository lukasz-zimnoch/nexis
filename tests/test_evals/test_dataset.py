"""Tests for the labelled dataset and the band arithmetic under it."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from nexis.evals.dataset import (
    LabelledIdea,
    ScoreBand,
    count_labels,
    load_dataset,
)
from nexis.state import ReviewerRole

# Resolved from this file so the test does not depend on the working directory.
SHIPPED_DATASET = Path(__file__).resolve().parents[1] / "evals" / "dataset.jsonl"

# Below this the sample is too small to read a hit rate from. Above it the
# labelling effort stops being honest hand work.
MIN_IDEAS = 12
MAX_IDEAS = 20

# Below this a role's hit rate moves by more than 10 points on one miss.
MIN_IDEAS_PER_ROLE = 8


class TestScoreBand:
    def test_contains_both_edges(self):
        band = ScoreBand(low=4, high=7)
        assert band.contains(4)
        assert band.contains(7)
        assert not band.contains(3)
        assert not band.contains(8)

    def test_distance_is_zero_inside(self):
        band = ScoreBand(low=4, high=7)
        assert band.distance(4) == 0
        assert band.distance(6) == 0
        assert band.distance(7) == 0

    def test_distance_counts_points_outside(self):
        band = ScoreBand(low=4, high=7)
        assert band.distance(1) == 3
        assert band.distance(10) == 3

    def test_single_point_band_is_allowed(self):
        band = ScoreBand(low=5, high=5)
        assert band.contains(5)
        assert band.distance(6) == 1

    def test_reversed_band_is_rejected(self):
        with pytest.raises(ValidationError):
            ScoreBand(low=8, high=3)

    def test_band_outside_the_score_scale_is_rejected(self):
        with pytest.raises(ValidationError):
            ScoreBand(low=0, high=5)
        with pytest.raises(ValidationError):
            ScoreBand(low=5, high=11)


def _line(idea_id: str, expected: dict | None = None) -> str:
    return json.dumps(
        {
            "idea": {
                "id": idea_id,
                "title": "A title",
                "problem_statement": "A problem",
                "target_market": "A market",
                "revenue_model": "A model",
                "confidence": 0.6,
            },
            "expected": expected
            if expected is not None
            else {"moat": {"low": 1, "high": 3}},
            "label_rationale": "because",
        }
    )


class TestLoadDataset:
    def test_reads_every_line(self, tmp_path):
        path = tmp_path / "d.jsonl"
        path.write_text(_line("a") + "\n" + _line("b") + "\n", encoding="utf-8")
        assert [item.idea.id for item in load_dataset(path)] == ["a", "b"]

    def test_blank_lines_and_comments_are_skipped(self, tmp_path):
        path = tmp_path / "d.jsonl"
        path.write_text(f"// a note\n\n{_line('a')}\n\n", encoding="utf-8")
        assert len(load_dataset(path)) == 1

    def test_duplicate_id_is_rejected(self, tmp_path):
        path = tmp_path / "d.jsonl"
        path.write_text(_line("a") + "\n" + _line("a") + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="repeats idea id"):
            load_dataset(path)

    def test_malformed_line_names_its_number(self, tmp_path):
        path = tmp_path / "d.jsonl"
        path.write_text(_line("a") + "\nnot json\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r":2 is not a valid idea"):
            load_dataset(path)

    def test_empty_file_is_rejected(self, tmp_path):
        path = tmp_path / "d.jsonl"
        path.write_text("\n\n", encoding="utf-8")
        with pytest.raises(ValueError, match="holds no ideas"):
            load_dataset(path)

    def test_an_idea_may_carry_no_label(self, tmp_path):
        path = tmp_path / "d.jsonl"
        path.write_text(_line("a", expected={}) + "\n", encoding="utf-8")
        assert count_labels(load_dataset(path)) == 0


class TestShippedDataset:
    """Guards over the dataset in the repository, not over the loader."""

    @pytest.fixture(scope="class")
    def labelled(self) -> list[LabelledIdea]:
        return load_dataset(SHIPPED_DATASET)

    def test_size_is_within_the_planned_range(self, labelled):
        assert MIN_IDEAS <= len(labelled) <= MAX_IDEAS

    def test_every_idea_carries_labels_and_a_rationale(self, labelled):
        for item in labelled:
            assert item.expected, f"{item.idea.id} has no label"
            assert len(item.label_rationale) > 80, (
                f"{item.idea.id} has a thin rationale"
            )

    def test_every_role_is_labelled_often_enough_to_measure(self, labelled):
        """A role labelled on one or two ideas gives a hit rate that is noise."""
        counts = Counter(role for item in labelled for role in item.expected)
        assert set(counts) == set(ReviewerRole)
        for role, count in counts.items():
            assert count >= MIN_IDEAS_PER_ROLE, f"{role.value} has only {count} bands"

    def test_bands_leave_room_to_be_wrong(self, labelled):
        """A one-point band gates on an exact value, which no human label supports."""
        for item in labelled:
            for role, band in item.expected.items():
                assert band.high > band.low, f"{item.idea.id}/{role.value} is a point"

    def test_labels_span_the_scale(self, labelled):
        """A dataset of only low or only high bands measures nothing."""
        lows = [band.low for item in labelled for band in item.expected.values()]
        highs = [band.high for item in labelled for band in item.expected.values()]
        assert min(lows) <= 2
        assert max(highs) >= 9
