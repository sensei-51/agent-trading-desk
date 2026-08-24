#!/usr/bin/env python3
"""
Fundamentals sheet — the deterministic half of the fundamentals leg of
the Analyst's data ingestion.

WHY THIS EXISTS
  The data-source contract (`docs/DATA_SOURCES.md`) names three sources every
  run must read live: a **fundamentals scorer** (composite /100 + 5 pillars + ACCEL/RECORD),
  a chart / flow platform, and web search. Two of the three have a deterministic
  half that belongs in a script — price/analyst/earnings/ratings in
  `tools/facts.py`, and the fundamentals leg here. The stock card's gates 1
  and 2 (composite ≥ 60 + ACCEL/RECORD; pillar floors CF ≥ 7, Stability ≥ 5,
  Quality ≥ 13) require these numbers and they are the ones the daily run
  historically carried forward across days because there was no batch read.

  A carried-forward score is a worse failure than a missing one: it reads as
  current and quietly passes a gate that should have failed. Scores can change,
  so this script **re-reads live every run** — `output/data/fundamentals_<date>.md`
  always carries today's date in the header and `Source: <provider> (read live
  YYYY-MM-DD)` in the source line — naming the providers that ACTUALLY answered,
  so a run with fallback rows in it says so rather than claiming the primary. Invariant 8 in `docs/SYSTEM_MAP.md` says
  the same thing about all cached figure sources; this file lifts the rule.

SOURCE-AGNOSTIC + PUBLISH-SAFE
  The leg reads whichever **provider** `input/config/providers.json` names:

      {"fundamentals": {"provider": "curated_csv", "fallback": "derived"}}

  Providers are auto-discovered plugin modules under `providers/fundamentals/`
  (and `providers/private/fundamentals/` for paid ones, which is gitignored).
  There is no registry in this file to edit — that is deliberate; see
  `providers/__init__.py` for why discovery is also the privacy mechanism.

  Three ship publicly:

    - `none` (the published default): every roster name returns `status: NONE`
      with no network call, and the gates render `GATE*-INFERRED`. Honest
      missing data, never a fabricated pass. A clone with no subscription stays
      truthful rather than quietly waving names through.

    - `derived`: a composite rebuilt from free Yahoo data on the same pillar
      scale, marked `approx: True`. Calibrated 18 Aug 2026 against 86 curated
      composites — r = 0.88, runs +3.4 points hot. See
      `docs/DERIVED_CALIBRATION_2026-08-18.md`.

    - `example`: a documented template. Copy it to add your own source.

  A provider declares what it can answer, and the gates consult that BEFORE
  they consult its data:

      PROVIDER = {"name": ..., "leg": "fundamentals",
                  "ingestion": "fetch" | "file" | "browser",
                  "supplies": {"score", "pillars", "accel", "record", "eps"},
                  "approx": bool, "private": bool, "max_age_days": int | None}

      def fetch(ticker, ctx) -> dict

  `supplies` is not documentation. A provider that cannot produce an
  earnings-acceleration tag leaves "accel" out, and gate 1 returns
  `GATE1-INFERRED(no-accel/record-from-<name>)` for that clause. Declare it and
  return None instead, and the gate reads the absence as "checked, and this
  company does not accelerate" — a FAIL. Same missing data; one version blames
  the provider and the other blames the company, and only one is true.

  The returned dict:

      {
        "score": int|None,           # composite /100; required when status "OK"
        "grade": str|None,           # composite label, e.g. "Good"
        "pillars": {                 # name -> (n, max, label); None when not OK
          "quality": (20, 30, "Good"), "growth": (20, 20, "Exceptional"),
          "cash_flow": (5, 10, "Good"), "stability": (10, 10, "Exceptional"),
          "valuation": (4, 10, "Mixed"), "ownership": (8, 15, "Good"),
        }|None,
        "accel": bool|None,          # the source's own tag, where it has one
        "record": bool|None,
        "eps_quarterly": [(period, value, growth_yoy|None), ...]|None,
        "revenue_quarterly": [(period, value, growth_yoy|None), ...]|None,
        "status": "OK"|"PARTIAL"|"FAIL"|"NONE"|"FUND-VEHICLE",
        "notes": [str, ...],
        "approx": bool,              # optional per-row override of the declaration
      }

  ACCEL/RECORD: `resolve_accel_record` prefers the source's own tags and only
  derives them from the EPS series when the provider has none. Deriving when a
  tag exists is how the NVDA disagreement of 18 Aug 2026 happened — two
  calculations over two inputs, filed as a vendor false negative when it was
  neither.

STATUS DISCIPLINE
  Every roster name appears in the output exactly once — including the ones
  that failed or returned NONE. `rules/03_DAILY_RUN.md` makes the roster a
  contract of the run; a fundamentals file that drops its failures hands
  the Trader a shorter roster than the one it is judged against. `FAIL`,
  `PARTIAL` and `NONE` rows are listed under a `## Failures and gaps`
  section *and* in the table, because a row in a 60-line table is easy to
  miss.

  `FUND-VEHICLE`: a provider-emitted pre-check that flags the ticker as a
  fund/ETF/basket for which company-level scoring is structurally invalid.
  No HTTP call is made, no fabricated PASS. The Trader routes these rows
  through the **ETF card (E)**, gate 1 from the rotation read per
  `rules/02_SLEEVE_RULES.md:62-66`.

SCORES, NOT GUESSES
  When the source is `none`, every flag is `GATE*-INFERRED` — no fake pass.
  `rules/02_SLEEVE_RULES.md:189` ("if the scorer has no data on a name,
  that is a fail, not a pass") is what this file implements.

Inputs   input/*.csv                     via heartbeat_radar's schema detection
         input/watchlist*.md
         input/tracking/universe.md      only with --include-discovery
         input/config/providers.json     provider selection, per leg
         input/capture/fundamentals_*.csv  for `file`/`browser` providers
Output   output/data/fundamentals_<date>.csv   one row per roster name, carrying
                                               `provider` and `approx` per row
         output/data/fundamentals_latest.md    the file the Trader reads

Usage    python3 tools/fundamentals.py
         python3 tools/fundamentals.py --include-discovery
         python3 tools/fundamentals.py --list-providers      # what is installed
         python3 tools/fundamentals.py --provider derived    # override config
"""

import argparse
import csv
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, ROOT)                      # so `import providers` resolves

import heartbeat_radar as hr  # noqa: E402  — path set above

# Gate-card thresholds. Mirror `rules/02_SLEEVE_RULES.md` lines 44-45 verbatim so
# the readable source maps 1:1 to the rulebook — change one here and change the
# rule there in the same edit, or the gate prefix and the row that say "GATE*"
# will mean slightly different things.
SCORE_FLOOR  = 60   # gate 1: composite score ≥ 60
ACCEL_NEEDED = True # gate 1: ACCEL or RECORD tag required alongside ≥ 60
CF_FLOOR     = 7    # gate 2: Cash Flow pillar ≥ 7/10
STAB_FLOOR   = 5    # gate 2: Stability pillar ≥ 5/10
QUALITY_FLOOR = 13  # gate 2: Quality pillar ≥ 13/30

# Provider selection lives in `input/config/providers.json` (gitignored); the
# committed `.example` ships every leg on `none`, so a fresh clone runs and
# reports INFERRED rather than fabricating a pass.
CONFIG_PATH = os.path.join(ROOT, "input", "config", "providers.json")

# ---------------------------------------------------------------- providers
#
# Sources used to be a hardcoded `ADAPTERS` dict in this file, which meant a
# vendor name was baked into core code and adding a source required editing two
# core files. They are now auto-discovered plugins under `providers/`, with the
# paid ones under the gitignored `providers/private/`. See providers/__init__.py
# for why discovery is also the privacy mechanism.

import providers                                   # noqa: E402 — path set above
from providers.scoring import (is_fund_vehicle,     # noqa: E402
                               derive_accel_record)

def resolve_accel_record(out, provider):
    """(accel, record, basis) for one row.

    Order matters, and it is the fix for a real defect. A provider that
    publishes ACCEL/RECORD tags had them ignored: gate 1 recomputed both from
    the EPS series regardless. Those are two calculations over two inputs and
    they disagree — the single gate-1 false pass in the 18 Aug calibration
    (NVDA) was recorded as a "Curated-side ACCEL/RECORD false negative" and was
    nothing of the kind. The vendor published a tag; this code computed a
    different one. So: use the tag if the provider has one, derive only if it
    does not, and say which happened.

    `basis` is None when neither route is available. That is a GAP, and gate 1
    must render it as INFERRED rather than as a negative verdict about the
    company — "my source cannot answer" and "this company does not accelerate"
    are different claims.
    """
    supplies_tags = provider is not None and provider.supplies("accel")
    if supplies_tags and ("accel" in out or "record" in out):
        return out.get("accel"), out.get("record"), "provider tags"
    supplies_eps = provider is None or provider.supplies("eps")
    if supplies_eps:
        series = out.get("eps_quarterly") or []
        if series:
            a, r = derive_accel_record(series)
            return a, r, "derived from EPS series"
        if provider is not None and not provider.supplies("eps"):
            return None, None, None
        return None, None, "derived from EPS series"
    return None, None, None
# ---------------------------------------------------------------- gate flags

def gate1(adapter_out, provider=None):
    """Composite score ≥ 60 AND ACCEL or RECORD. Returns a single flag token."""
    if adapter_out.get("status") == "NONE":
        return "GATE1-INFERRED"
    if adapter_out.get("status") == "FUND-VEHICLE":
        return "GATE1-N/A"
    score = adapter_out.get("score")
    accel, record, basis = resolve_accel_record(adapter_out, provider)

    # A provider that supplies neither the tags nor an EPS series cannot answer
    # this clause at all. That is a capability gap, not evidence — degrade the
    # one clause and name the provider, rather than returning a FAIL that reads
    # as a judgement about the company. Before capability declarations existed,
    # any such provider produced FAIL(no-ACCEL/RECORD-data) on every name in the
    # book, which is a data gap wearing a quality verdict.
    if basis is None and adapter_out.get("status") in ("OK", "PARTIAL"):
        who = provider.name if provider is not None else "provider"
        return f"GATE1-INFERRED(no-accel/record-from-{who})"

    if score is None:
        return "GATE1-FAIL(no-score)"
    if score < SCORE_FLOOR:
        return f"GATE1-FAIL(score-{score}-lt-{SCORE_FLOOR})"
    # We need ACCEL or RECORD. If the source offers the clause but the data
    # isn't decidable, missing-tag = fail (Safe-failure rule, DATA_SOURCES.md:65).
    accel_or_record = (accel is True) or (record is True)
    if accel is None and record is None:
        return "GATE1-FAIL(no-ACCEL/RECORD-data)"
    if not accel_or_record:
        bits = []
        if accel is False: bits.append("no-ACCEL")
        if record is False: bits.append("no-RECORD")
        return "GATE1-FAIL(" + "+".join(bits) + ")"
    # Proxy-resolution borderline zone (approx providers only, calibrated
    # 18 Aug 2026 against a live curated run — docs/DERIVED_CALIBRATION_*).
    # An approx composite runs ~+3 hot with σ≈9 vs the curated score, so
    # near the floor it cannot discriminate: of five gate-1 false passes in
    # the head-to-head, four sat in the 60-70 single-tag zone. A derived
    # score there is a VERIFY, not a pass — BORDERLINE is not PASS, and the
    # Trader treats it like ⚫ VERIFY. Both tags firing together (ACCEL and
    # RECORD) is stronger evidence and passes from the floor up.
    if adapter_out.get("approx") and score < SCORE_FLOOR + 10 \
            and not (accel is True and record is True):
        return f"GATE1-BORDERLINE(score-{score}-proxy-resolution)"
    return "GATE1-PASS"


def gate2(adapter_out):
    """Pillar floors: Cash Flow ≥ 7/10 AND Stability ≥ 5/10 AND Quality ≥ 13/30.

    A `FUND` vehicle row skips entirely (returned by the caller, not here) —
    ETF card takes gate 1 from the rotation read.
    """
    if adapter_out.get("status") == "NONE":
        return "GATE2-INFERRED"
    if adapter_out.get("status") == "FUND-VEHICLE":
        return "GATE2-N/A"
    p = adapter_out.get("pillars") or {}
    if not p:
        return "GATE2-FAIL(no-pillars)"
    fails = []
    cf = p.get("cash_flow")
    if cf is None or cf[0] < CF_FLOOR:
        fails.append(f"CF-{cf[0] if cf else 'NA'}-lt-{CF_FLOOR}")
    sb = p.get("stability")
    if sb is None or sb[0] < STAB_FLOOR:
        fails.append(f"Stab-{sb[0] if sb else 'NA'}-lt-{STAB_FLOOR}")
    ql = p.get("quality")
    if ql is None or ql[0] < QUALITY_FLOOR:
        fails.append(f"Quality-{ql[0] if ql else 'NA'}-lt-{QUALITY_FLOOR}")
    if fails:
        return "GATE2-FAIL(" + "+".join(fails) + ")"
    # Proxy-resolution borderline (approx providers only, same calibration as
    # gate 1): a proxied pillar within 2 points above its floor is inside the
    # provider's noise band — all three gate-2 false passes in the 18 Aug 2026
    # head-to-head straddled a floor by ≤2. BORDERLINE, not PASS.
    if adapter_out.get("approx"):
        near = []
        for key, floor, label in (("cash_flow", CF_FLOOR, "CF"),
                                  ("stability", STAB_FLOOR, "Stab"),
                                  ("quality", QUALITY_FLOOR, "Quality")):
            val = p.get(key)
            if val is not None and floor <= val[0] < floor + 2:
                near.append(f"{label}-{val[0]}-near-{floor}")
        if near:
            return "GATE2-BORDERLINE(" + "+".join(near) + ")"
    return "GATE2-PASS"


# ---------------------------------------------------------------- assembly

def build_row(entry, provider, fallback=None, ctx=None):
    """Build a fundamentals row for one ticker.

    `provider` and `fallback` are `providers.Provider` instances.

    The primary runs first. If it returns `status: FAIL` (network error,
    rate-limit, layout drift, name absent from an export) AND a fallback was
    configured, the row transparently drops to the fallback and carries
    `approx: true`, so the proxy-resolution BORDERLINE zones (`~` grades,
    GATE*-BORDERLINE near floors) apply automatically — a Trader sees a
    VERIFY, not a fabricated pass.

    FUND-VEHICLE rows do NOT trigger the fallback: providers short-circuit a
    recognised UCITS/ETF wrapper before any network call using the shared
    `providers.scoring._KNOWN_FUND_VEHICLES` set, so the row would not change.

    The row records `provider` — the source that actually answered — because
    the run-level header cannot: a `curated` run with fallback rows in it used
    to print `Source: curated` for the whole file, with the only per-row
    evidence a trailing `~` on the grade string.
    """
    ticker, membership, sector = entry
    used = provider                     # which provider actually answered
    out = provider.fetch(ticker, ctx)
    if fallback is not None and out.get("status") == "FAIL":
        fb = fallback.fetch(ticker, ctx)
        if fb.get("status") in ("OK", "PARTIAL"):
            primary_err = "; ".join(out.get("notes") or []) or "fetch failed"
            fb_notes = list(fb.get("notes") or [])
            fb_notes.insert(
                0,
                f"primary provider {provider.name!r} returned FAIL ({primary_err}); "
                f"fallback {fallback.name!r} succeeded — APPROXIMATE, not curated",
            )
            fb["notes"] = fb_notes
            out, used = fb, fallback
    # `approx` is a property of the provider that answered, so a fallback row
    # inherits the fallback's honesty marker even if the provider itself forgot
    # to set it. A row may still override per-row.
    if "approx" not in out and used.approx:
        out["approx"] = True
    row = {
        "ticker": ticker,
        "membership": membership,
        "sector": sector,
        "score": out.get("score"),
        "grade": out.get("grade"),
        "pillars": out.get("pillars") or {},
        "eps_quarterly": out.get("eps_quarterly"),
        "revenue_quarterly": out.get("revenue_quarterly"),
        "status": out.get("status", "FAIL"),
        "notes": list(out.get("notes") or []),
    }
    accel, record, basis = resolve_accel_record(out, used)
    row["accel"] = accel
    row["record"] = record
    row["provider"] = used.name
    row["approx"] = bool(out.get("approx"))
    if basis == "provider tags":
        row["notes"].append("ACCEL/RECORD read from the source's own tags")

    g1 = gate1(out, used)
    g2 = gate2(out)
    # Strip ACCEL/RECORD from the gate flag set so the caller can render
    # them as dedicated columns. The gate token itself is what `tools/pnl.py`
    # will see, and it is unambiguous (no internal spaces).
    row["flags"] = [g1, g2]
    return row


def fmt(v, dp=2, suffix=""):
    return f"{v:,.{dp}f}{suffix}" if isinstance(v, (int, float)) else "—"


# ---------------------------------------------------------------- rendering

def render_md(rows, provider_name, today, demo, include_discovery):
    ok     = sum(1 for r in rows if r["status"] == "OK")
    part   = sum(1 for r in rows if r["status"] == "PARTIAL")
    fail   = sum(1 for r in rows if r["status"] == "FAIL")
    none_  = sum(1 for r in rows if r["status"] == "NONE")
    fund   = sum(1 for r in rows if r["status"] == "FUND-VEHICLE")
    # The source line is built from the providers that ACTUALLY answered, not
    # from the configured primary. Previously a run with fallback rows in it
    # still printed `Source: <primary>` for the whole file, and the only per-row
    # evidence was a trailing `~` on the grade string. A header that names a
    # source the rows did not all come from is worse than no header.
    source_label = {
        "none":    "no source configured — `input/config/providers.json` is publish-default `none`",
        "derived": "~Yahoo Finance proxy pillars (approximate — free substitute, "
                   "calibrated against a curated scorer 2026-08-18; see "
                   "docs/DERIVED_CALIBRATION_2026-08-18.md)",
    }.get(provider_name, provider_name)

    used = {}
    for r in rows:
        key = r.get("provider") or provider_name
        used[key] = used.get(key, 0) + 1
    if len(used) > 1:
        mix = ", ".join(f"{n} \u00d7 {k}" for k, n in sorted(used.items(), key=lambda kv: -kv[1]))
        source_label = f"{source_label} \u2014 MIXED RUN: {mix}"
    n_approx = sum(1 for r in rows if r.get("approx"))
    if n_approx:
        source_label += (f" \u00b7 {n_approx} of {len(rows)} row(s) are APPROXIMATE "
                         f"(`~`) and carry BORDERLINE zones")

    L = [f"# Fundamentals sheet — {today}", ""]
    if demo:
        L += ["> ⚠️ **DEMO DATA.** No real holdings CSV found; an *.example.csv file is in input/.", ""]
    L += [
        f"**Coverage: {len(rows)} names** — {ok} OK, {part} PARTIAL, {fail} FAIL, {none_} NONE, {fund} FUND-VEHICLE.",
        f"**Source: {source_label} (read live {today}).** "
        "Scores are re-read every run; a cached / carried-forward figure doesn't exist on disk.",
        "",
        "> Gates below are arithmetic — every PASS / FAIL is over the figures the source just returned.",
        " An `INFERRED` flag is not a pass: the `none` provider, a provider that cannot supply a clause,",
        " and the unparseable-acceleration cases all INFER,",
        " *both* INFER, then the Trader decides what to do. **No data is a fail, not a pass** — gate",
        " 1 says composite ≥ 60 + ACCEL/RECORD, and if any of those is `None` then `None ≠ PASS`. ",
        "`N/A` for fund/ETF wrappers — these rows do not score; gate 1 moves to the rotation read (E card).",
        "",
        "| Ticker | Held | Score | Grade | Q | G | CF | Stab | Val | Own | ACCEL | RECORD | G1 | G2 | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (x["membership"] != "HELD", x["ticker"])):
        p = r["pillars"]
        def pl(k):
            v = p.get(k)
            return f"{v[0]}/{v[1]}" if v else "—"

        accel = "✓" if r["accel"] is True else ("✗" if r["accel"] is False else "—")
        record = "✓" if r["record"] is True else ("✗" if r["record"] is False else "—")

        L.append(
            f"| **{r['ticker']}** | {r['membership']} | "
            f"{fmt(r['score'], 0) if r['score'] is not None else '—'} | "
            f"{r['grade'] or '—'} | "
            f"{pl('quality')} | {pl('growth')} | {pl('cash_flow')} | "
            f"{pl('stability')} | {pl('valuation')} | {pl('ownership')} | "
            f"{accel} | {record} | "
            f"{r['flags'][0]} | {r['flags'][1]} | "
            f"{'✅' if r['status']=='OK' else ('⚠️ PARTIAL' if r['status']=='PARTIAL' else ('⛔' if r['status']=='FAIL' else ('⚫ NONE' if r['status']=='NONE' else '🅿️ FUND-VEHICLE'))) } |"
        )

    failed = [r for r in rows if r["status"] == "FAIL"]
    partial = [r for r in rows if r["status"] == "PARTIAL"]
    none_rows = [r for r in rows if r["status"] == "NONE"]
    funds = [r for r in rows if r["status"] == "FUND-VEHICLE"]
    L += ["", "## Failures and gaps", ""]
    if not failed and not partial and not none_rows:
        if funds:
            L.append("No fetch-level failures this run. "
                      f"{len(funds)} roster name(s) were tagged `FUND-VEHICLE` "
                      "and routed to the ETF card — see the table above.")
        else:
            L.append("None — every roster name returned every leg it should have.")
    for r in failed:
        L.append(f"- ⛔ **{r['ticker']}** ({r['membership']}) — {'; '.join(r['notes'])}. "
                 "**Check this name live before writing its call.**")
    for r in partial:
        L.append(f"- ⚠️ **{r['ticker']}** ({r['membership']}) — {'; '.join(r['notes'])}.")
    for r in none_rows:
        L.append(f"- ⚫ **{r['ticker']}** ({r['membership']}) — {'; '.join(r['notes'])}.")
    if funds:
        L += ["",
               "**Fund / ETF wrappers (no per-ticker Curated page):**",
               ", ".join(f"**{r['ticker']}**" for r in funds) +
               " — routed through the E card; gate 1 lives in the rotation read."]


    if not include_discovery:
        L += ["", "*Discovery names excluded — they are triaged from the radar, not "
              "evaluated. Run with `--include-discovery` to pull them too.*"]
    L += ["", f"*Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} by "
          "`tools/fundamentals.py`. " "Not financial advice — see `DISCLAIMER.md`.*"]
    return "\n".join(L)


# `provider` and `approx` are in the CSV deliberately. Before they were, a
# consumer reading this file could not tell a curated row from a fallback row
# except by noticing a trailing `~` inside the free-text `grade` string — which
# is not something a parser should have to do, and not something a human
# scanning a column would spot.
CSV_COLS = ["ticker", "membership", "sector", "provider", "approx",
            "score", "grade", "accel", "record",
            "quality_n", "quality_max", "growth_n", "growth_max", "cash_flow_n",
            "cash_flow_max", "stability_n", "stability_max", "valuation_n",
            "valuation_max", "ownership_n", "ownership_max", "gate1", "gate2",
            "status", "notes"]


# ---------------------------------------------------------------- config + roster

def load_config(override):
    """Resolve the fundamentals leg's provider pair.

    Returns `(primary Provider, fallback Provider|None)`, or `(None, None)` on
    a configuration error that must halt the run.

    Reads `input/config/providers.json`:

        {"fundamentals": {"provider": "curated_csv", "fallback": "derived"}}

    CLI `--provider` overrides the primary only.

    Four validation rules, each of which exists for a reason:

      1. an unknown name halts, and names the alternatives;
      2. `fallback == primary` becomes a no-op rather than recursing;
      3. `fallback: "none"` is HARD-REJECTED — a primary failure must never
         silently fabricate data, and "none" here would mean exactly that;
      4. a malformed config halts rather than defaulting, because a default
         chosen by an error is a default nobody decided.
    """
    primary = override
    fallback = None
    fb_raw = None

    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                leg = (json.load(f).get("fundamentals") or {})
            if not primary:
                primary = leg.get("provider", "none")
            fb_raw = leg.get("fallback")
        elif not primary:
            primary = "none"              # missing config => publish-safe default
        if fb_raw:
            fallback = str(fb_raw).strip() or None
    except json.JSONDecodeError as e:
        print(f"ERROR: {CONFIG_PATH} is not valid JSON: {e}", file=sys.stderr)
        return None, None

    for errmsg in providers.errors():
        print(f"WARNING: provider discovery — {errmsg}", file=sys.stderr)

    known = providers.names("fundamentals")
    resolved = {}
    for tag, name in (("primary", primary), ("fallback", fallback)):
        if name is None:
            resolved[tag] = None
            continue
        p = providers.get("fundamentals", name)
        if p is None:
            print(f"ERROR: {tag} provider {name!r} not found. "
                  f"choose from: {known}", file=sys.stderr)
            return None, None
        resolved[tag] = p

    if fallback == primary:
        resolved["fallback"] = None          # no-op, never recurse
    if fallback == "none":
        print("ERROR: fallback 'none' is not allowed — a primary failure must "
              "not silently fabricate data. Use null to disable, or 'derived' "
              "to fall back to the open proxy.", file=sys.stderr)
        return None, None
    return resolved["primary"], resolved["fallback"]


def load_membership(include_discovery):
    """Roster = holdings + watchlists, matching `tools/facts.py`. Discovery is
    off by default — pulling eight legs on ~30 universe names that will mostly
    screen themselves out silently is exactly the spend this script exists to
    avoid."""
    smap = hr.load_sector_map()
    seen, out = set(), []
    held, skipped, detections, demo = hr.load_roster(smap=smap)
    for tk, sector, sym, basis in held:
        if tk not in seen:
            seen.add(tk)
            out.append((tk, "HELD", sector))
    for tk, src, spec in hr.load_watchlists(smap=smap):
        if tk not in seen:
            seen.add(tk)
            out.append((tk, "SPECULATIVE" if spec else "WATCHLIST",
                        smap.get(tk, "Unclassified")))
    if include_discovery:
        for cells in hr.md_table_rows(os.path.join(hr.INPUT_DIR, "tracking", "universe.md")):
            if len(cells) >= 2 and cells[0] not in seen and cells[0].isupper():
                seen.add(cells[0])
                out.append((cells[0], "DISCOVERY", smap.get(cells[0], cells[1])))
    return out, skipped, detections, demo


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-discovery", action="store_true",
                    help="also pull the discovery universe (off by default)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out-dir", default=os.path.join(hr.OUTPUT_DIR, "data"))
    ap.add_argument("--provider", "--adapter", dest="provider",
                    help="override the configured fundamentals provider "
                         "(unknown value halts)")
    ap.add_argument("--list-providers", action="store_true",
                    help="print discovered providers for every leg and exit")
    a = ap.parse_args()

    if a.list_providers:
        for leg in ("fundamentals", "flow", "conviction"):
            for name in providers.names(leg):
                pr = providers.get(leg, name)
                tag = " [private]" if pr.private else ""
                approx = " ~approx" if pr.approx else ""
                print(f"{leg:14} {name:14} {pr.ingestion:8}{approx}{tag}  "
                      f"supplies: {sorted(pr.supplies_set) or '—'}")
        for e in providers.errors():
            print(f"  ERROR {e}", file=sys.stderr)
        return 0

    provider, fallback = load_config(a.provider)
    if provider is None:
        return 1
    provider_name = provider.name
    fallback_name = fallback.name if fallback else None
    ctx = {"input_dir": hr.INPUT_DIR, "output_dir": hr.OUTPUT_DIR,
           "today": datetime.date.today().isoformat()}

    members, skipped, detections, demo = load_membership(a.include_discovery)
    if not members:
        print("No roster found. Expected holdings CSVs in input/ "
              "or watchlists matching input/watchlist*.md.", file=sys.stderr)
        return 1
    print(f"Roster: {len(members)} names "
          f"({sum(1 for m in members if m[1] == 'HELD')} held). "
          f"Provider: {provider_name} ({provider.ingestion}"
          + (", approx" if provider.approx else "") + ")"
      + (f" · fallback: {fallback_name} on per-ticker FAIL"
         if fallback_name else " · no fallback"))
    for base, detail in detections:
        print(f"  \u00b7 {base}: {detail}")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(
            lambda e: build_row(e, provider, fallback, ctx), members))

    os.makedirs(a.out_dir, exist_ok=True)
    today = datetime.date.today().isoformat()

    csv_path = os.path.join(a.out_dir, f"fundamentals_{today}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            p = r["pillars"]
            flat = {
                "ticker": r["ticker"], "membership": r["membership"], "sector": r["sector"],
                "provider": r.get("provider"), "approx": r.get("approx"),
                "score": r["score"], "grade": r["grade"], "accel": r["accel"], "record": r["record"],
                "quality_n": (p.get("quality") or (None,))[0],
                "quality_max": (p.get("quality") or (None, None))[1],
                "growth_n": (p.get("growth") or (None,))[0],
                "growth_max": (p.get("growth") or (None, None))[1],
                "cash_flow_n": (p.get("cash_flow") or (None,))[0],
                "cash_flow_max": (p.get("cash_flow") or (None, None))[1],
                "stability_n": (p.get("stability") or (None,))[0],
                "stability_max": (p.get("stability") or (None, None))[1],
                "valuation_n": (p.get("valuation") or (None,))[0],
                "valuation_max": (p.get("valuation") or (None, None))[1],
                "ownership_n": (p.get("ownership") or (None,))[0],
                "ownership_max": (p.get("ownership") or (None, None))[1],
                "gate1": r["flags"][0], "gate2": r["flags"][1],
                "status": r["status"], "notes": "; ".join(r["notes"]),
            }
            w.writerow(flat)

    md = render_md(rows, provider_name, today, demo, a.include_discovery)
    for p in (os.path.join(a.out_dir, f"fundamentals_{today}.md"),
              os.path.join(a.out_dir, "fundamentals_latest.md")):
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)

    fail = sum(1 for r in rows if r["status"] == "FAIL")
    print(f"Wrote {csv_path}")
    print(f"Wrote {os.path.join(a.out_dir, 'fundamentals_latest.md')}")
    if fail:
        print(f"⛔ {fail} name(s) failed and are listed under FAILURES \u2014 "
              "check these live before writing their calls.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
