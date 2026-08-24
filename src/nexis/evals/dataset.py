"""The frozen, hand-labelled dataset the reviewer calibration eval reads.

A label is a band of acceptable scores, not one number. Two people who agree an
idea is commoditised still disagree on whether that is a 2 or a 3, so a band is
the strongest claim a human label can honestly make. `nexis.evals.metrics` gates
on the band and never on an exact value.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from nexis.state import BusinessIdea, ReviewerRole

# The dataset is test data, not shipped data: the wheel packages src/nexis only.
DEFAULT_DATASET_PATH = Path("tests/evals/dataset.jsonl")


class ScoreBand(BaseModel):
    """The range of scores a human accepts from one reviewer on one idea."""

    low: int = Field(ge=1, le=10)
    high: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def _ordered(self) -> "ScoreBand":
        if self.low > self.high:
            raise ValueError(f"band low {self.low} is above high {self.high}")
        return self

    def contains(self, score: int) -> bool:
        return self.low <= score <= self.high

    def distance(self, score: int) -> int:
        """Return how far a score sits outside the band, and 0 when inside.

        This is the error measure the calibration report averages. A band has no
        single true value, so distance to the nearest edge is the only error that
        does not punish an answer the human already called acceptable.
        """
        if score < self.low:
            return self.low - score
        if score > self.high:
            return score - self.high
        return 0


class LabelledIdea(BaseModel):
    """One frozen idea and the bands a human expects from the panel.

    `expected` holds a band only for the roles where the human holds a firm
    opinion. An unlabelled role still gets reviewed, because the panel runs whole
    and its spread feeds the variance report, but it does not gate.
    """

    idea: BusinessIdea
    expected: dict[ReviewerRole, ScoreBand] = Field(default_factory=dict)
    label_rationale: str


def load_dataset(path: Path | str = DEFAULT_DATASET_PATH) -> list[LabelledIdea]:
    """Read labelled ideas from a JSONL file, one object per line.

    Raises ValueError on a malformed line, on a duplicate idea id, or on an empty
    file. A silent gap here would shrink the eval without anybody noticing.
    """
    path = Path(path)
    labelled: list[LabelledIdea] = []
    seen: set[str] = set()

    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                item = LabelledIdea.model_validate(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path}:{number} is not a valid idea: {exc}") from exc
            if item.idea.id in seen:
                raise ValueError(f"{path}:{number} repeats idea id {item.idea.id!r}")
            seen.add(item.idea.id)
            labelled.append(item)

    if not labelled:
        raise ValueError(f"{path} holds no ideas")
    return labelled


def count_labels(labelled: list[LabelledIdea]) -> int:
    """Return how many (idea, role) pairs carry a band."""
    return sum(len(item.expected) for item in labelled)
