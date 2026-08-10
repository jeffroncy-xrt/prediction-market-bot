# prediction-market-bot

> **Portfolio excerpt.** This is a reduced subset of a private automated
> trading system for a prediction market. Strategy logic, entry conditions,
> thresholds, sizing and wallet handling are **not** included. What is here is
> the execution and bookkeeping layer, with its tests.
>
> Published as an engineering sample. It is not trading advice, and no
> performance is claimed.

## What is in this excerpt

| Module | Responsibility |
|---|---|
| `depth_util.py` | Order-book depth: what a given size would actually fill at |
| `event_store.py` | Append-only event log; state is rebuilt by replay |
| `tick_retry_util.py` | Retry across the venue's price-tick constraints |
| `tp_payout_util.py` | Payout arithmetic at settlement |
| `gas_guard_util.py` | Refuses on-chain actions when the fee balance is too low |

```bash
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m pytest -q
```

## Decisions worth reading

**State is an event log, not a mutable object.** Positions are rebuilt by
replaying events, so a process killed mid-operation reconstructs the same state
on restart. An in-memory position object that is mutated as fills arrive cannot
survive a restart honestly — it silently diverges from the venue.

**A price tick is a hard constraint, not a suggestion.** Orders are rejected
outright if they fall off the venue's tick grid, so prices are snapped and
retried rather than sent optimistically and lost.

**Refuse to act when a precondition is unmet.** `gas_guard_util.py` blocks
on-chain operations when the fee balance is too low to broadcast. The failure
it prevents is subtle and expensive: broadcasts fail silently, a background
task stops doing its job, and the system carries on believing it succeeded.
Bookkeeping quietly diverges from reality and nothing reports an error.

**Fills are reconciled against the venue, not assumed.** The settlement
authority is the venue's own record; local expectations are treated as a
hypothesis to be checked.

## What is not included

Strategy, signals, entry and exit conditions, thresholds, position sizing, the
live trading loop, wallet and key handling, and any historical trading data.
Those live in the private repository this was taken from.
