"""Check whether collected answers still describe the code as it is now.

An answer is evidence about the prompt, the model, and the temperature that
produced it, and about nothing else. Reading a directory collected before any of
those changed reports a measurement of code that no longer exists, and the
numbers look exactly as trustworthy as fresh ones.

These notes explain the numbers rather than judge them, so they never change the
exit code. A person may be rereading an old run on purpose.
"""

from __future__ import annotations

from nexis.agents.reviewers import REVIEWER_PROMPTS
from nexis.config import PipelineConfig
from nexis.evals.runner import ReviewRecord, RunManifest
from nexis.state import ReviewerRole
from nexis.telemetry import prompt_version


def staleness_notes(
    manifest: RunManifest,
    records: list[ReviewRecord],
    config: PipelineConfig,
) -> list[str]:
    """Return one note per role whose answers no longer match the current code.

    Returns an empty list when every role used the prompt and the model the code
    holds today. A role with no records is skipped, because nothing was collected
    for it to be stale.
    """
    notes: list[str] = []

    for role in ReviewerRole:
        seen_prompts = {
            record.prompt_version for record in records if record.role is role
        }
        if not seen_prompts:
            continue

        current_prompt = prompt_version(REVIEWER_PROMPTS[role])
        if current_prompt not in seen_prompts:
            notes.append(
                f"{role.value}: answers came from prompt "
                f"{', '.join(sorted(seen_prompts))} and the prompt is now "
                f"{current_prompt}"
            )

        collected_model = manifest.models.get(role.value)
        current_model = config.model_for(f"reviewer_{role.value}")
        if collected_model is not None and collected_model != current_model:
            notes.append(
                f"{role.value}: answers came from {collected_model} and the panel "
                f"now uses {current_model}"
            )

        if role.value in manifest.temperatures:
            collected_temperature = manifest.temperatures[role.value]
            current_temperature = config.temperature_for(f"reviewer_{role.value}")
            if collected_temperature != current_temperature:
                notes.append(
                    f"{role.value}: answers came from temperature "
                    f"{_show(collected_temperature)} and the panel now uses "
                    f"{_show(current_temperature)}"
                )

    return notes


def _show(temperature: float | None) -> str:
    """Name a temperature, including the case where none was sent at all."""
    return "the provider default" if temperature is None else f"{temperature}"
