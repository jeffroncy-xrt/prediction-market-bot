"""Resolution payout when a resting take-profit sold shares early (2026-08-04).

A winning position is normally booked as `sure_shares x $1.00`. When the GTC
take-profit filled before the market resolved, those shares were already sold
— the $1.00 claim never happens for them — so the books overstated profit.

Two separate defects produced that:
  1. `_cancel_tp` captured the TP fill into `_tp_fills` only AFTER
     `resolve_position` had already computed and persisted the payout, and it
     was fired as a detached task, so the capture could not affect the number.
  2. Nothing at resolution time ever read `_tp_fills`.

This module is the payout arithmetic, kept pure so it is testable in
isolation (test_tp_payout_util.py) — the same shape as the SL payout
correction that `resolve_position` already applies for stop-loss sells.
"""

__all__ = ["corrected_win_payout"]


def corrected_win_payout(sure_shares, tp_size, tp_price):
    """Payout for a winning position, accounting for shares the TP sold.

    A resting maker SELL fills AT its limit price, so proceeds are
    `sold_shares x tp_price` with no slippage term.

    Args:
        sure_shares: shares held on the winning outcome
        tp_size:     shares the take-profit sold (0/negative = none)
        tp_price:    price the take-profit sold at (0/negative = none)

    Returns:
        float payout in USDC.
    """
    shares = max(0.0, float(sure_shares))
    size = float(tp_size or 0.0)
    price = float(tp_price or 0.0)

    if size <= 0 or price <= 0:
        return shares * 1.0

    # Never credit a sale we could not have made, and never let a bogus
    # above-$1 price beat the $1.00 resolution claim.
    sold = min(size, shares)
    price = min(price, 1.0)

    return sold * price + (shares - sold) * 1.0
