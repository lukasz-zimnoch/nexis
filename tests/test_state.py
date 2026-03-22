"""Tests for state models."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from nexis.state import (
    BusinessIdea,
    Challenge,
    Channel,
    ComplexityRating,
    Feature,
    GTMPlan,
    LaunchPhase,
    MoSCoWPriority,
    MVPPlan,
    OutputFormat,
    PricingModel,
    Rebuttal,
    Report,
    Review,
    ReviewerRole,
    Severity,
    Sprint,
    TechStack,
    TrendSignal,
    merge_dicts,
)
from datetime import datetime


def test_business_idea_auto_uuid():
    idea = BusinessIdea(
        title="Test",
        problem_statement="A problem",
        target_market="Market",
        revenue_model="Subscription",
        confidence=0.5,
    )
    assert idea.id is not None
    assert len(idea.id) == 36  # UUID4 format


def test_business_idea_two_instances_have_different_ids():
    idea1 = BusinessIdea(
        title="Test1",
        problem_statement="P",
        target_market="M",
        revenue_model="R",
        confidence=0.5,
    )
    idea2 = BusinessIdea(
        title="Test2",
        problem_statement="P",
        target_market="M",
        revenue_model="R",
        confidence=0.5,
    )
    assert idea1.id != idea2.id


def test_business_idea_failure_reason_defaults_none():
    idea = BusinessIdea(
        title="Test",
        problem_statement="P",
        target_market="M",
        revenue_model="R",
        confidence=0.5,
    )
    assert idea.failure_reason is None


def test_business_idea_round_trip_json():
    idea = BusinessIdea(
        title="Test",
        problem_statement="P",
        target_market="M",
        revenue_model="R",
        confidence=0.7,
        sources=["https://example.com"],
        trend_signals=[
            TrendSignal(
                source="HN",
                signal="Growing trend",
                url="https://hn.com",
                timestamp="2026-01-01T00:00:00Z",
            )
        ],
    )
    json_str = idea.model_dump_json()
    restored = BusinessIdea.model_validate_json(json_str)
    assert restored == idea


def test_review_round_trip_json():
    review = Review(
        idea_id="abc",
        reviewer_role=ReviewerRole.market,
        score=8,
        rationale="Good market",
        red_flags=["Competition"],
        confidence=0.9,
    )
    restored = Review.model_validate_json(review.model_dump_json())
    assert restored == review


def test_review_failure_reason_defaults_none():
    review = Review(
        idea_id="abc",
        reviewer_role=ReviewerRole.technical,
        score=5,
        rationale="Neutral",
        confidence=0.5,
    )
    assert review.failure_reason is None


def test_review_score_bounds():
    with pytest.raises(ValidationError):
        Review(
            idea_id="abc",
            reviewer_role=ReviewerRole.risk,
            score=11,  # out of bounds
            rationale="R",
            confidence=0.5,
        )
    with pytest.raises(ValidationError):
        Review(
            idea_id="abc",
            reviewer_role=ReviewerRole.risk,
            score=0,  # out of bounds
            rationale="R",
            confidence=0.5,
        )


def test_enum_values():
    assert ReviewerRole.market.value == "market"
    assert ComplexityRating.high.value == "high"
    assert Severity.critical.value == "critical"
    assert MoSCoWPriority.must.value == "must"
    assert OutputFormat.json.value == "json"


def test_merge_dicts_reducer():
    a = {"key1": 1.0, "key2": 2.0}
    b = {"key3": 3.0, "key1": 10.0}
    result = merge_dicts(a, b)
    assert result == {"key1": 10.0, "key2": 2.0, "key3": 3.0}


def test_mvp_plan_round_trip(sample_mvp_plan):
    restored = MVPPlan.model_validate_json(sample_mvp_plan.model_dump_json())
    assert restored == sample_mvp_plan


def test_gtm_plan_round_trip(sample_gtm_plan):
    restored = GTMPlan.model_validate_json(sample_gtm_plan.model_dump_json())
    assert restored == sample_gtm_plan


def test_rebuttal_model():
    r = Rebuttal(
        idea_id="abc",
        challenges=[
            Challenge(argument="Too crowded", evidence="100 competitors", counter_argument="Niche focus")
        ],
        severity=Severity.medium,
        suggested_mitigations=["Focus on niche"],
        overall_survivability=0.6,
    )
    assert r.failure_reason is None
    restored = Rebuttal.model_validate_json(r.model_dump_json())
    assert restored == r


def test_report_model():
    r = Report(
        title="Nexis Report",
        generated_at=datetime(2026, 3, 22),
        ideas_evaluated=8,
        ideas_selected=3,
        content="# Report content",
        format=OutputFormat.markdown,
    )
    restored = Report.model_validate_json(r.model_dump_json())
    assert restored == r
