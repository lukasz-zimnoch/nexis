"""Tests for the collector: the spend guard, the records it writes, and failures."""

from __future__ import annotations

import json

import pytest

from nexis.evals.dataset import LabelledIdea, ScoreBand
from nexis.evals.runner import (
    ASSUMED_INPUT_TOKENS,
    ASSUMED_OUTPUT_TOKENS,
    MANIFEST_NAME,
    REVIEWS_NAME,
    SpendLimitExceeded,
    collect,
    load_manifest,
    load_records,
    models_for_roles,
    project_cost,
)
from nexis.pricing import estimate_cost_usd
from nexis.state import BusinessIdea, Review, ReviewerRole
from nexis.telemetry import log_llm_call

CHEAP_MODEL = "openai/gpt-5.6-luna"


def make_labelled(idea_id: str) -> LabelledIdea:
    return LabelledIdea(
        idea=BusinessIdea(
            id=idea_id,
            title="A title",
            problem_statement="A problem",
            target_market="A market",
            revenue_model="A model",
            confidence=0.6,
        ),
        expected={ReviewerRole.moat: ScoreBand(low=1, high=3)},
        label_rationale="a rationale",
    )


class FakeReviewer:
    """Stands in for a ReviewerAgent without reaching the network.

    Emits a call event so the collector's measured cost goes through the same
    telemetry path a real reviewer uses.
    """

    calls: list[tuple[str, str]] = []

    def __init__(self, role, model_name, **_kwargs):
        self.role = role
        self.model_name = model_name
        self.prompt_version = "fakever0001"
        self.score = 2
        self.raises: BaseException | None = None
        self.failure_reason: str | None = None

    async def invoke_review(self, idea: BusinessIdea) -> Review:
        FakeReviewer.calls.append((idea.id, self.role.value))
        log_llm_call(
            agent="FakeReviewer",
            model=self.model_name,
            latency_ms=1.0,
            input_tokens=ASSUMED_INPUT_TOKENS,
            output_tokens=ASSUMED_OUTPUT_TOKENS,
            total_tokens=ASSUMED_INPUT_TOKENS + ASSUMED_OUTPUT_TOKENS,
            attempt=1,
            success=True,
            prompt_version=self.prompt_version,
        )
        if self.raises is not None:
            raise self.raises
        return Review(
            idea_id=idea.id,
            reviewer_role=self.role,
            score=self.score,
            rationale="because",
            confidence=0.8,
            failure_reason=self.failure_reason,
        )


@pytest.fixture(autouse=True)
def reset_fake_calls():
    FakeReviewer.calls = []
    yield
    FakeReviewer.calls = []


@pytest.fixture
def factory():
    def build(role, model_name, **kwargs):
        return FakeReviewer(role, model_name, **kwargs)

    return build


class TestModelsForRoles:
    def test_each_role_gets_its_configured_model(self, sample_config):
        models = models_for_roles(sample_config)
        assert set(models) == {role.value for role in ReviewerRole}
        assert models["market"] == sample_config.model_for("reviewer_market")

    def test_an_override_replaces_every_model(self, sample_config):
        models = models_for_roles(sample_config, CHEAP_MODEL)
        assert set(models.values()) == {CHEAP_MODEL}


class TestProjectCost:
    def test_calls_multiply_out(self):
        models = {role.value: CHEAP_MODEL for role in ReviewerRole}
        calls, _ = project_cost(models, ideas=15, repeats=5)
        assert calls == 15 * 6 * 5

    def test_cost_follows_the_price_table(self):
        models = {role.value: CHEAP_MODEL for role in ReviewerRole}
        per_call = estimate_cost_usd(
            CHEAP_MODEL, ASSUMED_INPUT_TOKENS, ASSUMED_OUTPUT_TOKENS
        )
        _, usd = project_cost(models, ideas=2, repeats=3)
        assert usd == pytest.approx(per_call * 6 * 2 * 3, abs=1e-6)

    def test_an_unpriced_model_stops_the_projection(self):
        """A missing price would let the spend guard read a real cost as zero."""
        models = {role.value: "someone/unlisted-model" for role in ReviewerRole}
        with pytest.raises(ValueError, match="No price for"):
            project_cost(models, ideas=1, repeats=1)


class TestSpendGuard:
    async def test_a_run_above_the_limit_never_calls_a_model(
        self, sample_config, tmp_path, factory
    ):
        with pytest.raises(SpendLimitExceeded):
            await collect(
                [make_labelled("a")],
                sample_config,
                tmp_path / "run",
                repeats=100,
                model_override=CHEAP_MODEL,
                max_usd=0.0001,
                reviewer_factory=factory,
            )
        assert FakeReviewer.calls == []
        assert not (tmp_path / "run" / REVIEWS_NAME).exists()

    async def test_a_run_inside_the_limit_proceeds(
        self, sample_config, tmp_path, factory
    ):
        manifest = await collect(
            [make_labelled("a")],
            sample_config,
            tmp_path / "run",
            model_override=CHEAP_MODEL,
            max_usd=1.0,
            reviewer_factory=factory,
        )
        assert manifest.projected_calls == 6
        assert len(FakeReviewer.calls) == 6

    async def test_repeats_below_one_are_rejected(
        self, sample_config, tmp_path, factory
    ):
        with pytest.raises(ValueError, match="at least 1"):
            await collect(
                [make_labelled("a")],
                sample_config,
                tmp_path / "run",
                repeats=0,
                model_override=CHEAP_MODEL,
                reviewer_factory=factory,
            )


class TestCollect:
    async def test_one_record_per_idea_role_and_repeat(
        self, sample_config, tmp_path, factory
    ):
        out = tmp_path / "run"
        await collect(
            [make_labelled("a"), make_labelled("b")],
            sample_config,
            out,
            repeats=3,
            model_override=CHEAP_MODEL,
            reviewer_factory=factory,
        )
        records = load_records(out)
        assert len(records) == 2 * 6 * 3
        assert {record.repeat for record in records} == {1, 2, 3}
        assert {record.idea_id for record in records} == {"a", "b"}
        assert {record.role for record in records} == set(ReviewerRole)

    async def test_the_manifest_lands_before_the_first_call(
        self, sample_config, tmp_path, factory
    ):
        """A run that dies halfway must still leave a directory the report can read."""
        out = tmp_path / "run"
        seen: list[bool] = []

        def build(role, model_name, **kwargs):
            seen.append((out / MANIFEST_NAME).exists())
            return FakeReviewer(role, model_name, **kwargs)

        await collect(
            [make_labelled("a")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            reviewer_factory=build,
        )
        assert all(seen)

    async def test_a_raising_reviewer_becomes_a_failed_record(
        self, sample_config, tmp_path
    ):
        def build(role, model_name, **kwargs):
            agent = FakeReviewer(role, model_name, **kwargs)
            if role is ReviewerRole.risk:
                agent.raises = RuntimeError("provider said no")
            return agent

        out = tmp_path / "run"
        await collect(
            [make_labelled("a")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            reviewer_factory=build,
        )
        records = {record.role: record for record in load_records(out)}
        assert records[ReviewerRole.risk].score is None
        assert "provider said no" in records[ReviewerRole.risk].failure_reason
        assert records[ReviewerRole.moat].score == 2

    async def test_one_failing_reviewer_does_not_stop_the_others(
        self, sample_config, tmp_path
    ):
        def build(role, model_name, **kwargs):
            agent = FakeReviewer(role, model_name, **kwargs)
            if role is ReviewerRole.risk:
                agent.raises = RuntimeError("provider said no")
            return agent

        out = tmp_path / "run"
        await collect(
            [make_labelled("a")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            reviewer_factory=build,
        )
        assert len(load_records(out)) == 6

    async def test_a_review_carrying_a_failure_reason_keeps_no_score(
        self, sample_config, tmp_path
    ):
        """The agent's own partial result is a failure, not an opinion worth 1."""

        def build(role, model_name, **kwargs):
            agent = FakeReviewer(role, model_name, **kwargs)
            agent.failure_reason = "out of retries"
            return agent

        out = tmp_path / "run"
        await collect(
            [make_labelled("a")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            reviewer_factory=build,
        )
        assert all(record.score is None for record in load_records(out))

    async def test_the_manifest_records_what_the_run_measured(
        self, sample_config, tmp_path, factory
    ):
        out = tmp_path / "run"
        manifest = await collect(
            [make_labelled("a")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            dataset_name="tests/evals/dataset.jsonl",
            reviewer_factory=factory,
        )
        assert manifest.measured_calls == 6
        assert manifest.measured_cost_usd == pytest.approx(
            manifest.projected_cost_usd, abs=1e-6
        )
        assert manifest.completed_at is not None
        assert manifest.wall_seconds >= 0
        assert load_manifest(out).run_id == manifest.run_id

    async def test_collecting_twice_into_one_directory_is_refused(
        self, sample_config, tmp_path, factory
    ):
        """Two runs under one manifest would read as a single measurement."""
        out = tmp_path / "run"
        await collect(
            [make_labelled("a")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            reviewer_factory=factory,
        )
        with pytest.raises(ValueError, match="already holds answers"):
            await collect(
                [make_labelled("a")],
                sample_config,
                out,
                model_override=CHEAP_MODEL,
                reviewer_factory=factory,
            )

    async def test_records_are_flushed_as_they_arrive(self, sample_config, tmp_path):
        """An interrupted run must keep the answers it already paid for."""
        out = tmp_path / "run"
        sizes: list[int] = []

        def build(role, model_name, **kwargs):
            path = out / REVIEWS_NAME
            sizes.append(path.stat().st_size if path.exists() else 0)
            return FakeReviewer(role, model_name, **kwargs)

        await collect(
            [make_labelled("a"), make_labelled("b"), make_labelled("c")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            reviewer_factory=build,
        )
        # The panel for the third idea starts after two panels are on disk.
        assert sizes[-1] > 0
        assert sizes[0] == 0

    async def test_records_are_valid_json_lines(self, sample_config, tmp_path, factory):
        out = tmp_path / "run"
        await collect(
            [make_labelled("a")],
            sample_config,
            out,
            model_override=CHEAP_MODEL,
            reviewer_factory=factory,
        )
        lines = (out / REVIEWS_NAME).read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 6
        for line in lines:
            assert json.loads(line)["model"] == CHEAP_MODEL


class TestLoadRecords:
    def test_a_malformed_line_names_its_number(self, tmp_path):
        out = tmp_path / "run"
        out.mkdir()
        (out / REVIEWS_NAME).write_text("not json\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r":1 is not a valid record"):
            load_records(out)
