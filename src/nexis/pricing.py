"""OpenRouter prices for the models this pipeline can call.

Every price is USD per million tokens, input and output. The rates come from
OpenRouter /api/v1/models, read on 2026-08-14, and repeat the rates quoted per
assignment in nexis/models.py. A vendor changes a price whenever it wants, so
every cost derived from this table is an estimate and not a bill. Refresh the
table and the date together.
"""

from __future__ import annotations

from typing import NamedTuple

PRICE_TABLE_DATE = "2026-08-14"

_TOKENS_PER_PRICE_UNIT = 1_000_000


class ModelPrice(NamedTuple):
    input_usd_per_mtok: float
    output_usd_per_mtok: float


# openai/gpt-5.6-terra and openai/gpt-5.6-sol charge about double above 272k
# prompt tokens. Only the base rate is here: the largest Nexis prompt holds a
# few thousand tokens, three orders of magnitude below that limit.
MODEL_PRICES: dict[str, ModelPrice] = {
    "anthropic/claude-opus-5": ModelPrice(5.00, 25.00),
    "anthropic/claude-sonnet-5": ModelPrice(2.00, 10.00),
    "anthropic/claude-haiku-4.5": ModelPrice(1.00, 5.00),
    "openai/gpt-5.6-sol": ModelPrice(5.00, 30.00),
    "openai/gpt-5.6-terra": ModelPrice(1.00, 6.00),
    "openai/gpt-5.6-luna": ModelPrice(0.10, 0.60),
    "google/gemini-3.7-flash": ModelPrice(0.375, 1.875),
}


def estimate_cost_usd(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Return the estimated cost of one call in USD.

    Returns None when the table holds no price for `model`. The caller must not
    read None as zero: the call still costs money.
    """
    price = MODEL_PRICES.get(model)
    if price is None:
        return None
    return (
        input_tokens * price.input_usd_per_mtok
        + output_tokens * price.output_usd_per_mtok
    ) / _TOKENS_PER_PRICE_UNIT
