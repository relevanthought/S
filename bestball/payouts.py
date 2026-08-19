"""Illustrative tournament payout curve.

DraftKings' actual per-contest payout tables aren't published anywhere this
sandbox can reach live, and they vary by contest/buy-in anyway. This module
builds a generic, GPP-style top-heavy payout curve (a small fraction of the
field cashes, the top spot takes a disproportionate share) so a simulated
league produces a plausible $ result -- clearly an illustrative model, not
DK's real numbers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PayoutSpec:
    entry_fee: float = 25.0
    rake: float = 0.15  # DK's overround/juice
    paid_fraction: float = 0.25  # fraction of the field that cashes
    top_heaviness: float = 1.6  # higher = more winner-take-most


def payout_table(num_entries: int, spec: PayoutSpec | None = None) -> dict[int, float]:
    """Return {rank: payout_dollars} for rank 1..num_paid."""
    if num_entries < 1:
        return {}
    spec = spec or PayoutSpec()
    prize_pool = num_entries * spec.entry_fee * (1 - spec.rake)
    num_paid = max(1, round(num_entries * spec.paid_fraction))

    weights = [1.0 / (rank**spec.top_heaviness) for rank in range(1, num_paid + 1)]
    weight_sum = sum(weights)

    payouts = {}
    for rank, weight in enumerate(weights, start=1):
        payouts[rank] = round(prize_pool * weight / weight_sum, 2)
    return payouts
