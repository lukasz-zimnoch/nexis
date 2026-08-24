"""Command line for the reviewer evals.

Two commands, on purpose. `collect` calls the models and writes their answers to
disk. `report` reads that directory and calls nothing, so every change to a
metric, a band or a threshold is free to try again.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from nexis.config import PipelineConfig
from nexis.evals import metrics, report
from nexis.evals.dataset import DEFAULT_DATASET_PATH, count_labels, load_dataset
from nexis.evals.runner import SpendLimitExceeded, collect, load_manifest, load_records
from nexis.evals.staleness import staleness_notes

# The reviewers read frozen ideas, so the research prompt never reaches a model.
UNUSED_RESEARCH_PROMPT = "not used: the eval reviews a frozen dataset"

API_KEY_VAR = "OPENROUTER_API_KEY"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexis.evals", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    collect_parser = sub.add_parser("collect", help="review the dataset, costs money")
    collect_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    collect_parser.add_argument("--out", type=Path, required=True)
    collect_parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="how many times to review each idea; 2 or more to measure variance",
    )
    collect_parser.add_argument(
        "--model",
        default=None,
        help="use one model for every role, for debugging the harness cheaply",
    )
    collect_parser.add_argument(
        "--max-usd",
        type=float,
        default=5.0,
        help="refuse to start when the projected cost is above this",
    )

    report_parser = sub.add_parser(
        "report", help="read collected answers, costs nothing"
    )
    report_parser.add_argument("--run", type=Path, required=True)
    report_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    report_parser.add_argument("--min-hit-rate", type=float, default=0.7)
    report_parser.add_argument("--out", type=Path, default=None)

    return parser


def _run_collect(args: argparse.Namespace) -> int:
    # Checked here rather than at the first call, which would fail deep inside
    # the client after the manifest is already on disk.
    if not os.environ.get(API_KEY_VAR):
        print(f"{API_KEY_VAR} is not set, so no model can be reached.", file=sys.stderr)
        return 2

    labelled = load_dataset(args.dataset)
    config = PipelineConfig(research_prompt=UNUSED_RESEARCH_PROMPT)
    print(
        f"{len(labelled)} ideas, {count_labels(labelled)} labelled scores, "
        f"{args.repeats} repeat(s)"
    )
    try:
        manifest = asyncio.run(
            collect(
                labelled,
                config,
                args.out,
                repeats=args.repeats,
                model_override=args.model,
                max_usd=args.max_usd,
                dataset_name=str(args.dataset),
            )
        )
    except SpendLimitExceeded as exc:
        print(f"Refused to start: {exc}", file=sys.stderr)
        return 2

    print(
        f"Wrote {manifest.measured_calls} calls to {args.out}, "
        f"{manifest.measured_cost_usd:.4f} USD measured against "
        f"{manifest.projected_cost_usd:.4f} USD projected"
    )
    return 0


def _run_report(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.run)
    records = load_records(args.run)
    labelled = load_dataset(args.dataset)

    calibration_report = metrics.calibration(records, labelled)
    variance_report = metrics.variance(records)
    failures = metrics.gate(calibration_report, args.min_hit_rate)
    stale_notes = staleness_notes(
        manifest, records, PipelineConfig(research_prompt=UNUSED_RESEARCH_PROMPT)
    )

    text = report.render(
        manifest,
        calibration_report,
        variance_report,
        args.min_hit_rate,
        failures=failures,
        stale_notes=stale_notes,
    )
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(text)

    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args(argv)
    if args.command == "collect":
        return _run_collect(args)
    return _run_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
