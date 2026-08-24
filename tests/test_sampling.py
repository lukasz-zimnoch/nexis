"""Tests for the per-agent sampling temperature and the policy behind it."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nexis import models as models_module
from nexis import sampling
from nexis.agents import base
from nexis.config import PipelineConfig
from nexis.state import ReviewerRole


def make_config(**overrides) -> PipelineConfig:
    return PipelineConfig(research_prompt="unused", **overrides)


class TestPolicy:
    """The ordering of the bands is the decision; the exact numbers are not."""

    def test_every_reviewer_measures(self):
        """A reviewer feeds a weighted score and an eval gate, so it is an instrument."""
        config = make_config()
        for role in ReviewerRole:
            assert (
                config.temperature_for(f"reviewer_{role.value}") == sampling.MEASUREMENT
            )

    def test_the_idea_generator_sits_above_every_reviewer(self):
        config = make_config()
        generator = config.temperature_for("research_agent")
        assert generator == sampling.DIVERGENCE
        for role in ReviewerRole:
            assert generator > config.temperature_for(f"reviewer_{role.value}")

    def test_the_research_layer_is_not_uniform(self):
        """The split is measurement against invention, not layer against layer."""
        config = make_config()
        assert config.temperature_for("trend_scanner") == sampling.MEASUREMENT
        assert config.temperature_for("niche_validator") == sampling.MEASUREMENT
        assert config.temperature_for("research_agent") == sampling.DIVERGENCE

    def test_the_bands_are_ordered(self):
        assert sampling.MEASUREMENT < sampling.BALANCED < sampling.DIVERGENCE

    def test_the_two_agent_tables_describe_the_same_agents(self):
        assert set(sampling.DEFAULT_AGENT_TEMPERATURES) == set(
            models_module.DEFAULT_AGENT_MODELS
        )


class TestConfig:
    def test_temperature_for_reads_the_table(self):
        overridden = dict(sampling.DEFAULT_AGENT_TEMPERATURES)
        overridden["reviewer_market"] = 0.25
        config = make_config(agent_temperatures=overridden)
        assert config.temperature_for("reviewer_market") == 0.25
        assert config.temperature_for("reviewer_moat") == sampling.MEASUREMENT

    def test_an_unknown_agent_key_raises(self):
        config = make_config()
        with pytest.raises(ValueError, match="Unknown agent key"):
            config.temperature_for("no_such_agent")

    def test_none_means_send_no_setting(self):
        keys = dict.fromkeys(models_module.DEFAULT_AGENT_MODELS, 0.0)
        keys["reviewer_moat"] = None
        config = make_config(agent_temperatures=keys)
        assert config.temperature_for("reviewer_moat") is None

    def test_a_missing_temperature_fails_at_startup(self):
        """Otherwise the run dies part-way, after earlier calls were paid for."""
        partial = dict(sampling.DEFAULT_AGENT_TEMPERATURES)
        del partial["reviewer_risk"]
        with pytest.raises(ValueError, match="Missing a temperature"):
            make_config(agent_temperatures=partial)

    def test_a_temperature_for_an_unknown_agent_fails_at_startup(self):
        extra = dict(sampling.DEFAULT_AGENT_TEMPERATURES)
        extra["ghost_agent"] = 0.5
        with pytest.raises(ValueError, match="Unknown agent"):
            make_config(agent_temperatures=extra)


class TestBuildLlm:
    def test_the_temperature_reaches_the_client(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        with patch("nexis.agents.base.ChatOpenAI") as mock:
            base.build_llm("anthropic/claude-sonnet-5", 0.0)
        assert mock.call_args.kwargs["temperature"] == 0.0

    def test_none_sends_no_temperature_at_all(self, monkeypatch):
        """A model that rejects the setting needs a way to receive nothing."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        with patch("nexis.agents.base.ChatOpenAI") as mock:
            base.build_llm("anthropic/claude-sonnet-5", None)
        assert "temperature" not in mock.call_args.kwargs


class TestFallback:
    def test_the_fallback_model_keeps_the_temperature(self, monkeypatch):
        """A timeout must not re-sample a reviewer at a different setting."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        with patch("nexis.agents.base.build_llm") as mock_build:
            mock_build.return_value = MagicMock()
            agent = base.BaseAgent(
                model_name="slow/model",
                output_schema=MagicMock,
                system_prompt="test",
                temperature=0.0,
                fallback_model="fast/fallback",
            )
            mock_build.reset_mock()
            agent._switch_to_fallback()

        mock_build.assert_called_once_with("fast/fallback", 0.0)
