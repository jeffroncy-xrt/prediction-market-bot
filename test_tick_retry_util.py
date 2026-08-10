#!/usr/bin/env python3
"""Tests for tick_retry_util — the tick-max SELL retry price decision.

Regression cover for the Aug-4 2026 "sold at cost" bug: on 1c-tick markets
the client-layer retry resubmitted a rejected TP SELL at the CLOB's stated
max (0.99) — the same price the position was bought at — so the bot sold its
winning position for exactly what it paid and forfeited the $1.00 resolution
payout.
"""

import sys

from tick_retry_util import tick_retry_price, MIN_SELL_EDGE

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want!r}, got {got!r}")


ERR_1C = "invalid price (0.999), min: 0.01 - max: 0.99"
ERR_NO_MAX = "invalid price (0.999), something else entirely"

# ── THE BUG: never retry at or below the economic floor ──────────────────────
# Entry was 0.99; a retry at max 0.99 sells at cost. Must refuse.
check("entry 0.99 -> no retry at 0.99",
      tick_retry_price(side="SELL", err_str=ERR_1C, requested_price=0.999,
                       min_price=0.99 + MIN_SELL_EDGE),
      None)

# Entry 0.985 -> floor 0.995 > 0.99. Still refuse (sub-1c edge).
check("entry 0.985 -> no retry",
      tick_retry_price(side="SELL", err_str=ERR_1C, requested_price=0.999,
                       min_price=0.985 + MIN_SELL_EDGE),
      None)

# ── Retry IS allowed when it clears the floor ────────────────────────────────
# Entry 0.98 -> floor 0.99; max 0.99 meets it exactly => retry at 0.99 (+1c).
check("entry 0.98 -> retry at 0.99",
      tick_retry_price(side="SELL", err_str=ERR_1C, requested_price=0.999,
                       min_price=0.98 + MIN_SELL_EDGE),
      0.99)

# Entry 0.95 -> comfortable edge.
check("entry 0.95 -> retry at 0.99",
      tick_retry_price(side="SELL", err_str=ERR_1C, requested_price=0.999,
                       min_price=0.95 + MIN_SELL_EDGE),
      0.99)

# ── No floor supplied = legacy behaviour preserved for other callers ─────────
check("no floor -> retry at stated max",
      tick_retry_price(side="SELL", err_str=ERR_1C, requested_price=0.999,
                       min_price=None),
      0.99)

# ── Guards that must keep working ────────────────────────────────────────────
check("BUY side never retries",
      tick_retry_price(side="BUY", err_str=ERR_1C, requested_price=0.999,
                       min_price=None),
      None)

check("unrelated error never retries",
      tick_retry_price(side="SELL", err_str="rate limited", requested_price=0.999,
                       min_price=None),
      None)

check("no parsable max -> no retry",
      tick_retry_price(side="SELL", err_str=ERR_NO_MAX, requested_price=0.999,
                       min_price=None),
      None)

# max must be strictly below what we asked for (no re-send at same price)
check("max == requested -> no retry",
      tick_retry_price(side="SELL", err_str="invalid price (0.99), max: 0.99",
                       requested_price=0.99, min_price=None),
      None)

# absurd max (below 0.5) is not trusted
check("implausible max -> no retry",
      tick_retry_price(side="SELL", err_str="invalid price (0.999), max: 0.05",
                       requested_price=0.999, min_price=None),
      None)

# case-insensitive error matching
check("uppercase error still parsed",
      tick_retry_price(side="sell", err_str="INVALID PRICE (0.999), MAX: 0.99",
                       requested_price=0.999, min_price=None),
      0.99)

# ── Floor edge: retry price exactly equal to floor is allowed ────────────────
check("max exactly at floor -> retry",
      tick_retry_price(side="SELL", err_str=ERR_1C, requested_price=0.999,
                       min_price=0.99),
      0.99)

# ── Floor edge: retry price a hair under floor is refused ────────────────────
check("max just under floor -> no retry",
      tick_retry_price(side="SELL", err_str=ERR_1C, requested_price=0.999,
                       min_price=0.9901),
      None)

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS — 13 tick-max SELL retry decision cases (floor/guards/legacy)")
