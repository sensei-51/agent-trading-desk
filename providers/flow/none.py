#!/usr/bin/env python3
"""
none — the publish-safe default for the flow leg, and the *expected* state for
the public build.

`docs/DATA_SOURCES.md` is explicit that institutional flow is the hardest leg
to replace, and that the correct response to not having it is to drop the
tactical flow read entirely rather than substitute a proxy you do not
understand. So an absent flow leg is not a degraded system — it is the system
behaving as documented. The rules already treat flow as insufficient on its own
to exit a position with a valid long-term thesis, which is why nothing breaks.
"""

PROVIDER = {
    "name": "none",
    "leg": "flow",
    "ingestion": "file",
    "supplies": set(),
    "approx": False,
    "private": False,
    "max_age_days": 36500,
}


def load(ctx=None):
    return {
        "status": "NONE",
        "session_date": None,
        "market": None,
        "tickers": {},
        "notes": ["no flow source configured — the tactical flow read is ABSENT, "
                  "not zero (DATA_SOURCES rule: drop the leg, do not proxy it)"],
    }
