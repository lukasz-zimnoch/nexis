"""Tests for the warning that collected answers describe code that has changed."""

from __future__ import annotations

import json

from nexis.agents.reviewers import REVIEWER_PROMPTS
from nexis.config import PipelineConfig
from nexis.evals import report as report_module
from nexis.evals.__main__ import main
from nexis.evals.metrics import calibration, variance
from nexis.evals.runner import MANIFEST_NAME, REVIEWS_NAME, ReviewRecord, RunManifest
from nexis.evals.staleness import staleness_notes
from nexis.state import ReviewerRole
from nexis.telemetry import prompt_version

MIN_HIT_RATE = 0.7


def current_config() -> PipelineConfig:
    return PipelineConfig(research_prompt="unused")


def current_models() -> dict[str, str]:
    config = current_config()
    return {
        role.value: config.model_for(f"reviewer_{role.value}") for role in ReviewerRole
    }


def make_manifest(**overrides) -> RunManifest:
    fields = {
        "run_id": "eval-abc123",
        "dataset": "tests/evals/dataset.jsonl",
        "ideas": 1,
        "repeats": 1,
        "models": current_models(),
        "price_table_date": "2026-08-14",
        "started_at": "2026-08-18T10:00:00+00:00",
        "projected_calls": 6,
        "projected_cost_usd": 0.01,
    }
    fields.update(overrides)
    return RunManifest(**fields)


def fresh_record(role: ReviewerRole, score: int = 5) -> ReviewRecord:
    """A record carrying the prompt version and model the code holds right now."""
    return ReviewRecord(
        idea_id="a",
        repeat=1,
        role=role,
        model=current_models()[role.value],
        prompt_version=prompt_version(REVIEWER_PROMPTS[role]),
        score=score,
        confidence=0.8,
    )


class TestStalenessNotes:
    def test_a_fresh_run_produces_no_notes(self):
        records = [fresh_record(role) for role in ReviewerRole]
        assert staleness_notes(make_manifest(), records, current_config()) == []

    def test_a_changed_prompt_is_named(self):
        records = [fresh_record(role) for role in ReviewerRole]
        records[0] = records[0].model_copy(update={"prompt_version": "0000deadbeef"})
        notes = staleness_notes(make_manifest(), records, current_config())
        assert len(notes) == 1
        assert notes[0].startswith("market:")
        assert "0000deadbeef" in notes[0]
        assert prompt_version(REVIEWER_PROMPTS[ReviewerRole.market]) in notes[0]

    def test_a_changed_model_is_named(self):
        records = [fresh_record(role) for role in ReviewerRole]
        models = current_models()
        models["risk"] = "openai/gpt-5.6-luna"
        notes = staleness_notes(make_manifest(models=models), records, current_config())
        assert len(notes) == 1
        assert notes[0].startswith("risk:")
        assert "openai/gpt-5.6-luna" in notes[0]
        assert current_models()["risk"] in notes[0]

    def test_a_role_with_no_records_is_skipped(self):
        """Nothing was collected for it, so nothing about it can be stale."""
        records = [fresh_record(ReviewerRole.market)]
        models = current_models()
        models["risk"] = "openai/gpt-5.6-luna"
        assert (
            staleness_notes(make_manifest(models=models), records, current_config())
            == []
        )

    def test_one_role_can_be_stale_twice(self):
        records = [fresh_record(ReviewerRole.moat)]
        records[0] = records[0].model_copy(update={"prompt_version": "0000deadbeef"})
        models = current_models()
        models["moat"] = "openai/gpt-5.6-luna"
        notes = staleness_notes(make_manifest(models=models), records, current_config())
        assert len(notes) == 2
        assert all(note.startswith("moat:") for note in notes)

    def test_a_whole_panel_run_on_a_stand_in_model_is_flagged(self):
        """A debugging run must never read as a measurement of the real panel."""
        models = {role.value: "openai/gpt-5.6-luna" for role in ReviewerRole}
        records = [
            fresh_record(role).model_copy(update={"model": "openai/gpt-5.6-luna"})
            for role in ReviewerRole
        ]
        notes = staleness_notes(make_manifest(models=models), records, current_config())
        assert len(notes) == len(ReviewerRole)


class TestRendering:
    def test_notes_appear_above_the_numbers(self):
        text = report_module.render(
            make_manifest(),
            calibration([], []),
            variance([]),
            MIN_HIT_RATE,
            failures=[],
            stale_notes=[
                "moat: answers came from prompt aaa and the prompt is now bbb"
            ],
        )
        assert "**Stale run.**" in text
        assert "- moat: answers came from prompt aaa" in text
        assert text.index("**Stale run.**") < text.index("## Calibration")

    def test_a_fresh_run_says_nothing_about_staleness(self):
        text = report_module.render(
            make_manifest(),
            calibration([], []),
            variance([]),
            MIN_HIT_RATE,
            failures=[],
            stale_notes=[],
        )
        assert "Stale run" not in text


class TestCommandLine:
    def _write_run(self, tmp_path, records: list[ReviewRecord], manifest: RunManifest):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / MANIFEST_NAME).write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        (run_dir / REVIEWS_NAME).write_text(
            "\n".join(record.model_dump_json() for record in records) + "\n",
            encoding="utf-8",
        )
        return run_dir

    def _write_dataset(self, tmp_path) -> str:
        path = tmp_path / "dataset.jsonl"
        path.write_text(
            json.dumps(
                {
                    "idea": {
                        "id": "a",
                        "title": "A title",
                        "problem_statement": "A problem",
                        "target_market": "A market",
                        "revenue_model": "A model",
                        "confidence": 0.6,
                    },
                    "expected": {"moat": {"low": 4, "high": 7}},
                    "label_rationale": "a rationale",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return str(path)

    def test_a_stale_run_still_exits_zero_when_the_gate_passes(self, tmp_path, capsys):
        """Staleness explains the numbers rather than judging them."""
        records = [
            fresh_record(ReviewerRole.moat).model_copy(
                update={"prompt_version": "0000deadbeef"}
            )
        ]
        run_dir = self._write_run(tmp_path, records, make_manifest())
        code = main(
            [
                "report",
                "--run",
                str(run_dir),
                "--dataset",
                self._write_dataset(tmp_path),
            ]
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "Gate passed" in out
        assert "**Stale run.**" in out

    def test_a_fresh_run_reports_no_staleness(self, tmp_path, capsys):
        run_dir = self._write_run(
            tmp_path, [fresh_record(ReviewerRole.moat)], make_manifest()
        )
        code = main(
            [
                "report",
                "--run",
                str(run_dir),
                "--dataset",
                self._write_dataset(tmp_path),
            ]
        )
        assert code == 0
        assert "Stale run" not in capsys.readouterr().out
