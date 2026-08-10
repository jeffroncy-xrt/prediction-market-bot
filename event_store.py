"""Lightweight on-disk event store for observability.

Goals:
- Persist key bot events in /home/data (Azure) so deployments do not wipe history.
- Use JSON Lines (jsonl) for append-only logging that is easy to parse.
- Keep files bounded with simple retention.

This module is intentionally dependency-free.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Iterable, List
from datetime import datetime, timezone


AZURE_DATA_DIR = "/home/data"
APP_SERVICE_DATA_DIR = "/data"  # Azure App Service persistent mount (Linux)


def get_data_dir() -> Path:
    """Return best persistent data directory.

    Priority:
    1) /data      (Azure App Service persistent mount)
    2) /home/data (some Azure runtimes)
    3) CWD        (local/dev)
    """
    if os.path.isdir(APP_SERVICE_DATA_DIR):
        Path(APP_SERVICE_DATA_DIR).mkdir(parents=True, exist_ok=True)
        return Path(APP_SERVICE_DATA_DIR)
    if os.path.isdir("/home"):
        Path(AZURE_DATA_DIR).mkdir(parents=True, exist_ok=True)
        return Path(AZURE_DATA_DIR)
    return Path.cwd()


def get_events_dir() -> Path:
    d = get_data_dir() / "events"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _day_str(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts or time.time()))


def append_jsonl(stream: str, event: Dict[str, Any], *, ts: Optional[float] = None) -> Path:
    """Append event to `events/<stream>_YYYY-MM-DD.jsonl`.

    Returns the file path written.
    """
    t = ts or time.time()
    event = dict(event)
    event.setdefault("ts", t)
    event.setdefault("stream", stream)
    path = get_events_dir() / f"{stream}_{_day_str(t)}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path


def enforce_retention(*, stream: str, keep_days: int = 7) -> int:
    """Delete stream files older than keep_days. Returns deleted count."""
    deleted = 0
    cutoff = time.time() - keep_days * 86400
    for p in get_events_dir().glob(f"{stream}_*.jsonl"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                deleted += 1
        except OSError:
            pass
    return deleted


def read_jsonl(path: Path, *, max_lines: int = 5000) -> List[Dict[str, Any]]:
    """Read JSONL file (tail). Skips malformed lines.

    To keep the bot responsive, this reads at most max_lines from the end of the file.
    """
    from collections import deque

    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out

    try:
        dq: deque[str] = deque(maxlen=max_lines)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                dq.append(line)
        for line in dq:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    except OSError:
        return out

    return out


def events_path(stream: str, day: Optional[str] = None) -> Path:
    """Return events file path for a given stream and day (YYYY-MM-DD)."""
    if day is None:
        day = _day_str()
    return get_events_dir() / f"{stream}_{day}.jsonl"


def utc_day_str(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m-%d")


def build_daily_digest(*, day: Optional[str] = None, blocked_trades_history: Optional[list] = None) -> Dict[str, Any]:
    """Build an ops-friendly daily digest from event streams + blocked trades.

    This is deterministic (no AI) and is safe to persist.
    """
    day = day or utc_day_str()

    # Read tails only; these files can grow throughout the day
    execution = read_jsonl(events_path("execution", day), max_lines=8000)
    snipes = read_jsonl(events_path("snipes", day), max_lines=2000)

    phase = {}
    reasons = {}
    for e in execution:
        ph = e.get("phase") or "?"
        phase.setdefault(ph, {"filled": 0, "miss": 0, "skip_no_asks_cooldown": 0, "other": 0})
        ev = e.get("event")
        if ev == "filled":
            phase[ph]["filled"] += 1
        elif ev == "miss":
            phase[ph]["miss"] += 1
            r = (e.get("reason") or "").strip()[:160]
            if r:
                reasons[r] = reasons.get(r, 0) + 1
        elif ev == "skip_no_asks_cooldown":
            phase[ph]["skip_no_asks_cooldown"] += 1
        else:
            phase[ph]["other"] += 1

    top_reasons = sorted(reasons.items(), key=lambda kv: kv[1], reverse=True)[:10]

    # Blocked trades stats (24h window)
    if blocked_trades_history is None:
        # Load from persisted file if available (survives deployments)
        try:
            p = get_data_dir() / "blocked_trades.json"
            if p.exists():
                raw = json.loads(p.read_text())
                blocked_trades_history = raw.get("history") if isinstance(raw, dict) else raw
        except Exception:
            blocked_trades_history = []

    blocked = blocked_trades_history or []
    # Cap work: only scan the most recent N records (blocked_trades.json can grow)
    blocked = blocked[-5000:]
    now = time.time()
    last_24h = [r for r in blocked if now - float(r.get("ts", 0) or 0) < 86400]
    layer_counts = {}
    would_win = 0
    checked = 0
    near_miss = 0
    for r in last_24h:
        layers = r.get("blocking_layers") or []
        for L in layers:
            layer_counts[L] = layer_counts.get(L, 0) + 1
        if r.get("checked"):
            checked += 1
            if r.get("would_have_won"):
                would_win += 1
        if r.get("is_near_miss"):
            near_miss += 1

    digest = {
        "date": day,
        "events": {
            "execution_count": len(execution),
            "snipes_count": len(snipes),
        },
        "phases": phase,
        "top_miss_reasons": [{"reason": r, "count": c} for r, c in top_reasons],
        "blocked_24h": {
            "count": len(last_24h),
            "checked": checked,
            "would_have_won": would_win,
            "near_miss": near_miss,
            "layer_counts": dict(sorted(layer_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]),
        },
        "snipes": snipes[-20:],
    }
    return digest
