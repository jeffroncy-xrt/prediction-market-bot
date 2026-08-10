"""Tick-aware SELL retry decision.

Some markets quote on a coarser price tick than others, so an order priced
just under the maximum is rejected outright with a stated min/max. An earlier
client-layer fix parsed that stated maximum and resubmitted once at the top of
the range — but it was price-blind: it did not know what the position had cost.

On a coarse-tick market that turned a take-profit into an order resting at
roughly the entry price. On a near-certain position the resting bid sits right
there, so it filled within seconds — closing the position for what it cost and
forfeiting the settlement payout instead.

The engine already implemented the correct policy: fall back to the top tick
only when the entry price leaves a margin, and otherwise skip the take-profit
and hold to resolution. That guard only ran when order creation returned
nothing, and the retry made order creation *succeed* — so the guard became
dead code.

This module holds the retry decision as pure logic, so the price floor is
enforced in one place and is testable in isolation.
"""

import re

# A retry must clear the entry price by at least this much to be worth doing.
# Below 1c/share the $1.00 resolution claim beats selling into the book.
MIN_SELL_EDGE = 0.01

_MAX_RE = re.compile(r"max:?\s*\$?(0\.\d+)")

# The lowest stated max we will believe; anything under this looks like a
# malformed/unrelated error rather than a tick ceiling.
MIN_PLAUSIBLE_MAX = 0.5

__all__ = ["tick_retry_price", "MIN_SELL_EDGE", "MIN_PLAUSIBLE_MAX"]


def tick_retry_price(*, side, err_str, requested_price, min_price=None):
    """Return the price to resubmit a rejected SELL at, or None to not retry.

    Args:
        side:            order side; only SELL is ever retried
        err_str:         the CLOB error text (parsed for the stated max)
        requested_price: the price that was rejected
        min_price:       economic floor — refuse to retry below it. Pass
                         `entry_price + MIN_SELL_EDGE` for a take-profit.
                         None keeps the pre-existing behaviour (no floor).

    Returns:
        float retry price, or None.
    """
    if str(side).upper() != "SELL":
        return None
    if "invalid price" not in str(err_str).lower():
        return None

    m = _MAX_RE.search(str(err_str).lower())
    if not m:
        return None

    max_px = float(m.group(1))
    if not (MIN_PLAUSIBLE_MAX <= max_px < float(requested_price)):
        return None

    # The floor is the whole point: never sell at or below what we paid.
    if min_price is not None and max_px < float(min_price):
        return None

    return max_px
