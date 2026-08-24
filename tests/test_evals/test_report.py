"""Tests for the rendered markdown and for the command line contract."""

from __future__ import annotations

import json

import pytest

from nexis.evals import report as report_module
from nexis.evals.__main__ import main
from nexis.evals.dataset import LabelledIdea, ScoreBand
from nexis.evals.metrics import calibration, gate, variance
from nexis.evals.runner import MANIFEST_NAME, REVIEWS_NAME, RunManifest
from nexis.state import BusinessIdea, ReviewerRole

MIN_HIT_RATE = 0.7


def make_manifest(**overrides) -> RunManifest:
    fields = {
        "run_id": "eval-abc123",
        "dataset": "tests/evals/dataset.jsonl",
        "ideas": 2,
        "repeats": 2,
        "models": {role.value: "openai/gpt-5.6-luna" for role in ReviewerRole},
        "price_table_date": "2026-08-14",
        "started_at": "2026-08-18T10:00:00+00:00",
        "projected_calls": 24,
        "projected_cost_usd": 0.00672,
        "measured_calls": 24,
        "measured_cost_usd": 0.0071,
        "wall_seconds": 42.5,
        "completed_at": "2026-08-18T10:01:00+00:00",
    }
    fields.update(overrides)
    return RunManifest(**fields)


def make_labelled(idea_id: str, **bands: tuple[int, int]) -> LabelledIdea:
    return LabelledIdea(
        idea=BusinessIdea(
            id=idea_id,
            title="A title",
            problem_statement="A problem",
            target_market="A market",
            revenue_model="A model",
            confidence=0.6,
        ),
        expected={
            ReviewerRole(role): ScoreBand(low=low, high=high)
            for role, (low, high) in bands.items()
        },
        label_rationale="a rationale",
    )


def make_record_dict(idea_id: str, role: str, score: int, repeat: int = 1) -> dict:
    return {
        "idea_id": idea_id,
        "repeat": repeat,
        "role": role,
        "model": "openai/gpt-5.6-luna",
        "prompt_version": "abc123abc123",
        "score": score,
        "confidence": 0.8,
        "red_flags": [],
        "rationale": "because",
        "failure_reason": None,
    }


class TestRender:
    def test_a_passing_gate_says_so_first(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        records = calibration([], labelled)
        text = report_module.render(
            make_manifest(), records, variance([]), MIN_HIT_RATE, []
        )
        assert text.splitlines()[2].startswith("**Gate passed.**")

    def test_a_failing_gate_lists_every_reason(self):
        text = report_module.render(
            make_manifest(),
            calibration([], []),
            variance([]),
            MIN_HIT_RATE,
            ["moat: 20% below", "risk: 30% below"],
        )
        assert "**Gate failed.**" in text
        assert "- moat: 20% below" in text
        assert "- risk: 30% below" in text

    def test_both_cost_columns_appear(self):
        text = report_module.render(
            make_manifest(), calibration([], []), variance([]), MIN_HIT_RATE, []
        )
        assert "| Projected | Measured |" in text
        assert "0.0067" in text
        assert "0.0071" in text

    def test_an_unfinished_run_is_marked(self):
        manifest = make_manifest(
            measured_calls=None, measured_cost_usd=None, completed_at=None
        )
        text = report_module.render(
            manifest, calibration([], []), variance([]), MIN_HIT_RATE, []
        )
        assert "this run did not finish" in text
        assert "n/a" in text

    def test_variance_says_why_it_is_empty(self):
        text = report_module.render(
            make_manifest(), calibration([], []), variance([]), MIN_HIT_RATE, []
        )
        assert "--repeats 2 or more" in text

    def test_misses_are_listed_with_their_band(self):
        labelled = [make_labelled("a", moat=(1, 3))]
        from nexis.evals.runner import ReviewRecord

        records = [
            ReviewRecord(
                idea_id="a",
                repeat=1,
                role=ReviewerRole.moat,
                model="m",
                prompt_version="v",
                score=9,
            )
        ]
        calibration_report = calibration(records, labelled)
        text = report_module.render(
            make_manifest(),
            calibration_report,
            variance(records),
            MIN_HIT_RATE,
            gate(calibration_report, MIN_HIT_RATE),
        )
        assert "### Misses" in text
        assert "| a | moat | 1 | 9 | 1-3 | 6 |" in text

    def test_a_long_miss_list_is_trimmed(self):
        from nexis.evals.runner import ReviewRecord

        labelled = [make_labelled(f"i{n}", moat=(1, 3)) for n in range(30)]
        records = [
            ReviewRecord(
                idea_id=f"i{n}",
                repeat=1,
                role=ReviewerRole.moat,
                model="m",
                prompt_version="v",
                score=9,
            )
            for n in range(30)
        ]
        calibration_report = calibration(records, labelled)
        text = report_module.render(
            make_manifest(), calibration_report, variance(records), MIN_HIT_RATE, []
        )
        assert "10 further misses" in text


class TestCommandLine:
    def _write_run(self, tmp_path, scores: list[tuple[str, str, int, int]]):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / MANIFEST_NAME).write_text(
            make_manifest().model_dump_json(indent=2), encoding="utf-8"
        )
        lines = [
            json.dumps(make_record_dict(idea, role, score, repeat))
            for idea, role, score, repeat in scores
        ]
        (run_dir / REVIEWS_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return run_dir

    def _write_dataset(self, tmp_path, items: list[LabelledIdea]):
        path = tmp_path / "dataset.jsonl"
        path.write_text(
            "\n".join(item.model_dump_json() for item in items) + "\n", encoding="utf-8"
        )
        return path

    def test_report_exits_zero_when_every_role_passes(self, tmp_path, capsys):
        run_dir = self._write_run(tmp_path, [("a", "moat", 2, 1)])
        dataset = self._write_dataset(tmp_path, [make_labelled("a", moat=(1, 3))])
        code = main(["report", "--run", str(run_dir), "--dataset", str(dataset)])
        assert code == 0
        assert "Gate passed" in capsys.readouterr().out

    def test_report_exits_one_when_a_role_fails(self, tmp_path, capsys):
        """CI reads this exit code, so a bad calibration must not look like success."""
        run_dir = self._write_run(tmp_path, [("a", "moat", 10, 1)])
        dataset = self._write_dataset(tmp_path, [make_labelled("a", moat=(1, 3))])
        code = main(["report", "--run", str(run_dir), "--dataset", str(dataset)])
        assert code == 1
        assert "Gate failed" in capsys.readouterr().out

    def test_report_writes_a_file_when_asked(self, tmp_path):
        run_dir = self._write_run(tmp_path, [("a", "moat", 2, 1)])
        dataset = self._write_dataset(tmp_path, [make_labelled("a", moat=(1, 3))])
        out = tmp_path / "report.md"
        main(
            [
                "report",
                "--run",
                str(run_dir),
                "--dataset",
                str(dataset),
                "--out",
                str(out),
            ]
        )
        assert "# Reviewer eval" in out.read_text(encoding="utf-8")

    def test_report_reads_repeats_as_variance(self, tmp_path, capsys):
        run_dir = self._write_run(tmp_path, [("a", "moat", 2, 1), ("a", "moat", 3, 2)])
        dataset = self._write_dataset(tmp_path, [make_labelled("a", moat=(1, 3))])
        main(["report", "--run", str(run_dir), "--dataset", str(dataset)])
        out = capsys.readouterr().out
        assert "## Variance" in out
        assert "--repeats 2 or more" not in out

    def test_collect_refuses_a_run_over_budget(self, tmp_path, capsys):
        """Exit code 2 separates a refusal to spend from a failed gate."""
        dataset = self._write_dataset(tmp_path, [make_labelled("a", moat=(1, 3))])
        code = main(
            [
                "collect",
                "--dataset",
                str(dataset),
                "--out",
                str(tmp_path / "run"),
                "--max-usd",
                "0.0000001",
            ]
        )
        assert code == 2
        assert "Refused to start" in capsys.readouterr().err

    def test_collect_says_when_the_api_key_is_missing(
        self, tmp_path, capsys, monkeypatch
    ):
        """A clear message beats a KeyError from inside the client."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        dataset = self._write_dataset(tmp_path, [make_labelled("a", moat=(1, 3))])
        code = main(
            ["collect", "--dataset", str(dataset), "--out", str(tmp_path / "run")]
        )
        assert code == 2
        assert "OPENROUTER_API_KEY" in capsys.readouterr().err
        assert not (tmp_path / "run").exists()

    def test_an_unknown_command_is_rejected(self):
        with pytest.raises(SystemExit):
            main(["nonsense"])
