#!/usr/bin/env python3
"""
example — template for a flow provider (options / dark-pool / positioning).

Copy, rename, edit. Nothing in core changes.

READ THIS BEFORE YOU BUILD ONE. Several retail flow platforms prohibit
automated access in their terms. Where that is so, `ingestion: "browser"` is
the honest mode: a human or agent reads the logged-in screen and writes a
capture file, and this provider parses that file. Do not build a scraper and
label it "fetch" — the subscription at risk belongs to the user, not to you.

THE `method` BLOCK IS NOT OPTIONAL. A flow number is meaningless without the
convention that produced it. "68% bullish" computed over buy-side premium with
index names excluded is a different quantity from the same figure computed over
all prints, and pooling the two silently corrupts any later calibration.
Record the convention with the data, every time.

AND BE CAREFUL WHAT YOU CALL DIRECTION. On options flow the contract type is
fact — a put is a put — but the initiating side is inferred from where the
trade printed against the bid/ask. A bought call may be a hedge against a
short, or one leg of a spread priced separately. Report what you measured;
let the rules decide what it means.
"""

PROVIDER = {
    "name": "example",
    "leg": "flow",
    "ingestion": "browser",
    "supplies": {"premium", "direction"},
    "approx": False,
    "private": False,
    "max_age_days": 2,
}


def load(ctx=None):
    """Return the whole book's flow for one session.

    status        "OK" | "PARTIAL" | "FAIL" | "NONE"
    session_date  "YYYY-MM-DD" — the trading session the data describes
    read_at       ISO8601 — when it was captured (browser/file modes)
    method        {...} the convention behind the numbers. Include at least
                  side_filter, and any exclusions or thresholds applied.
    market        {...} optional market-wide summary
    tickers       {TICKER: {premium_usd, pct_bullish, pct_bearish, trade_count}}
    notes         [str]
    """
    return {
        "status": "NONE",
        "session_date": None,
        "read_at": None,
        "method": None,
        "market": None,
        "tickers": {},
        "notes": ["example provider — copy this file and implement load()"],
    }
