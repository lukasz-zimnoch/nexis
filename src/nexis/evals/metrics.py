"""Turn collected reviews into calibration and variance numbers. Costs nothing.

Two questions, two reports. Calibration asks whether a reviewer agrees with a
human. Variance asks whether it agrees with itself. A reviewer can pass one and
fail the other, so neither number replaces the other.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from pydantic import BaseModel, Field

from nexis.evals.dataset import LabelledIdea, ScoreBand
from nexis.evals.runner import ReviewRecord
from nexis.state import ReviewerRole


class Miss(BaseModel):
    """One score that landed outside the band a human set for it."""

    idea_id: str
    role: ReviewerRole
    repeat: int
    score: int
    band_low: int
    band_high: int
    distance: int


class RoleCalibration(BaseModel):
    role: ReviewerRole
    labelled_scores: int
    in_band: int
    hit_rate: float
    # Mean distance from the band, counting a score inside the band as 0. This is
    # the mean absolute error of a label that is a range and not a point.
    mean_band_distance: float
    worst_distance: int
    mean_score: float | None = None


class CalibrationReport(BaseModel):
    labelled_scores: int
    scored: int
    failed: int
    in_band: int
    hit_rate: float
    mean_band_distance: float
    by_role: list[RoleCalibration] = Field(default_factory=list)
    # Roles the dataset labels but the run never scored, because every call failed
    # or the run never reached them. They carry no hit rate, so they cannot appear
    # in by_role, and a silent absence there would read as a pass.
    unmeasured_roles: list[ReviewerRole] = Field(default_factory=list)
    misses: list[Miss] = Field(default_factory=list)


class RoleVariance(BaseModel):
    role: ReviewerRole
    ideas_measured: int
    # Sample standard deviation of the score across repeats of one idea, averaged
    # over ideas.
    mean_stdev: float
    worst_stdev: float
    worst_idea_id: str
    # Mean of (highest score - lowest score) per idea. Easier to read than a
    # standard deviation when N is small.
    mean_range: float


class VarianceReport(BaseModel):
    repeats: int
    pairs_measured: int
    mean_stdev: float
    by_role: list[RoleVariance] = Field(default_factory=list)


def _scored(records: list[ReviewRecord]) -> list[ReviewRecord]:
    return [r for r in records if r.score is not None and r.failure_reason is None]


def calibration(
    records: list[ReviewRecord], labelled: list[LabelledIdea]
) -> CalibrationReport:
    """Compare every score against the band its idea and role carry.

    A record whose (idea, role) has no band is ignored: the panel runs whole, but
    only the pairs a human was willing to label can gate.
    """
    bands: dict[tuple[str, ReviewerRole], ScoreBand] = {}
    for item in labelled:
        for role, band in item.expected.items():
            bands[(item.idea.id, role)] = band

    usable = _scored(records)
    failed = len(records) - len(usable)

    misses: list[Miss] = []
    per_role_distance: dict[ReviewerRole, list[int]] = defaultdict(list)
    per_role_scores: dict[ReviewerRole, list[int]] = defaultdict(list)
    per_role_hits: dict[ReviewerRole, int] = defaultdict(int)

    for record in usable:
        band = bands.get((record.idea_id, record.role))
        if band is None:
            continue
        score = record.score
        assert score is not None  # _scored filtered these out
        distance = band.distance(score)
        per_role_distance[record.role].append(distance)
        per_role_scores[record.role].append(score)
        if distance == 0:
            per_role_hits[record.role] += 1
        else:
            misses.append(
                Miss(
                    idea_id=record.idea_id,
                    role=record.role,
                    repeat=record.repeat,
                    score=score,
                    band_low=band.low,
                    band_high=band.high,
                    distance=distance,
                )
            )

    labelled_roles = {role for _, role in bands}

    by_role: list[RoleCalibration] = []
    unmeasured_roles: list[ReviewerRole] = []
    for role in ReviewerRole:
        distances = per_role_distance.get(role)
        if not distances:
            if role in labelled_roles:
                unmeasured_roles.append(role)
            continue
        scores = per_role_scores[role]
        by_role.append(
            RoleCalibration(
                role=role,
                labelled_scores=len(distances),
                in_band=per_role_hits[role],
                hit_rate=round(per_role_hits[role] / len(distances), 4),
                mean_band_distance=round(statistics.fmean(distances), 4),
                worst_distance=max(distances),
                mean_score=round(statistics.fmean(scores), 3),
            )
        )

    total_scores = sum(c.labelled_scores for c in by_role)
    total_hits = sum(c.in_band for c in by_role)
    all_distances = [d for values in per_role_distance.values() for d in values]

    misses.sort(key=lambda m: (-m.distance, m.idea_id, m.role.value, m.repeat))

    return CalibrationReport(
        labelled_scores=total_scores,
        scored=len(usable),
        failed=failed,
        in_band=total_hits,
        hit_rate=round(total_hits / total_scores, 4) if total_scores else 0.0,
        mean_band_distance=round(statistics.fmean(all_distances), 4)
        if all_distances
        else 0.0,
        by_role=by_role,
        unmeasured_roles=unmeasured_roles,
        misses=misses,
    )


def variance(records: list[ReviewRecord]) -> VarianceReport:
    """Measure how far a reviewer's score moves when nothing about the idea moves.

    Needs at least two repeats of the same (idea, role). Pairs with fewer are
    skipped, so a calibration run with one repeat yields an empty report rather
    than a misleading zero.
    """
    usable = _scored(records)
    repeats = len({r.repeat for r in usable})

    grouped: dict[tuple[str, ReviewerRole], list[int]] = defaultdict(list)
    for record in usable:
        assert record.score is not None
        grouped[(record.idea_id, record.role)].append(record.score)

    per_role: dict[ReviewerRole, list[tuple[str, float, int]]] = defaultdict(list)
    for (idea_id, role), scores in grouped.items():
        if len(scores) < 2:
            continue
        per_role[role].append(
            (idea_id, statistics.stdev(scores), max(scores) - min(scores))
        )

    by_role: list[RoleVariance] = []
    for role in ReviewerRole:
        measured = per_role.get(role)
        if not measured:
            continue
        worst = max(measured, key=lambda entry: entry[1])
        by_role.append(
            RoleVariance(
                role=role,
                ideas_measured=len(measured),
                mean_stdev=round(statistics.fmean(e[1] for e in measured), 4),
                worst_stdev=round(worst[1], 4),
                worst_idea_id=worst[0],
                mean_range=round(statistics.fmean(e[2] for e in measured), 4),
            )
        )

    pairs = sum(role_variance.ideas_measured for role_variance in by_role)
    overall = [entry[1] for values in per_role.values() for entry in values]

    return VarianceReport(
        repeats=repeats,
        pairs_measured=pairs,
        mean_stdev=round(statistics.fmean(overall), 4) if overall else 0.0,
        by_role=by_role,
    )


def gate(report: CalibrationReport, min_hit_rate: float) -> list[str]:
    """Return one message per role below the required hit rate, empty when all pass.

    The gate reads the band and never an exact score, so a reviewer that answers
    within human tolerance passes even when no two runs agree on the number.

    A role the dataset labels but the run never scored also fails. No answer is not
    a pass: an outage that drops every call from one reviewer would otherwise leave
    a green run carrying no opinion from it at all.
    """
    failures = [
        f"{role.role.value}: {role.hit_rate:.0%} of {role.labelled_scores} labelled "
        f"scores in band, below the required {min_hit_rate:.0%}"
        for role in report.by_role
        if role.hit_rate < min_hit_rate
    ]
    failures.extend(
        f"{role.value}: no labelled score was collected, so the role was never checked"
        for role in report.unmeasured_roles
    )
    if not report.by_role and not report.unmeasured_roles:
        failures.append("no labelled score was collected, so nothing was checked")
    return failures
