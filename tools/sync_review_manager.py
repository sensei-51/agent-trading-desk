#!/usr/bin/env python3
"""
sync_review_manager.py — DEPRECATED.

Use `python3 tools/sync_agents.py` instead. The reviewer is one of the agents
iterated by `sync_agents.py`. This file is kept as a one-line shim for the
documented CLI surface cited in older versions of the daily-run contract and
ensure `--check` still has the expected exit semantics. It will be removed once
nothing references it.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Path bootstrap: re-exec the new tool in-process.
NEW = os.path.join(HERE, "sync_agents.py")

if not os.path.exists(NEW):
    sys.stderr.write("sync_agents.py missing — cannot forward\n")
    sys.exit(1)
sys.argv = ["sync_agents.py"] + sys.argv[1:]
with open(NEW) as f:
    ns = {"__name__": "__main__", "__file__": NEW}
    for k, v in os.environ.items():
        ns[k] = v
    # simplest: exec the source
    exec(compile(f.read(), NEW, "exec"), ns)
