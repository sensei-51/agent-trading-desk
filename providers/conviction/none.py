#!/usr/bin/env python3
"""
none — the publish-safe default for the conviction leg.

Renders as the documented degraded path, already exercised in production on
18 Aug 2026: conviction goes ABSENT, the EXTENDED test falls back to "up >15%
from cost with no fundamental improvement", and the risk level steps
DEPLOY -> HOLD. `tools/checks.py::check_status_honesty` FAILs the run if an
absent leg is rendered with a green tick, so this state cannot be quietly
dressed up as a pass.
"""

PROVIDER = {
    "name": "none",
    "leg": "conviction",
    "ingestion": "file",
    "supplies": set(),
    "approx": False,
    "private": False,
    "max_age_days": 36500,
}


def load(ctx=None):
    return {
        "status": "NONE",
        "regime": None,
        "signal_date": None,
        "read_at": None,
        "positions": [],
        "changes": [],
        "notes": ["no conviction source configured — render as ABSENT and run the "
                  "EXTENDED test in fallback mode; do not substitute your own view"],
    }
