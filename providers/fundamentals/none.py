#!/usr/bin/env python3
"""
none — the publish-safe default for the fundamentals leg.

Makes no network call and returns an honest `NONE`, which the gates render as
`GATE1-INFERRED` / `GATE2-INFERRED`. That is the whole point: a clone with no
configured source produces a report where every gate says "I do not know",
never a fabricated pass. `rules/02_SLEEVE_RULES.md` states the rule this
implements — a name the scorer has no data on is a fail, not a pass.
"""

PROVIDER = {
    "name": "none",
    "leg": "fundamentals",
    "ingestion": "file",
    "supplies": set(),
    "approx": False,
    "private": False,
    "max_age_days": 36500,
}


def fetch(ticker, ctx=None):
    return {
        "score": None,
        "grade": None,
        "pillars": None,
        "eps_quarterly": None,
        "revenue_quarterly": None,
        "status": "NONE",
        "notes": [
            "no fundamentals source configured — gate 1/2 are INFERRED",
            "point `input/config/providers.json` at a provider; "
            "`derived` needs no subscription",
        ],
    }
