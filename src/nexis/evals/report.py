"""Render the eval numbers as markdown tables."""

from __future__ import annotations

from nexis.evals.metrics import CalibrationReport, VarianceReport
from nexis.evals.runner import (
    ASSUMED_INPUT_TOKENS,
    ASSUMED_OUTPUT_TOKENS,
    RunManifest,
)

# Long lists of near-identical rows bury the interesting ones.
MAX_MISS_ROWS = 20


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join("---" for _ in header) + "|")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render_run(manifest: RunManifest) -> list[str]:
    lines = ["## Run", ""]
    rows = [
        ["Run id", manifest.run_id],
        ["Dataset", manifest.dataset or "(unnamed)"],
        ["Ideas", str(manifest.ideas)],
        ["Repeats", str(manifest.repeats)],
        ["Price table", manifest.price_table_date],
        ["Started", manifest.started_at],
    ]
    if manifest.completed_at is None:
        rows.append(["Completed", "no, this run did not finish"])
    lines.extend(_table(["Field", "Value"], rows))

    lines.extend(["", "### Cost", ""])
    measured_calls = (
        str(manifest.measured_calls) if manifest.measured_calls is not None else "n/a"
    )
    measured_usd = (
        f"{manifest.measured_cost_usd:.4f}"
        if manifest.measured_cost_usd is not None
        else "n/a"
    )
    rows = [
        ["Calls", str(manifest.projected_calls), measured_calls],
        ["USD", f"{manifest.projected_cost_usd:.4f}", measured_usd],
    ]
    # Per call, so the numbers can be read straight into ASSUMED_INPUT_TOKENS and
    # ASSUMED_OUTPUT_TOKENS without arithmetic.
    if manifest.measured_calls:
        rows.append(
            [
                "Input tokens per call",
                str(ASSUMED_INPUT_TOKENS),
                str(round(manifest.measured_input_tokens / manifest.measured_calls))
                if manifest.measured_input_tokens is not None
                else "n/a",
            ]
        )
        rows.append(
            [
                "Output tokens per call",
                str(ASSUMED_OUTPUT_TOKENS),
                str(round(manifest.measured_output_tokens / manifest.measured_calls))
                if manifest.measured_output_tokens is not None
                else "n/a",
            ]
        )
    lines.extend(_table(["", "Projected", "Measured"], rows))
    lines.append("")
    lines.append(
        "The projection assumes a fixed token split per call. The measured column "
        "comes from the token counts the provider returned, so a gap between the "
        "two columns is the assumption being wrong, not the price. Set the two "
        "constants in `nexis/evals/runner.py` from the measured rows when they "
        "drift, because the spend guard refuses a run on the projection alone."
    )

    lines.extend(["", "### Panel", ""])
    lines.extend(
        _table(
            ["Role", "Model", "Temperature"],
            [
                [role, model, _temperature_cell(manifest, role)]
                for role, model in sorted(manifest.models.items())
            ],
        )
    )
    return lines


def _temperature_cell(manifest: RunManifest, role: str) -> str:
    """Name the temperature a role ran at, or say the run never recorded one."""
    if role not in manifest.temperatures:
        return "not recorded"
    temperature = manifest.temperatures[role]
    return "provider default" if temperature is None else f"{temperature}"


def render_calibration(report: CalibrationReport, min_hit_rate: float) -> list[str]:
    lines = ["## Calibration", ""]
    lines.append(
        f"{report.in_band} of {report.labelled_scores} labelled scores landed inside "
        f"the human band ({report.hit_rate:.0%}). Mean distance from the band: "
        f"{report.mean_band_distance:.2f} points."
    )
    if report.failed:
        lines.append("")
        lines.append(
            f"{report.failed} of {report.scored + report.failed} calls returned no "
            "score and were dropped rather than counted as a low score."
        )
    rows = [
        [
            role.role.value,
            str(role.labelled_scores),
            str(role.in_band),
            f"{role.hit_rate:.0%}",
            f"{role.mean_band_distance:.2f}",
            str(role.worst_distance),
            f"{role.mean_score:.1f}" if role.mean_score is not None else "n/a",
        ]
        for role in report.by_role
    ]
    # A labelled role that scored nothing still gets a row. Leaving it out of the
    # table is what let a dropped reviewer read as a passing one.
    rows.extend(
        [role.value, "0", "0", "no score", "n/a", "n/a", "n/a"]
        for role in report.unmeasured_roles
    )
    lines.extend(["", ""])
    lines.extend(
        _table(
            [
                "Role",
                "Labelled",
                "In band",
                "Hit rate",
                "Mean distance",
                "Worst",
                "Mean score",
            ],
            rows,
        )
    )
    lines.append("")
    lines.append(f"Gate: every role must reach {min_hit_rate:.0%}.")
    if report.unmeasured_roles:
        named = ", ".join(role.value for role in report.unmeasured_roles)
        lines.append("")
        lines.append(
            f"The dataset labels {named}, and this run scored none of it. A role with "
            "no answer fails the gate rather than passing it quietly."
        )

    if report.misses:
        shown = report.misses[:MAX_MISS_ROWS]
        lines.extend(["", "### Misses", ""])
        lines.extend(
            _table(
                ["Idea", "Role", "Repeat", "Score", "Band", "Distance"],
                [
                    [
                        miss.idea_id,
                        miss.role.value,
                        str(miss.repeat),
                        str(miss.score),
                        f"{miss.band_low}-{miss.band_high}",
                        str(miss.distance),
                    ]
                    for miss in shown
                ],
            )
        )
        if len(report.misses) > len(shown):
            lines.append("")
            lines.append(
                f"{len(report.misses) - len(shown)} further misses are in the collected records."
            )
    return lines


def render_variance(report: VarianceReport) -> list[str]:
    lines = ["## Variance", ""]
    if not report.by_role:
        lines.append(
            "Not measured: variance needs the same idea reviewed at least twice. "
            "Collect again with --repeats 2 or more."
        )
        return lines

    lines.append(
        f"Same {report.pairs_measured} idea and role pairs, {report.repeats} repeats "
        f"each. Mean standard deviation of the score: {report.mean_stdev:.2f} points."
    )
    lines.extend(["", ""])
    lines.extend(
        _table(
            ["Role", "Ideas", "Mean stdev", "Worst stdev", "Worst idea", "Mean range"],
            [
                [
                    role.role.value,
                    str(role.ideas_measured),
                    f"{role.mean_stdev:.2f}",
                    f"{role.worst_stdev:.2f}",
                    role.worst_idea_id,
                    f"{role.mean_range:.2f}",
                ]
                for role in report.by_role
            ],
        )
    )
    return lines


def render_staleness(stale_notes: list[str]) -> list[str]:
    """Render the warning that these answers came from code that has changed."""
    if not stale_notes:
        return []
    lines = ["**Stale run.** These answers no longer describe the current code:", ""]
    lines.extend(f"- {note}" for note in stale_notes)
    lines.append("")
    lines.append(
        "Every number below still describes what was collected. Collect again "
        "before reading any of it as a statement about the code as it stands."
    )
    return lines


def render(
    manifest: RunManifest,
    calibration_report: CalibrationReport,
    variance_report: VarianceReport,
    min_hit_rate: float,
    *,
    failures: list[str],
    stale_notes: list[str],
) -> str:
    """Render the whole report, gate verdict first.

    The staleness notes sit beside the verdict rather than in it. They do not say
    the reviewers are wrong, they say the answers are old.
    """
    lines = ["# Reviewer eval", ""]
    if failures:
        lines.append("**Gate failed.**")
        lines.append("")
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("**Gate passed.** Every role reached the required hit rate.")
    lines.append("")

    stale = render_staleness(stale_notes)
    if stale:
        lines.extend(stale)
        lines.append("")

    lines.extend(render_calibration(calibration_report, min_hit_rate))
    lines.append("")
    lines.extend(render_variance(variance_report))
    lines.append("")
    lines.extend(render_run(manifest))
    lines.append("")
    return "\n".join(lines)
