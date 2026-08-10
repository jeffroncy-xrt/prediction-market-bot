#!/usr/bin/env python3
"""Tests for tp_payout_util — resolution payout when a TP sold shares early.

Regression cover for the Aug-4 2026 booking bug: a resting take-profit that
filled before resolution was still booked as sure_shares x $1.00, because the
TP fill was captured (a) after resolve_position had already computed the
payout, and (b) only ever into a dict nothing read at resolution time.
"""

import sys

from tp_payout_util import corrected_win_payout

failures = []


def check(label, got, want):
    if abs(got - want) > 1e-9:
        failures.append(f"{label}: expected {want!r}, got {got!r}")


# ── No TP fill → every share claims $1.00 (unchanged behaviour) ──────────────
check("no tp fill", corrected_win_payout(10.0, 0.0, 0.0), 10.0)
check("negative size treated as none", corrected_win_payout(10.0, -1.0, 0.99), 10.0)
check("zero price treated as none", corrected_win_payout(10.0, 10.0, 0.0), 10.0)

# ── THE BUG: full TP fill at cost → payout is the sale, not $1/share ─────────
check("full fill at 0.99", corrected_win_payout(10.0, 10.0, 0.99), 9.9)
check("full fill at 0.999", corrected_win_payout(10.0, 10.0, 0.999), 9.99)
check("full fill 5 shares at 0.99", corrected_win_payout(5.0, 5.0, 0.99), 4.95)

# ── Partial fill → sold shares at fill price, rest claims $1.00 ──────────────
check("partial 4 of 10 at 0.999", corrected_win_payout(10.0, 4.0, 0.999), 4.0 * 0.999 + 6.0)
check("partial 9 of 10 at 0.99", corrected_win_payout(10.0, 9.0, 0.99), 9.0 * 0.99 + 1.0)

# ── Fill size can never exceed the position (CLOB dust / double-count guard) ─
check("oversized fill clamps to position", corrected_win_payout(10.0, 12.0, 0.99), 9.9)

# ── Fractional share sizes survive intact ───────────────────────────────────
check("fractional partial", corrected_win_payout(10.0, 2.5, 0.99), 2.5 * 0.99 + 7.5)

# ── Degenerate positions ────────────────────────────────────────────────────
check("zero-share position", corrected_win_payout(0.0, 0.0, 0.99), 0.0)

# ── A TP price above $1 is nonsense; never pay more than the claim ───────────
check("price above 1.0 clamped", corrected_win_payout(10.0, 10.0, 1.5), 10.0)

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS — 12 TP payout-correction cases (none/full/partial/clamps)")
