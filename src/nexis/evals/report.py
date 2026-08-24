"""Render the eval numbers as markdown tables."""

from __future__ import annotations

from nexis.evals.metrics import CalibrationReport, VarianceReport
from nexis.evals.runner import RunManifest

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
    lines.extend(
        _table(
            ["", "Projected", "Measured"],
            [
                ["Calls", str(manifest.projected_calls), measured_calls],
                ["USD", f"{manifest.projected_cost_usd:.4f}", measured_usd],
            ],
        )
    )
    lines.append("")
    lines.append(
        "The projection assumes a fixed token split per call. The measured column "
        "comes from the token counts the provider returned, so a gap between the "
        "two columns is the assumption being wrong, not the price."
    )

    lines.extend(["", "### Models", ""])
    lines.extend(
        _table(
            ["Role", "Model"],
            [[role, model] for role, model in sorted(manifest.models.items())],
        )
    )
    return lines


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
            [
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
            ],
        )
    )
    lines.append("")
    lines.append(f"Gate: every role must reach {min_hit_rate:.0%}.")

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


def render(
    manifest: RunManifest,
    calibration_report: CalibrationReport,
    variance_report: VarianceReport,
    min_hit_rate: float,
    failures: list[str],
) -> str:
    """Render the whole report, gate verdict first."""
    lines = ["# Reviewer eval", ""]
    if failures:
        lines.append("**Gate failed.**")
        lines.append("")
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("**Gate passed.** Every role reached the required hit rate.")
    lines.append("")

    lines.extend(render_calibration(calibration_report, min_hit_rate))
    lines.append("")
    lines.extend(render_variance(variance_report))
    lines.append("")
    lines.extend(render_run(manifest))
    lines.append("")
    return "\n".join(lines)
