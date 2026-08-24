#!/usr/bin/env python3
"""
example — template for a conviction provider (strategic research / model portfolio).

Copy, rename, edit. Nothing in core changes.

TWO DATES, NOT ONE. `signal_date` is when the source published the signal;
`read_at` is when you last looked. They are different questions and conflating
them is a real bug with a real history: a regime signal that had been unchanged
for two weeks was treated as stale because the *read* was three days old, and
the conviction leg was downgraded for no reason. Staleness gates fire on
`read_at`. The value is quoted with `signal_date`.

DO NOT INVENT A REGIME. If your source has no house view, return
status NONE and let the leg render ABSENT. `docs/DATA_SOURCES.md` is explicit:
the rules still work without this leg, and substituting your own gut for it is
the one thing that must not happen. `tools/checks.py::check_status_honesty`
FAILs any run that renders an absent leg with a green tick.
"""

PROVIDER = {
    "name": "example",
    "leg": "conviction",
    "ingestion": "browser",
    "supplies": {"regime", "weights", "changes"},
    "approx": False,
    "private": False,
    "max_age_days": 7,
}

# Pin the action vocabulary so an unrecognised verb fails loudly instead of
# being dropped. A silently-ignored "close" is a position the system still
# thinks is held.
ACTIONS = ("initiate", "increase", "trim", "close", "hold")


def load(ctx=None):
    """Return the current strategic view.

    status       "OK" | "PARTIAL" | "FAIL" | "NONE"
    regime       str — the house signal, e.g. "CASH" | "MODERATE" | "AGGRESSIVE".
                 Report the source's own vocabulary; do not normalise it here.
    signal_date  "YYYY-MM-DD" — when the source published this signal
    read_at      ISO8601 — when you captured it
    instruments  [str] — what the regime signal is expressed in, if stated
    positions    [{ticker, weight, action, bucket, change}] — model portfolio
    changes      [{date, ticker, action, reason}] — deltas since last publication
    notes        [str]
    """
    return {
        "status": "NONE",
        "regime": None,
        "signal_date": None,
        "read_at": None,
        "instruments": [],
        "positions": [],
        "changes": [],
        "notes": ["example provider — copy this file and implement load()"],
    }
