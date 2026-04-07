from __future__ import annotations

import operator
from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator
from typing_extensions import TypedDict

from nexis.config import PipelineConfig


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReviewerRole(str, Enum):
    market = "market"
    technical = "technical"
    moat = "moat"
    financial = "financial"
    risk = "risk"
    ai_resilience = "ai_resilience"


class ComplexityRating(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class MoSCoWPriority(str, Enum):
    must = "must"
    should = "should"
    could = "could"
    wont = "wont"


class OutputFormat(str, Enum):
    markdown = "markdown"
    json = "json"


# ---------------------------------------------------------------------------
# Supporting models
# ---------------------------------------------------------------------------


class TrendSignal(BaseModel):
    source: str
    signal: str
    url: str
    timestamp: str


class Feature(BaseModel):
    name: str
    description: str
    priority: MoSCoWPriority


class TechStack(BaseModel):
    languages: list[str]
    frameworks: list[str]
    databases: list[str]
    infrastructure: list[str]
    external_apis: list[str]


class Sprint(BaseModel):
    number: int
    duration_weeks: int
    deliverables: list[str]


class Channel(BaseModel):
    name: str
    rationale: str
    estimated_cost_usd: float | None = None


class PricingTier(BaseModel):
    name: str
    price: str
    description: str


class PricingModel(BaseModel):
    strategy: str
    tiers: list[PricingTier]
    notes: str


class LaunchPhase(BaseModel):
    name: str
    duration: str
    activities: list[str]
    success_metrics: list[str]


class Challenge(BaseModel):
    argument: str
    evidence: str
    counter_argument: str | None = None


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


class BusinessIdea(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    problem_statement: str
    target_market: str
    revenue_model: str
    estimated_tam: str | None = None
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    sources: list[str] = Field(default_factory=list)
    trend_signals: list[TrendSignal] = Field(default_factory=list)
    iteration: int = 0
    failure_reason: str | None = None


class Review(BaseModel):
    idea_id: str
    reviewer_role: ReviewerRole
    score: int = Field(description="Score from 1 to 10")
    rationale: str
    red_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    failure_reason: str | None = None

    @field_validator("score")
    @classmethod
    def _score_bounds(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("score must be between 1 and 10")
        return v


class MVPPlan(BaseModel):
    idea_id: str
    core_features: list[Feature]
    tech_stack: TechStack
    data_model: str
    sprint_plan: list[Sprint]
    estimated_cost_usd: float
    complexity_rating: ComplexityRating
    failure_reason: str | None = None


class GTMPlan(BaseModel):
    idea_id: str
    icp: str
    positioning: str
    channels: list[Channel]
    pricing_model: PricingModel
    launch_sequence: list[LaunchPhase]
    first_100_playbook: str
    failure_reason: str | None = None


class BusinessPlan(BaseModel):
    idea_id: str
    executive_summary: str
    key_assumptions: list[str]
    success_metrics: list[str]
    mvp_plan: MVPPlan
    gtm_plan: GTMPlan
    failure_reason: str | None = None


class Rebuttal(BaseModel):
    idea_id: str
    challenges: list[Challenge]
    severity: Severity
    suggested_mitigations: list[str]
    overall_survivability: float = Field(
        description="Survivability score between 0.0 and 1.0"
    )
    failure_reason: str | None = None


class Report(BaseModel):
    title: str
    generated_at: datetime
    ideas_evaluated: int
    ideas_selected: int
    content: str
    format: OutputFormat


# ---------------------------------------------------------------------------
# State reducers
# ---------------------------------------------------------------------------


def merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------


class PipelineState(TypedDict):
    config: PipelineConfig
    research_prompt: str
    iteration: int
    ideas: Annotated[list[BusinessIdea], operator.add]
    reviews: Annotated[list[Review], operator.add]
    scores: Annotated[dict[str, float], merge_dicts]
    top_ideas: list[str]
    mvp_plans: Annotated[dict[str, MVPPlan], merge_dicts]
    gtm_plans: Annotated[dict[str, GTMPlan], merge_dicts]
    business_plans: Annotated[dict[str, BusinessPlan], merge_dicts]
    rebuttals: Annotated[dict[str, Rebuttal], merge_dicts]
    final_reports: Annotated[list[Report], operator.add]
