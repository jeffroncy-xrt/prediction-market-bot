"""Order-book depth ladder for position-sizing / spread-loss analysis.

Pure functions, no external deps — unit-testable in isolation.
Used by the execution engine.execute_snipe to snapshot how much could be
bought/sold at each price level at the moment of an entry attempt.
"""
from typing import Any, Dict, List, Optional


def _to_float(level: Any, key: str) -> Optional[float]:
    try:
        return float(level.get(key))
    except (TypeError, ValueError, AttributeError):
        return None


def compute_depth_ladder(asks: List[Dict], bids: List[Dict]) -> Dict[str, Any]:
    """Cumulative buy/sell depth at key price thresholds.

    asks/bids: lists of {"price": <str|float>, "size": <str|float>} as returned
    by the Polymarket CLOB /book endpoint.

    BUY side (asks): `buy_usd_le_X` = total USDC of asks priced <= X. This is the
    max you could accumulate while keeping every fill at or below price X (i.e.
    the deployable size with no spread loss beyond X).

    SELL side (bids): `sell_usd_ge_X` = total USDC of bids priced >= X — the exit
    depth available without selling below X (matters for stop-loss on big size).
    """
    def cum_ask(thr: float):
        usd = 0.0
        sh = 0.0
        for lv in asks or []:
            p = _to_float(lv, "price")
            s = _to_float(lv, "size")
            if p is None or s is None:
                continue
            if p <= thr + 1e-9:
                usd += s * p
                sh += s
        return round(usd, 2), round(sh, 2)

    def cum_bid(thr: float) -> float:
        usd = 0.0
        for lv in bids or []:
            p = _to_float(lv, "price")
            s = _to_float(lv, "size")
            if p is None or s is None:
                continue
            if p >= thr - 1e-9:
                usd += s * p
        return round(usd, 2)

    ask_prices = [p for p in (_to_float(lv, "price") for lv in (asks or [])) if p is not None]
    bid_prices = [p for p in (_to_float(lv, "price") for lv in (bids or [])) if p is not None]

    a98 = cum_ask(0.98)
    a985 = cum_ask(0.985)
    a99 = cum_ask(0.99)
    a995 = cum_ask(0.995)
    a999 = cum_ask(0.999)

    return {
        "best_ask": round(min(ask_prices), 4) if ask_prices else None,
        "best_bid": round(max(bid_prices), 4) if bid_prices else None,
        "buy_usd_le_98": a98[0],
        "buy_usd_le_985": a985[0],
        "buy_usd_le_99": a99[0],
        "buy_usd_le_995": a995[0],
        "buy_usd_le_999": a999[0],
        "buy_sh_le_99": a99[1],
        "sell_usd_ge_99": cum_bid(0.99),
        "sell_usd_ge_97": cum_bid(0.97),
        "sell_usd_ge_95": cum_bid(0.95),
        "sell_usd_ge_90": cum_bid(0.90),
    }
