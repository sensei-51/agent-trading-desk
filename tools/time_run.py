#!/usr/bin/env python3
"""
time_run.py — measure where the pipeline spends its time.

The pipeline has two execution phases:

  Phase A — `run_daily.py` (data ingestion)
    Already self-timed: every step records `seconds` in
    `output/.state/run_manifest.json` (checks-pre, radar, facts,
    fundamentals, xray, checks-post — see `run_daily.py:118`).

  Phase B — the Trader phase (the checklist of `agents/trader.md`)
    Until this script existed, was untimed. The Trader reads
    artefacts, runs the macro search, applies gate cards, writes
    `output/evaluation_<date>.md`, runs validation and the Reviewer
    checklist. Whichever subagent does
    it cannot see how long it spent, so over-spend on macro
    search or under-spend on validation are equally invisible.

This script fills that gap. Its design:

  1. `TradeTimer` — a context-manager / `mark()` API the Trader
     subagent imports and calls between phases. Each `mark()`
     closes the previous phase and opens the next, recording the
     duration spent in the prior phase.

  2. CLI interface — ad-hoc timing:
          python3 tools/time_run.py mark macro
          python3 tools/time_run.py mark gates
          python3 tools/time_run.py mark write
          python3 tools/time_run.py summary
          python3 tools/time_run.py summary --phase data+trader

  3. Auto-fingerprinted — appends to
     `output/.state/trader_timings_<date>.json`, sha1-locked
     against the artefacts the Trader consumed (same invariant
     `run_daily.py` enforces: post-run regeneration is detectable).

  4. Joins to `run_manifest.json` — the summary prints both phases
     side by side, plus the total wall-clock from the manifest's
     `started` to the Trader's last `mark()`.

The Trader phase names below track the checklist of `agents/trader.md`
— keeping them aligned keeps a future drift check trivial (line up the
names against the canonical and diff).

Usage in a script:
    from tools.time_run import TradeTimer
    t = TradeTimer(date="2026-08-20")
    t.mark("start")
    ...read artefacts...
    t.mark("read")
    ...macro search...
    t.mark("macro")
    ...gates...
    t.mark("gates")
    ...write evaluation...
    t.mark("write")
    ...review...
    t.mark("review")
    ...save...
    t.mark("end")
    t.report()

Standard library only.
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))
STATE_DIR = os.path.join(OUTPUT_DIR, ".state")

# Canonical phase names — mirror the Trader's `agents/trader.md`
# checklist so a drift check can diff them.
PHASES = [
    "start",         # Trader begins work; records wall-clock anchor
    "read",          # §0-1 — manifest, Analyst handoff, rotation read, 4 sheets
    "macro",         # §2 — web search for index/oil/gold/FX + geopolitics
    "signals",       # §3-5 — interpretation + gates + signal assignment
    "sizing",        # §6 — caps, stops, risk-budget math
    "write",         # §7 — draft report and its required sections
    "validate",      # §8 — eval_reviewer.py + the stop-pair hand check
    "review",        # orchestrator step 5 — manager subagent pre-save check
    "save",          # §9 — write evaluation_<date>.md
    "end",           # last mark — closes the run
]


def trader_path(date):
    return os.path.join(STATE_DIR, f"trader_timings_{date}.json")


def manifest_path():
    return os.path.join(STATE_DIR, "run_manifest.json")


def today():
    return datetime.date.today().isoformat()


def closed_run_on_disk(date):
    """The already-finished timing record for `date`, or None.

    A record counts as CLOSED when its last phase is a finished `end`. A second
    pipeline run on the same day is supported (decision 2026-08-23) and must not
    append into that list — see the `mark` CLI for why. Callers carry the return
    value into `previous_runs[]` and start a fresh phase list.
    """
    tp = trader_path(date)
    if not os.path.exists(tp):
        return None
    try:
        with open(tp, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        return None                    # unreadable: treat as a fresh run
    phases = prev.get("phases") or []
    if not phases or phases[-1].get("name") != "end" \
            or phases[-1].get("finished") is None:
        return None
    return prev


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class TradeTimer:
    """Collect per-phase durations for a Trader run.

    Use `mark(name)` between phases. `name` must be one of
    `PHASES`. Out-of-order marks are recorded but flagged in
    the report — the rule says Phase B steps happen but does
    not enforce order; an LLM calling `mark("save")` before
    `mark("write")` is a real failure mode and should surface.
    """

    def __init__(self, date=None, artefact_globs=None):
        self.date = date or today()
        # Same-day re-run: a finished record for this date belongs to an earlier
        # run of the pipeline. `finish()` writes with "w", so without this the
        # second run silently replaces the first run's timings.
        self.previous_runs = []
        already = closed_run_on_disk(self.date)
        if already:
            self.previous_runs = list(already.get("previous_runs") or [])
            self.previous_runs.append(
                {k: v for k, v in already.items() if k != "previous_runs"})
        self.artefact_globs = artefact_globs or [
            "output/data/facts_<date>.md",
            "output/data/fundamentals_<date>.md",
            "output/data/flow_<date>.md",
            "output/data/xray_<date>.md",
            "output/radar/Heartbeat_Radar_<date>.md",
            "output/data/analyst_<date>.md",
            "output/evaluation_<date>.md",
        ]
        self.entries = []  # [{name, started, finished, seconds}]
        self._t0 = time.time()
        first = {
            "name": "start",
            "started": datetime.datetime.fromtimestamp(self._t0).isoformat(timespec="microseconds"),
            "finished": None,
            "seconds": None,
        }
        self.entries.append(first)
        self._last_open = first

    @staticmethod
    def _t0_of(entry):
        return datetime.datetime.fromisoformat(entry["started"]).timestamp()

    def mark(self, name):
        if name not in PHASES:
            raise ValueError(
                f"unknown phase {name!r}; expected one of {PHASES}")
        now = time.time()
        # Same-name repeat: closing it first (the only open phase can be a
        # repeat of THIS name) and then re-opening it would zero the
        # duration. Detect that pattern and ignore the second call — the
        # caller (finish() then the CLI's mark("end")) hits this when
        # they inadvertently double-book.
        if (self._last_open is not None
                and self._last_open["finished"] is None
                and self._last_open["name"] == name):
            return  # no-op: same phase; stay open until a different mark arrives
        # Close the previous open entry if there is one and it is still open
        if self._last_open is not None and self._last_open["finished"] is None:
            self._last_open["finished"] = datetime.datetime.fromtimestamp(now).isoformat(timespec="microseconds")
            self._last_open["seconds"] = round(now - self._t0_of(self._last_open), 3)
        entry = {
            "name": name,
            "started": datetime.datetime.fromtimestamp(now).isoformat(timespec="microseconds"),
            "finished": None,
            "seconds": None,
        }
        self.entries.append(entry)
        self._last_open = entry

    def finish(self):
        """Close the run, finger-print consumed artefacts, write the json."""
        # If `end` is already open, close it; otherwise open and close it.
        existing_end_open = (self._last_open is not None
                             and self._last_open["name"] == "end"
                             and self._last_open["finished"] is None)
        if not existing_end_open:
            self.mark("end")
        # Close the open `end` entry explicitly (mark() may be a no-op if
        # `end` is the same name being repeated).
        if self._last_open is not None and self._last_open["finished"] is None:
            now_iso = datetime.datetime.now().isoformat(timespec="microseconds")
            self._last_open["finished"] = now_iso
            self._last_open["seconds"] = round(
                datetime.datetime.now().timestamp()
                - datetime.datetime.fromisoformat(self._last_open["started"]).timestamp(),
                3)
        artefacts = {}
        for rel in self.artefact_globs:
            p = rel.replace("<date>", self.date)
            full = os.path.join(ROOT, p)
            if os.path.exists(full):
                real = os.path.realpath(full)
                artefacts[p] = {
                    "mtime": datetime.datetime.fromtimestamp(
                        os.path.getmtime(real)).isoformat(timespec="seconds"),
                    "sha1": sha1(real),
                }
        record = {
            "date": self.date,
            "started": self.entries[0]["started"],
            "finished": self.entries[-1]["finished"],
            "phases": self.entries,
            "artefacts": artefacts,
        }
        # Validation: did the run finish in the canonical order?
        order = [e["name"] for e in self.entries]
        canonical_idx = [PHASES.index(n) for n in order]
        record["in_order"] = canonical_idx == sorted(canonical_idx)
        if self.previous_runs:
            record["run"] = len(self.previous_runs) + 1
            record["previous_runs"] = self.previous_runs
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(trader_path(self.date), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=1)
        return record

    def report(self):
        """Close the run and print a one-screen summary."""
        rec = self.finish()
        self._print_summary(rec)
        return rec

    @staticmethod
    def _print_summary(rec):
        print(f"\n=== Trader timing — {rec['date']} ===")
        print(f"{'phase':<10} {'seconds':>10}  started → finished")
        for e in rec["phases"]:
            if e["seconds"] is None:
                continue
            sh = e["started"].split("T", 1)[-1][:12]
            fh = e["finished"].split("T", 1)[-1][:12]
            print(f"  {e['name']:<8} {e['seconds']:>9.2f}s  {sh} → {fh}")
        total = sum(e["seconds"] for e in rec["phases"]
                    if e["seconds"] is not None)
        print(f"  {'TOTAL':<8} {total:>9.2f}s")
        if not rec["in_order"]:
            print("  ⚠️  phases out of canonical order")
        print(f"\nartefacts fingerprinted: {len(rec['artefacts'])}")
        for path, fp in rec["artefacts"].items():
            print(f"  {path}  sha1={fp['sha1'][:10]}…")
        # Join to manifest
        mp = manifest_path()
        if os.path.exists(mp):
            with open(mp) as f:
                m = json.load(f)
            try:
                trader_finish_iso = rec["finished"]
                if trader_finish_iso:
                    wall = (datetime.datetime.fromisoformat(trader_finish_iso)
                            - datetime.datetime.fromisoformat(m["started"])).total_seconds()
                    print(f"\nfull pipeline wall-clock (manifest start → trader end): "
                          f"{wall:.1f}s")
            except (TypeError, ValueError):
                pass  # finished still open — nothing to compare


def load(date=None):
    date = date or today()
    p = trader_path(date)
    if not os.path.exists(p):
        print(f"no trader timings at {os.path.relpath(p, ROOT)}", file=sys.stderr)
        sys.exit(1)
    with open(p) as f:
        return json.load(f)


def summary(date=None, scope="data+trader"):
    date = date or today()

    def section(title, rec, indent=0):
        pad = "  " * indent
        print(f"{pad}=== {title} ===")
        if rec is None:
            print(f"{pad}  (no record)")
            return 0.0
        if "steps" in rec:
            for s in rec["steps"]:
                print(f"{pad}  {s['name']:<14} {s['seconds']:>7.1f}s")
            return sum(s["seconds"] for s in rec["steps"])
        for e in rec["phases"]:
            if e["seconds"] is None:
                continue
            print(f"{pad}  {e['name']:<14} {e['seconds']:>7.2f}s")
        return sum(e["seconds"] for e in rec["phases"] if e["seconds"] is not None)

    data_total = 0.0
    trader_total = 0.0
    if "data" in scope:
        mp = manifest_path()
        if os.path.exists(mp):
            with open(mp) as f:
                m = json.load(f)
            print(f"date: {m['date']}  manifest start: {m['started']}  "
                  f"finish: {m['finished']}  ok={m.get('ok')}")
            data_total = section("Phase A — data ingestion (run_daily.py)", m)

    if "trader" in scope:
        tp = trader_path(date)
        if os.path.exists(tp):
            t = load(date)
            finish_str = t.get("finished") or "(run incomplete)"
            print(f"date: {t['date']}  trader start: {t['started']}  "
                  f"finish: {finish_str}")
            trader_total = section("Phase B — Trader", t)
            if not t.get("in_order", True):
                print("  ⚠️  phases out of canonical order")
            if t.get("finished") is None:
                print("  ⚠️  trader run not closed (no `end` mark yet)")
            if t.get("previous_runs"):
                print(f"  ℹ️  run {t.get('run', len(t['previous_runs']) + 1)} "
                      f"of {t['date']} — {len(t['previous_runs'])} earlier "
                      f"run(s) retained under previous_runs[]")

    if "data+trader" in scope:
        print(f"\n>>> Phase A total: {data_total:.1f}s   "
              f"Phase B total: {trader_total:.2f}s   "
              f"combined: {data_total + trader_total:.1f}s <<<")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_mark = sub.add_parser("mark", help="close the current phase and open `<phase>`")
    p_mark.add_argument("phase", choices=PHASES)

    p_sum = sub.add_parser("summary", help="print a timing summary")
    p_sum.add_argument("--phase", choices=["data", "trader", "data+trader"],
                       default="data+trader")
    p_sum.add_argument("--date", default=None)

    args = ap.parse_args()

    if args.cmd == "mark":
        # Append-only mark: reuse existing phase list if present so the
        # single TradeTimer class stays the source of truth for dedup and
        # `in_order` recompute.
        #
        # EXCEPT when the record on disk is a CLOSED run. A second run of the
        # pipeline on the same day is supported (decision 2026-08-23), and
        # appending its `start` after the previous run's `end` walks the phase
        # list backwards: `in_order` flips False and every phase duration
        # becomes the gap between two different runs. That is not an
        # out-of-order run, it is two runs in one list. Rotate instead — the
        # closed record moves to `previous_runs[]` and the new run starts
        # clean, so both stay readable.
        date = today()
        tp = trader_path(date)
        t = TradeTimer(date=date)      # __init__ carries a closed run aside
        carried = t.previous_runs
        if carried:
            print(f"[time_run] ℹ️  run {len(carried)} of {date} was closed — "
                  f"starting a fresh phase list; the previous run is kept "
                  f"under previous_runs[]")
        elif os.path.exists(tp):
            with open(tp) as f:
                prev = json.load(f)
            t.entries = list(prev.get("phases", []))
            t._last_open = t.entries[-1] if t.entries else None
            t._t0 = time.time()
            # Carry the earlier runs forward. Each `mark` is its own process, so
            # the record we are extending is mid-run and `closed_run_on_disk`
            # correctly declines to rotate it — but it may ALREADY hold runs
            # rotated aside by the `start` mark, and rewriting without them
            # drops run 1 on the second mark of run 2. Found by test, 2026-08-23.
            t.previous_runs = list(prev.get("previous_runs") or [])
            carried = t.previous_runs
        t.mark(args.phase)
        # `end` is special — fingerprint artefacts and set the top-level
        # finished/started fields. Otherwise write a partial record.
        if args.phase == "end":
            rec = t.finish()   # finish() already folds in self.previous_runs
        else:
            order = [e["name"] for e in t.entries]
            rec = {
                "date": date,
                "started": t.entries[0]["started"],
                "finished": t.entries[-1].get("finished"),
                "phases": t.entries,
                "in_order": [PHASES.index(n) for n in order] == sorted(
                    [PHASES.index(n) for n in order]),
            }
            if carried:
                rec["run"] = len(carried) + 1
                rec["previous_runs"] = carried
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(tp, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        print(f"[time_run] mark → {args.phase}  "
              f"(recorded in {os.path.relpath(tp, ROOT)})")

    elif args.cmd == "summary":
        summary(date=args.date, scope=args.phase)


if __name__ == "__main__":
    main()
