"""Validation layer agents: DevilsAdvocate and ReportGenerator."""

from __future__ import annotations

import importlib.resources
import json
import logging
from datetime import datetime, timezone

from jinja2 import DictLoader, Environment

from nexis.agents.base import BaseAgent
from nexis.state import BusinessPlan, OutputFormat, Rebuttal, Report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default template fallbacks (used when package templates cannot be loaded)
# ---------------------------------------------------------------------------

DEFAULT_REPORT_TEMPLATE = """\
# Nexis Business Idea Report

Generated: {{ now }}

## Executive Summary

{{ top_ideas | length }} idea(s) selected from {{ ideas_evaluated }} evaluated.

{% if not top_ideas %}
No viable business ideas were found that met the scoring threshold.
{% endif %}
{% for idea in top_ideas %}
## {{ idea.title }}

**Score:** {{ "%.2f"|format(scores.get(idea.id, 0)) }}

**Problem:** {{ idea.problem_statement }}

**Target Market:** {{ idea.target_market }}

**Revenue Model:** {{ idea.revenue_model }}

{% if idea.estimated_tam %}**TAM:** {{ idea.estimated_tam }}{% endif %}

{% if mvp_plans.get(idea.id) %}
### MVP Plan

**Complexity:** {{ mvp_plans[idea.id].complexity_rating.value }}

**Estimated Cost:** ${{ "%.0f"|format(mvp_plans[idea.id].estimated_cost_usd) }}

**Core Features:**
{% for feature in mvp_plans[idea.id].core_features %}
- [{{ feature.priority.value.upper() }}] {{ feature.name }}: {{ feature.description }}
{% endfor %}
{% endif %}

{% if gtm_plans.get(idea.id) %}
### GTM Plan

**ICP:** {{ gtm_plans[idea.id].icp }}

**Positioning:** {{ gtm_plans[idea.id].positioning }}

**First 100 Customers:** {{ gtm_plans[idea.id].first_100_playbook }}
{% endif %}

{% if rebuttals.get(idea.id) %}
### Devil's Advocate

**Severity:** {{ rebuttals[idea.id].severity.value }}

**Survivability:** {{ "%.0f"|format(rebuttals[idea.id].overall_survivability * 100) }}%

**Challenges:**
{% for challenge in rebuttals[idea.id].challenges %}
- {{ challenge.argument }}
{% endfor %}

**Mitigations:**
{% for m in rebuttals[idea.id].suggested_mitigations %}
- {{ m }}
{% endfor %}
{% endif %}

---
{% endfor %}
"""

DEFAULT_IDEA_CARD_TEMPLATE = """\
## {{ idea.title }}

| Field | Value |
|---|---|
| Problem | {{ idea.problem_statement }} |
| Target Market | {{ idea.target_market }} |
| Revenue Model | {{ idea.revenue_model }} |
| TAM | {{ idea.estimated_tam or "Unknown" }} |
| Confidence | {{ "%.0f"|format(idea.confidence * 100) }}% |
| Score | {{ "%.2f"|format(score) }} |

### Trend Signals

{% for signal in idea.trend_signals %}
- [{{ signal.source }}] {{ signal.signal }} ({{ signal.url }})
{% endfor %}
"""


# ---------------------------------------------------------------------------
# DevilsAdvocate
# ---------------------------------------------------------------------------


class DevilsAdvocate(BaseAgent):
    """Adversarially stress-tests business plans to surface critical weaknesses."""

    def __init__(self, model_name: str, max_retries: int = 2) -> None:
        super().__init__(
            model_name=model_name,
            output_schema=Rebuttal,
            system_prompt=(
                "You are a Devil's Advocate. Your job is to adversarially stress-test business "
                "plans. Challenge every aspect: What if a big tech company copies this in 2 weeks? "
                "What regulatory barriers could kill this? What single points of failure exist? "
                "Be specific and evidence-based."
            ),
            max_retries=max_retries,
        )

    async def invoke_rebuttal(self, plan: BusinessPlan) -> Rebuttal:
        """Generate an adversarial rebuttal for the given business plan."""
        result = await self.invoke({"business_plan": plan})
        # Ensure idea_id is correctly set when the call succeeds
        if result.failure_reason is None:
            result = Rebuttal(
                idea_id=plan.idea_id,
                challenges=result.challenges,
                severity=result.severity,
                suggested_mitigations=result.suggested_mitigations,
                overall_survivability=result.overall_survivability,
                failure_reason=result.failure_reason,
            )
        return result  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Renders the final pipeline report from state using Jinja2 templates."""

    def __init__(self) -> None:
        self._env = self._build_jinja_env()

    def _build_jinja_env(self) -> Environment:
        """Load templates using importlib.resources for installed package compatibility."""
        try:
            templates_ref = importlib.resources.files("nexis.templates")
            report_template = (templates_ref / "report.md.j2").read_text()
            idea_card_template = (templates_ref / "idea_card.md.j2").read_text()
        except Exception as exc:
            logger.warning(
                "Could not load templates from package resources (%s) — using defaults",
                exc,
            )
            report_template = DEFAULT_REPORT_TEMPLATE
            idea_card_template = DEFAULT_IDEA_CARD_TEMPLATE

        loader = DictLoader(
            {
                "report.md.j2": report_template,
                "idea_card.md.j2": idea_card_template,
            }
        )
        return Environment(loader=loader, autoescape=False)

    def generate(self, state: dict) -> Report:
        """Render a Report from the full pipeline state."""
        config = state["config"]
        ideas = state.get("ideas", [])
        top_ideas_ids = state.get("top_ideas", [])
        top_ideas = [i for i in ideas if i.id in top_ideas_ids]
        scores = state.get("scores", {})
        mvp_plans = state.get("mvp_plans", {})
        gtm_plans = state.get("gtm_plans", {})
        business_plans = state.get("business_plans", {})
        rebuttals = state.get("rebuttals", {})

        if config.output_format == "json":
            content = self._render_json(state)
        else:
            content = self._render_markdown(
                state,
                top_ideas,
                scores,
                mvp_plans,
                gtm_plans,
                business_plans,
                rebuttals,
            )

        return Report(
            title="Nexis Business Idea Report",
            generated_at=datetime.now(tz=timezone.utc),
            ideas_evaluated=len(ideas),
            ideas_selected=len(top_ideas),
            content=content,
            format=OutputFormat(config.output_format),
        )

    def _render_markdown(
        self,
        state: dict,
        top_ideas: list,
        scores: dict,
        mvp_plans: dict,
        gtm_plans: dict,
        business_plans: dict,
        rebuttals: dict,
    ) -> str:
        """Render the Markdown report template, falling back to plain text on error."""
        try:
            template = self._env.get_template("report.md.j2")
            return template.render(
                now=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                top_ideas=top_ideas,
                ideas_evaluated=len(state.get("ideas", [])),
                scores=scores,
                mvp_plans=mvp_plans,
                gtm_plans=gtm_plans,
                business_plans=business_plans,
                rebuttals=rebuttals,
            )
        except Exception as exc:
            logger.warning(
                "Template rendering failed (%s) — using plain-text fallback", exc
            )
            if not top_ideas:
                return "# Nexis Business Idea Report\n\nNo viable ideas found."
            lines = ["# Nexis Business Idea Report\n"]
            for idea in top_ideas:
                lines.append(f"## {idea.title}")
                lines.append(f"Score: {scores.get(idea.id, 0):.2f}")
            return "\n".join(lines)

    def _render_json(self, state: dict) -> str:
        """Render the pipeline state as a JSON report."""
        ideas = state.get("ideas", [])
        top_ideas_ids = state.get("top_ideas", [])
        top_ideas = [i for i in ideas if i.id in top_ideas_ids]
        data = {
            "ideas_evaluated": len(ideas),
            "top_ideas": [i.model_dump() for i in top_ideas],
            "scores": state.get("scores", {}),
        }
        return json.dumps(data, indent=2, default=str)
