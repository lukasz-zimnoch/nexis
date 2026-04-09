"""CLI entry point for the Nexis pipeline."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from nexis.config import PipelineConfig
from nexis import run_pipeline


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    logging.getLogger(__name__).info(
        "LangSmith tracing %s", "enabled" if tracing_enabled else "disabled"
    )

    parser = argparse.ArgumentParser(
        prog="nexis",
        description="Autonomous multi-agent business idea pipeline",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Research prompt describing the domain or constraints for idea generation",
    )
    parser.add_argument(
        "--model",
        required=False,
        default=None,
        dest="model_name",
        help="Override ALL agent models for quick testing. Omit to use per-agent defaults from nexis/models.py.",
    )
    parser.add_argument(
        "--num-ideas",
        type=int,
        default=8,
        help="Number of candidate ideas to generate (default: 8)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Maximum number of ideas to pass from review to planning (default: 3)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        dest="score_threshold",
        help="Minimum aggregate score to pass review filter (default: 0.55)",
    )
    parser.add_argument(
        "--output-format",
        default="markdown",
        choices=["markdown", "json"],
        dest="output_format",
        help="Final report format (default: markdown)",
    )
    args = parser.parse_args()

    config_kwargs: dict = dict(
        research_prompt=args.prompt,
        num_ideas=args.num_ideas,
        top_k=args.top_k,
        score_threshold=args.score_threshold,
        output_format=args.output_format,
    )

    if args.model_name is not None:
        from nexis import models as _models

        config_kwargs["agent_models"] = {
            k: args.model_name for k in _models.AGENT_MODEL_KEYS
        }

    config = PipelineConfig(**config_kwargs)

    reports = run_pipeline(config)

    if not reports:
        print("No reports generated.", file=sys.stderr)
        sys.exit(1)

    for report in reports:
        print(report.content)


if __name__ == "__main__":
    main()
