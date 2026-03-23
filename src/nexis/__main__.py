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
        required=True,
        dest="model_name",
        help="LLM model name (e.g., claude-sonnet-4-6, gpt-4o)",
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
    parser.add_argument(
        "--checkpoint-db",
        default="./nexis_dev.db",
        dest="checkpoint_db_path",
        help="SQLite checkpoint database path (default: ./nexis_dev.db)",
    )

    args = parser.parse_args()

    config = PipelineConfig(
        research_prompt=args.prompt,
        model_name=args.model_name,
        num_ideas=args.num_ideas,
        top_k=args.top_k,
        score_threshold=args.score_threshold,
        output_format=args.output_format,
        checkpoint_db_path=args.checkpoint_db_path,
    )

    reports = run_pipeline(config)

    if not reports:
        print("No reports generated.", file=sys.stderr)
        sys.exit(1)

    for report in reports:
        print(report.content)


if __name__ == "__main__":
    main()
