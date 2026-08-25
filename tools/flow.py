#!/usr/bin/env python3
"""
flow.py — the flow and conviction legs, rendered for the agents to read.

WHAT THIS STEP DOES AND DELIBERATELY DOES NOT DO
  It reads the two whole-book legs (`flow`, `conviction`) from whichever
  providers `input/config/providers.json` names, and writes them to
  `output/data/flow_<date>.md`.

  It changes **no gate, no cap, no signal and no tag**. Nothing in the Trader's
  card reads this file yet. That is the point: the legs start producing data,
  and the parallel run in `docs/FLOW_FIRST_PROPOSAL.md` Phase 3 gets something
  to score, without a single decision moving on one day of evidence.

  The rotation read remains what ETF gate 1 consults. See Phase 4.

THE SIGNIFICANCE FLOOR IS RENDERED HERE, OWNED ELSEWHERE
  A percentage without a size is noise. Observed 2026-08-20: URA rendered
  "100% bullish" on ONE $84K print, in the same table as GLD's 86% on $131M.
  Rows below the floor are marked `THIN` — not bullish, not bearish, *not
  enough money to constitute an observation*.

  The number lives here as a rendering constant only. When Phase 4 lets a gate
  consult it, it moves to `rules/` where the other bars live, and this constant
  becomes an import. Do not let a rule quietly take up permanent residence in
  a reporting script.

STALENESS
  Both legs are `browser`-ingested, so both carry `max_age_days`. The check
  fires on `read_at` (when you looked), never on `session_date` / `signal_date`
  (what the data describes) — a fortnight-old regime signal read this morning
  is current; this morning's flow read a fortnight ago is not.

Inputs   input/config/providers.json        provider selection, per leg
         input/capture/flow_<date>.md       for browser/file flow providers
         input/capture/conviction_<date>.md
         input/*.csv                        broker export, to mark held names
Output   output/data/flow_<date>.md
         output/data/flow_<date>.md         the file the agents read

Usage    python3 tools/flow.py
         python3 tools/flow.py --list-providers
         python3 tools/flow.py --provider flowsource      # override config
         python3 tools/flow.py --conviction-provider none
"""

import argparse
import csv
import datetime
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import providers                                          # noqa: E402
from providers.contracts import ProviderError             # noqa: E402

INPUT_DIR = os.environ.get("TP_INPUT", os.path.join(ROOT, "input"))
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
CONFIG_PATH = os.path.join(INPUT_DIR, "config", "providers.json")

# See the module docstring. This is a rendering threshold, not yet a rule.
SIGNIFICANCE_FLOOR_USD = 500_000


# ---------------------------------------------------------------- helpers

def money(v):
    if v is None:
        return "—"
    a = abs(v)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim:
            return f"${v / lim:,.1f}{suf}".replace(".0", "", 1)
    return f"${v:,.0f}"


def pct(v):
    return "—" if v is None else f"{v:.0f}%"


def read_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def held_symbols():
    """Bare symbols from every broker CSV in input/. Cheap and deliberately
    dumb — no ticker resolution, no US-twin mapping. Twins arrive with Phase 4;
    pretending to have them now would put a proxy in the report unlabelled."""
    out = set()
    if not os.path.isdir(INPUT_DIR):
        return out
    for fn in sorted(os.listdir(INPUT_DIR)):
        if not fn.lower().endswith(".csv"):
            continue
        try:
            raw = io.open(os.path.join(INPUT_DIR, fn), encoding="utf-8",
                          errors="replace").read().lstrip("﻿")
            for row in csv.DictReader(io.StringIO(raw)):
                for key in row:
                    if key and re.sub(r"\W", "", key).lower() in {"symbol", "ticker"}:
                        s = (row[key] or "").strip().upper()
                        if s and s not in {"TOTALS", "GBP", "USD"}:
                            out.add(s)
                        break
        except Exception:
            continue
    return out


def age_days(read_at):
    if not read_at:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            t = datetime.datetime.strptime(read_at.replace("+00:00", "").strip()[:19], fmt)
            return (datetime.datetime.now() - t).days
        except ValueError:
            continue
    return None


def resolve(leg, override, cfg):
    """(provider|None, name, [notes]) — never raises for an ordinary absence."""
    name = override or (cfg.get(leg) or {}).get("provider") or "none"
    notes = []
    p = providers.get(leg, name)
    if p is None:
        notes.append(f"provider {name!r} not found for leg {leg!r} — "
                     f"installed: {', '.join(providers.names(leg)) or '(none)'}")
        return None, name, notes
    return p, name, notes


def call(p, ctx):
    try:
        return p.load(ctx), []
    except ProviderError as e:
        return None, [f"contract violation: {e}"]
    except Exception as e:                                  # noqa: BLE001
        return None, [f"{p.name} raised {type(e).__name__}: {e}"]


# ---------------------------------------------------------------- render

def render(flow, fl_name, conv, cv_name, held, warnings):
    today = datetime.date.today().isoformat()
    L = [f"# Flow & conviction — {today}", ""]
    L += ["*Whole-book legs, rendered for the agents. **Nothing in the gate cards "
          "reads this file yet** — the rotation read still drives ETF gate 1. "
          "See `docs/FLOW_FIRST_PROPOSAL.md` Phase 4.*", ""]

    # ---- flow -----------------------------------------------------------
    L += ["## Flow", ""]
    if not flow or flow.get("status") == "NONE":
        L += [f"**ABSENT** — provider `{fl_name}`. "
              + ((flow or {}).get("notes") or ["no provider configured"])[0], ""]
    else:
        age = age_days(flow.get("read_at"))
        cap = getattr(providers.get("flow", fl_name), "max_age_days", None)
        stale = (age is not None and cap is not None and age > cap)
        L += [f"**{flow['status']}** · provider `{fl_name}` · session "
              f"**{flow.get('session_date') or '?'}** · read {flow.get('read_at') or '?'}"
              + (f" · ⚠️ **STALE** ({age}d > {cap}d)" if stale else ""), ""]
        m = flow.get("method")
        L += [f"*Method: {m.get('raw') if m else '**unrecorded — do not pool with another capture**'}*", ""]

        mk = flow.get("market")
        if mk:
            L += ["### Market", "",
                  f"**{pct(mk.get('pct_bullish'))} bullish / {pct(mk.get('pct_bearish'))} bearish"
                  f" — {money(mk.get('call_premium_usd'))} calls vs "
                  f"{money(mk.get('put_premium_usd'))} puts"
                  + (f". {mk['label']}.**" if mk.get("label") else ".**"), ""]

        rows = flow.get("tickers") or {}
        if rows:
            L += ["### By ticker", "",
                  f"*`THIN` = under {money(SIGNIFICANCE_FLOOR_USD)} aggregate premium: "
                  f"not bullish, not bearish, not enough money to be an observation.*", "",
                  "| Ticker | Held | Bullish | Calls | Puts | Total | Read |",
                  "|---|---|---|---|---|---|---|"]
            for t, d in sorted(rows.items(),
                               key=lambda kv: -(kv[1].get("premium_usd") or 0)):
                tot = d.get("premium_usd") or 0.0
                if tot < SIGNIFICANCE_FLOOR_USD:
                    read = "`THIN`"
                else:
                    pb = d.get("pct_bullish")
                    read = ("—" if pb is None else
                            "**bullish**" if pb >= 60 else
                            "**bearish**" if pb <= 40 else "mixed")
                L.append(f"| {t} | {'✅' if t in held else ''} | {pct(d.get('pct_bullish'))} "
                         f"| {money(d.get('call_premium_usd'))} | {money(d.get('put_premium_usd'))} "
                         f"| {money(tot)} | {read} |")
            L.append("")
        for n in flow.get("notes") or []:
            L.append(f"- {n}")
        L.append("")

    # ---- conviction ------------------------------------------------------
    L += ["## Conviction", ""]
    if not conv or conv.get("status") == "NONE":
        L += [f"**ABSENT** — provider `{cv_name}`. "
              + ((conv or {}).get("notes") or ["no provider configured"])[0], ""]
    else:
        age = age_days(conv.get("read_at"))
        cap = getattr(providers.get("conviction", cv_name), "max_age_days", None)
        stale = (age is not None and cap is not None and age > cap)
        L += [f"**{conv['status']}** · provider `{cv_name}` · regime "
              f"**{conv.get('regime') or '—'}** · signal "
              f"{conv.get('signal_date') or '?'} · read {conv.get('read_at') or '?'}"
              + (f" · ⚠️ **STALE** ({age}d > {cap}d)" if stale else ""), ""]
        pos = conv.get("positions") or []
        if pos:
            L += ["| Ticker | Weight | Action | Bucket | Held |", "|---|---|---|---|---|"]
            for p in sorted(pos, key=lambda r: -(r.get("weight") or 0)):
                L.append(f"| {p['ticker']} | {p.get('weight') if p.get('weight') is not None else '—'} "
                         f"| {p.get('action') or '—'} | {p.get('bucket') or '—'} "
                         f"| {'✅' if p['ticker'] in held else ''} |")
            L.append("")
        empty = conv.get("empty_sections") or []
        if empty:
            L += [f"**Confirmed empty on the page: {', '.join(empty)}.** "
                  f"An absence of confirmation, never a contrary vote — anything in "
                  f"these sectors can score at most 1-of-3 and must be worded that way.", ""]
        for n in conv.get("notes") or []:
            L.append(f"- {n}")
        L.append("")

    if warnings:
        L += ["## Warnings", ""] + [f"- {w}" for w in warnings] + [""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Render the flow and conviction legs.")
    ap.add_argument("--provider", help="override the configured flow provider")
    ap.add_argument("--conviction-provider", help="override the configured conviction provider")
    ap.add_argument("--session-date", help="ask the flow provider for a specific session")
    ap.add_argument("--out-dir", default=DATA_DIR)
    ap.add_argument("--list-providers", action="store_true")
    a = ap.parse_args()

    if a.list_providers:
        for leg in ("flow", "conviction"):
            print(f"{leg}: {', '.join(providers.names(leg)) or '(none installed)'}")
        for e in providers.errors():
            print(f"  ⚠️  {e}")
        return 0

    warnings = list(providers.errors())
    cfg = read_config()

    fl, fl_name, n1 = resolve("flow", a.provider, cfg)
    cv, cv_name, n2 = resolve("conviction", a.conviction_provider, cfg)
    warnings += n1 + n2

    ctx = {"root": ROOT, "input_dir": INPUT_DIR}
    if a.session_date:
        ctx["session_date"] = a.session_date

    flow = conv = None
    if fl:
        flow, w = call(fl, ctx)
        warnings += w
    if cv:
        conv, w = call(cv, ctx)
        warnings += w

    held = held_symbols()
    text = render(flow, fl_name, conv, cv_name, held, warnings)

    os.makedirs(a.out_dir, exist_ok=True)
    today = datetime.date.today().isoformat()
    dated = os.path.join(a.out_dir, f"flow_{today}.md")
    with open(dated, "w", encoding="utf-8") as f:
        f.write(text)

    fs = (flow or {}).get("status", "NONE")
    cs = (conv or {}).get("status", "NONE")
    print(f"flow={fl_name}:{fs}  conviction={cv_name}:{cs}  "
          f"tickers={len((flow or {}).get('tickers') or {})}")
    for w in warnings:
        print(f"  ⚠️  {w}")
    print(f"Wrote {os.path.relpath(dated, ROOT)}")
    # A configured-but-absent leg is a normal published state, not a failure.
    # Only a broken provider is worth halting the pipeline for.
    return 1 if any("contract violation" in w or "raised" in w for w in warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
