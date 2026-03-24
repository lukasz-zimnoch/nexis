"""Tests for CLI argument parsing."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from nexis.config import PipelineConfig


def run_cli_parse(args: list[str]) -> PipelineConfig:
    """Run the CLI parser and return the constructed config."""
    import argparse
    from nexis.__main__ import main

    with patch("sys.argv", ["nexis"] + args), \
         patch("nexis.__main__.run_pipeline", return_value=[]) as mock_run, \
         patch("sys.exit") as mock_exit:
        try:
            main()
        except SystemExit:
            pass
    return mock_run


def test_help_exits_cleanly():
    """--help should print help and exit cleanly."""
    with patch("sys.argv", ["nexis", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            from nexis.__main__ import main
            main()
    assert exc_info.value.code == 0


def test_missing_prompt_raises():
    """Missing --prompt should cause argparse to exit with error."""
    with patch("sys.argv", ["nexis"]):
        with pytest.raises(SystemExit) as exc_info:
            from nexis.__main__ import main
            main()
    assert exc_info.value.code != 0


def test_valid_args_produce_correct_config():
    """Valid CLI args with --model override should set all agents to that model."""
    captured_config = {}

    def fake_run_pipeline(config):
        captured_config["config"] = config
        return []

    with patch("sys.argv", [
        "nexis",
        "--prompt", "Find dev tool ideas",
        "--model", "claude-sonnet-4-6",
        "--num-ideas", "6",
        "--top-k", "2",
        "--threshold", "0.6",
        "--output-format", "json",
    ]), patch("nexis.__main__.run_pipeline", side_effect=fake_run_pipeline), \
       patch("sys.exit"):
        from nexis.__main__ import main
        main()

    config = captured_config.get("config")
    assert config is not None
    assert config.research_prompt == "Find dev tool ideas"
    assert all(v == "claude-sonnet-4-6" for v in config.agent_models.values())
    assert config.num_ideas == 6
    assert config.top_k == 2
    assert config.score_threshold == 0.6
    assert config.output_format == "json"


def test_default_values_applied():
    """CLI defaults should match config defaults."""
    captured_config = {}

    def fake_run_pipeline(config):
        captured_config["config"] = config
        return []

    with patch("sys.argv", [
        "nexis",
        "--prompt", "test",
    ]), patch("nexis.__main__.run_pipeline", side_effect=fake_run_pipeline), \
       patch("sys.exit"):
        from nexis.__main__ import main
        main()

    config = captured_config.get("config")
    assert config is not None
    assert config.num_ideas == 8
    assert config.top_k == 3
    assert config.score_threshold == 0.55
    assert config.output_format == "markdown"


def test_model_override_applies_to_all_agents():
    """--model flag should override all agent models."""
    captured_config = {}

    def fake_run_pipeline(config):
        captured_config["config"] = config
        return []

    with patch("sys.argv", [
        "nexis",
        "--prompt", "test",
        "--model", "anthropic/claude-haiku-4-5",
    ]), patch("nexis.__main__.run_pipeline", side_effect=fake_run_pipeline), \
       patch("sys.exit"):
        from nexis.__main__ import main
        main()

    config = captured_config.get("config")
    assert config is not None
    assert all(v == "anthropic/claude-haiku-4-5" for v in config.agent_models.values())
