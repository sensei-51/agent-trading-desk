#!/usr/bin/env python3
"""
checks.py — the consolidated assertion pass for the daily run.

One file, many small checks, instead of ten single-check scripts. Each check
is a named function returning (status, message); the run prints a table and
exits non-zero if anything FAILed. `tools/run_daily.py` calls `--pre` before
the deterministic legs and `--post` after them; `--publish` is the pre-push
leak sweep for the public-repo move.

WHY ONE FILE. docs/PROBLEMS_AND_SOLUTIONS.md (2026-08-18) proposed
index_bloc_check.py, cap_check.py, nav_check.py, conviction_source_check.py
and friends as separate scripts. Each is a ~15-line assertion; ten entry
points is ten places to forget to run and ten more names in the system map.
This file replaces them as subcommands of one pass (audit decision,
2026-08-18).

BASIS DECISION (2026-08-18, recorded in CONFIG.md §3). The bloc ceiling and
the cap warnings here are computed on the broker's own sterling **market
value** per line ("Market Value £") — always present in the export,
unambiguous, and it tracks current exposure, which is what a concentration
rail guards. The prior "GBP at recorded book cost" wording was uncomputable
from the export (book cost ships in native currency) and produced two
irreconcilable manual readings of the same rail (33.3% vs 24.7% on the same
day). Order-ticket sizing for a NEW entry still uses native-currency cost
per CONFIG §3 — that rule is about funding a ticket, this one is about
concentration.

Checks
  --pre      providers on disk satisfy the contract, captures are inside their
             declared max age, provider config resolves; sector-map hygiene
             (duplicate rows; bare/.L collisions; HELD names with no row)
  --post     ticker identity (every held line's fetched currency matches its
             broker row — see check_ticker_identity),
             bloc ceiling ≤ 25% NAV per sector (warn ≥ 90% of cap),
             per-line ≥ 90% of the 5% cap surfaced,
             xray_<date> NAV == broker CSV sum,
             radar age (machine verdict: FRESH / STALE(n))
             status-table honesty (✅ on an absent leg = fail),
             ledger or pending file touched for today's evaluation
  --publish  leak sweep: real NAV / position-value strings anywhere outside
             input/ and output/.state/; gitignore sanity (no inline comment
             after a negation; node_modules covered)

Usage    python3 tools/checks.py --pre
         python3 tools/checks.py --post
         python3 tools/checks.py --publish
         python3 tools/checks.py            # pre + post

Standard library only. Exit 0 = all OK/WARN, 1 = at least one FAIL.
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, ROOT)
import heartbeat_radar as hr  # noqa: E402 — path set above
import providers              # noqa: E402

INPUT_DIR = os.environ.get("TP_INPUT", os.path.join(ROOT, "input"))
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))

BLOC_CAP_PCT = 25.0        # per-sector ceiling, % NAV (CONFIG §2)
LINE_CAP_PCT = 5.0         # per-line cap, % NAV (CONFIG §2)

# Sectors that are cash, not risk (2026-08-23). UK T-Bills sat in `Bonds` for one
# afternoon and immediately pushed that bloc to 24.1% of a 25% ceiling while each
# individual bill tripped the 5% line cap — three WARNs describing no risk at all.
#
# Both caps exist to bound CONCENTRATION: how much of the book dies if one sector
# or one name goes wrong. A three-week gilt does not go wrong in that sense, so
# counting it as a bloc reports danger where there is none, and — worse — leaves
# less apparent headroom for the positions that ARE at risk.
#
# Cash stays IN NAV. It is real money and `check_xray_nav` reconciles the total
# against the broker sum; removing it there would break that check and quietly
# shrink every percentage in the book. It is excluded from the two concentration
# gates only.
CASH_SECTORS = {"Cash"}
WARN_AT = 0.90             # warn at 90% of a cap
RADAR_STALE_DAYS = 3       # trading days before the technical leg is stale

OK, WARN, FAIL, SKIP = "OK", "WARN", "FAIL", "SKIP"


# ---------------------------------------------------------------- shared

def load_holdings():
    """[(symbol, value_gbp, sector)] + total, from the broker CSVs.

    Calls the SAME reader tools/xray.py does — hr.find_sterling_column and
    hr.parse_pounds — so the two cannot disagree on membership. This used to be a
    hand-copied version matching only "market value" headers and only cells carrying
    an explicit £, which is ii's format. AJ Bell writes `Value (£)` with bare numeric
    cells, so its file was skipped here and in the x-ray both, and check_xray_nav
    compared a blind sum against a blind NAV and reported OK while a whole
    account was missing.
    Mirroring by duplication is what allowed that; mirroring by call is why it cannot
    recur. Files reporting no usable value column are named, not silently dropped.
    """
    files, _ = hr.discover_holdings_files()
    smap = hr.load_sector_map()
    rows, unreadable = [], []
    for path in files:
        data = hr.read_csv_rows(path)
        if not data:
            continue
        heads = list(data[0].keys())
        tkcol = hr.pick_column(heads, hr.TICKER_HEADERS)
        vcol, native = hr.find_sterling_column(heads)
        if not tkcol or not vcol:
            unreadable.append(os.path.basename(path))
            continue
        for row in data:
            sym = (row.get(tkcol) or "").strip().upper()
            if not sym:
                continue  # cash lines carry a value and no ticker
            val, sterling = hr.parse_pounds(row.get(vcol))
            if val is None or not sterling:
                continue
            sec = hr.map_sector(sym, smap) or "Unclassified"
            rows.append((sym, val, sec))
    return rows, sum(v for _, v, _ in rows), unreadable


def today():
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------- pre checks

def check_sector_map_dupes():
    path = os.path.join(INPUT_DIR, "tracking", "sector_map.md")
    if not os.path.exists(path):
        return FAIL, "sector_map.md missing"
    seen, dupes = {}, []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\|\s*([A-Z0-9.\-]+)\s*\|\s*([A-Za-z]+)\s*\|\s*$", line)
        if not m:
            continue
        t, s = m.group(1), m.group(2)
        if t in seen and seen[t] == s:
            dupes.append(t)
        seen[t] = s
    if dupes:
        return WARN, f"duplicate identical rows: {', '.join(sorted(set(dupes)))}"
    return OK, f"{len(seen)} mappings, no duplicate rows"


def check_sector_map_ambiguous():
    """A symbol listed in BOTH bare and suffixed form makes the map unable to answer
    the question it exists to answer, and the two forms are routinely different
    securities on different exchanges.

    This is the check that would have caught the 16 Aug 2026 GIGB report. The map
    carried `GIGB` and `GIGB.L`; resolve_ticker took the bare form because it was
    tested first; bare GIGB is a live US investment-grade BOND ETF, so the radar
    screened a $45 bond fund against a £50 mining ETF's exit line and printed a SELL
    on a position that was 5% above its rising 150-day. Nothing 404'd, so the
    ALT_FORM retry — which only ever fired on a fetch failure — never ran.

    FAIL rather than WARN: the resolver now breaks the tie on the broker row's
    currency and the feed check catches what slips past, but both are backstops. A
    map that contradicts itself is the defect, and it costs one line to fix.
    """
    path = os.path.join(INPUT_DIR, "tracking", "sector_map.md")
    if not os.path.exists(path):
        return FAIL, "sector_map.md missing"
    smap = hr.load_sector_map()
    # ANY suffix, not just .L (2026-08-25). This read `t + ".L" in smap` while
    # resolve_ticker read the same two forms, so the check covered exactly what
    # resolution could see. Both now honour whatever suffix the map carries, and a
    # check narrower than the resolver it guards is the shape of the original bug:
    # `NEO` and `NEO.TO` sat in the shipped map reporting a clean pass, and the
    # radar screened NeoGenomics under a rare-earth thesis on the strength of it.
    pairs = sorted((t, hr.map_form(t, smap)) for t in smap
                   if "." not in t and hr.map_form(t, smap))
    if pairs:
        return FAIL, ("sector_map.md lists both forms of: "
                      + ", ".join(f"{t}/{s}" for t, s in pairs)
                      + " — keep only the Yahoo ticker you actually hold, or the "
                        "radar can screen the wrong security under the right symbol")
    return OK, f"no bare/suffixed collisions across {len(smap)} mappings"


def check_ticker_identity():
    """Every screened holding's fetched currency agreed with its broker row.

    Reads output/.state/ticker_resolution.json, which heartbeat_radar.py writes at the
    end of a run. The assertion itself has to happen where the feed is; this file is
    offline by design, so it reads the verdict rather than re-fetching 28 series.

    A missing manifest is a WARN, not a SKIP: it means either no radar has run since
    this check shipped, or the run died before writing it. Neither is evidence of
    agreement, and "no news" must not read as good news for a check about whether the
    prices under a position's name are that position's prices.
    """
    path = os.path.join(OUTPUT_DIR, ".state", "ticker_resolution.json")
    if not os.path.exists(path):
        return WARN, ("no ticker_resolution.json — run the radar; until then no "
                      "holding's ticker identity has been verified against the feed")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except ValueError as e:
        return FAIL, f"ticker_resolution.json does not parse: {e}"
    bad = d.get("mismatched") or []
    if bad:
        return FAIL, ("fetched currency disagrees with the broker row (the radar is "
                      "very likely screening a different security): "
                      + "; ".join(f"{b['ticker']} feed={b['fetched_currency']} "
                                  f"broker={b['expected_currency']}" for b in bad)
                      + " — set the correct Yahoo ticker in sector_map.md")
    res = d.get("resolution") or []
    ver = [r for r in res if r.get("verdict") == "VERIFIED"]
    unchecked = [r["ticker"] for r in res if r.get("verdict") == "UNCHECKED"]
    corr = d.get("corrected") or []
    note = f"{len(ver)}/{len(res)} verified against the broker row"
    if corr:
        note += " (" + ", ".join(f"{c['from']}→{c['to']}" for c in corr) + " corrected)"
    if unchecked:
        # Watchlist and discovery names have no broker row, so they have no currency
        # to assert against. Expected, and worth naming rather than hiding in a count.
        note += f"; {len(unchecked)} non-held name(s) have no broker row to check"
    if d.get("date") != today():
        return WARN, f"manifest is from {d.get('date')}, not today — {note}"
    return OK, note


def check_brokers_readable():
    """Every broker CSV in input/ contributed to the NAV, or is named here.

    The NAV-consistency check cannot catch a whole file being skipped: it compares the
    x-ray's NAV against a sum built by the same reader, so a file neither of them can
    read is simply absent from both sides and they agree. That is how AJ Bell.csv —
    header `Value (£)` rather than ii's `Market Value £` — passed unnoticed
    on 2026-08-23. FAIL rather than WARN: a broker export sitting in input/ and
    contributing nothing means every percentage of NAV in the run is computed on the
    wrong denominator, which is a sizing error in every gate card downstream.
    """
    files, _ = hr.discover_holdings_files()
    if not files:
        return SKIP, "no broker CSVs in input/"
    rows, total, unreadable = load_holdings()
    if unreadable:
        return FAIL, ("broker CSV present but contributing £0 to NAV — no usable "
                      "per-line value column: " + ", ".join(unreadable)
                      + ". Every % of NAV this run is computed on the wrong "
                      "denominator until the header is recognised in "
                      "hr.find_sterling_column().")
    return OK, (f"all {len(files)} broker CSV(s) read — {len(rows)} priced lines, "
                f"£{total:,.0f}")


def check_held_classified():
    rows, _, _ = load_holdings()
    missing = sorted({s for s, _, sec in rows if sec == "Unclassified"})
    if missing:
        return FAIL, ("HELD with no sector_map row (weights understated): "
                      + ", ".join(missing))
    return OK, f"all {len(rows)} held names classified"


def check_providers_discover():
    """Every provider on disk satisfies the contract.

    Discovery returns errors rather than raising, so one malformed third-party
    provider cannot kill a run — which is right, but it means nothing surfaces
    the breakage unless something asks. This asks. A provider that fails to
    import is a bug in that provider; a run that dies because of it would be a
    bug in the loader.
    """
    errs = providers.errors()
    if errs:
        return FAIL, "malformed provider(s): " + "; ".join(errs)
    counts = []
    for leg in ("fundamentals", "flow", "conviction"):
        counts.append(f"{leg} {len(providers.names(leg))}")
    priv = providers.private_providers()
    tail = f"; {len(priv)} private" if priv else ""
    return OK, "all providers valid — " + ", ".join(counts) + tail


def check_capture_freshness():
    """`file` and `browser` providers are quoting a capture no older than they
    declared.

    This is the staleness gate that makes browser-mode ingestion safe to rely
    on. A capture nobody refreshed is indistinguishable from a live read once
    it is in the report — which is the exact failure `check_status_honesty`
    exists to catch downstream, caught here at the source instead.
    """
    cap_dir = os.path.join(INPUT_DIR, "capture")
    stale, fresh, missing = [], [], []
    for leg in ("fundamentals", "flow", "conviction"):
        name = _configured_provider(leg)
        if not name or name == "none":
            continue
        p = providers.get(leg, name)
        if p is None or p.ingestion not in ("file", "browser"):
            continue
        cands = sorted(glob.glob(os.path.join(cap_dir, f"{leg}_*")))
        if not cands:
            missing.append(f"{leg}/{name}")
            continue
        newest = cands[-1]
        age_d = (datetime.datetime.now()
                 - datetime.datetime.fromtimestamp(os.path.getmtime(newest))).days
        label = f"{leg}/{name}: {os.path.basename(newest)} {age_d}d old"
        (stale if age_d > (p.max_age_days or 10**6) else fresh).append(
            label + (f" (max {p.max_age_days}d)" if age_d > (p.max_age_days or 10**6) else ""))
    if missing:
        return FAIL, ("configured provider(s) with no capture file in input/capture/: "
                      + ", ".join(missing) + " — the leg cannot be read live")
    if stale:
        return FAIL, "capture(s) past their declared max age: " + "; ".join(stale)
    if not fresh:
        return SKIP, "no file/browser providers configured"
    return OK, "captures fresh — " + "; ".join(fresh)


def _configured_provider(leg):
    """Provider name configured for `leg`, or None."""
    path = os.path.join(INPUT_DIR, "config", "providers.json")
    if not os.path.exists(path):
        return None
    try:
        return (json.load(open(path, encoding="utf-8")).get(leg) or {}).get("provider")
    except ValueError:
        return None


def check_no_private_providers():
    """PUBLISH GATE. No provider declaring `private: True` may exist in a tree
    about to be published, and no capture data may accompany it.

    Structural, not a string search. A grep for vendor names passes the moment
    someone writes "the paid provider" in a docstring; a check on the
    declaration cannot be talked around. The vendor-name sweep below is kept as
    a backstop for prose, in that order of trust.
    """
    priv = providers.private_providers()
    cap = os.path.join(INPUT_DIR, "capture")
    cap_files = [f for f in (os.listdir(cap) if os.path.isdir(cap) else [])
                 if not f.startswith(".")]
    if priv or cap_files:
        bits = []
        if priv:
            bits.append("private provider(s): " + ", ".join(p.path for p in priv))
        if cap_files:
            bits.append(f"{len(cap_files)} capture file(s) in input/capture/")
        return FAIL, ("; ".join(bits) + " — this tree is the PRIVATE one. "
                      "Publish with `python3 tools/publish.py --to <dir>`, which "
                      "excludes both, and run --publish inside that tree.")
    return OK, "no private providers and no capture data present"


def check_provider_config():
    """Every configured leg names a provider that exists, and the fallback rule
    holds.

    Validated against the live registry rather than a hardcoded name list — the
    old `KNOWN_ADAPTERS = {"none","curated","derived"}` had to be edited by hand
    every time a source was added, which is exactly the kind of second place to
    remember that the plugin design exists to remove.
    """
    new = os.path.join(INPUT_DIR, "config", "providers.json")
    if not os.path.exists(new):
        return WARN, ("no providers.json — every leg defaults to 'none' "
                      "(gates INFERRED, flow and conviction ABSENT)")
    bits, problems = [], []
    for leg in ("fundamentals", "flow", "conviction"):
        name = _configured_provider(leg) or "none"
        p = providers.get(leg, name)
        if p is None:
            problems.append(f"{leg}: provider {name!r} not found "
                            f"(have {providers.names(leg)})")
            continue
        bits.append(f"{leg}={name}" + ("~" if p.approx else ""))
    # fallback: null disables; 'none' is rejected — a primary failure must not
    # silently fabricate data.
    if os.path.exists(new):
        try:
            cfg = json.load(open(new, encoding="utf-8"))
        except ValueError as e:
            return FAIL, f"providers.json does not parse: {e}"
        for leg in ("fundamentals", "flow", "conviction"):
            fb = (cfg.get(leg) or {}).get("fallback")
            if fb == "none":
                problems.append(f"{leg}: fallback 'none' is not allowed — use null")
            elif fb and providers.get(leg, fb) is None:
                problems.append(f"{leg}: fallback {fb!r} not found")
    if problems:
        return FAIL, "; ".join(problems)
    return OK, " · ".join(bits)


# ---------------------------------------------------------------- post checks

def check_bloc_ceiling():
    rows, total, _ = load_holdings()
    if not total:
        return SKIP, "no holdings"
    by_sec = {}
    for _, v, sec in rows:
        if sec in CASH_SECTORS:
            continue
        by_sec[sec] = by_sec.get(sec, 0) + v
    breaches, warns = [], []
    for sec, v in sorted(by_sec.items(), key=lambda kv: -kv[1]):
        p = v / total * 100
        if p > BLOC_CAP_PCT:
            breaches.append(f"{sec} £{v:,.0f} = {p:.1f}%")
        elif p >= BLOC_CAP_PCT * WARN_AT:
            warns.append(f"{sec} {p:.1f}%")
    if breaches:
        return FAIL, (f"bloc ceiling {BLOC_CAP_PCT:.0f}% NAV breached (market value £): "
                      + "; ".join(breaches))
    if warns:
        return WARN, (f"within 10% of the {BLOC_CAP_PCT:.0f}% bloc ceiling: "
                      + "; ".join(warns))
    return OK, (f"all sector blocs under {BLOC_CAP_PCT:.0f}% NAV "
                f"(basis: market value £; cash excluded)")


def check_line_caps():
    rows, total, _ = load_holdings()
    if not total:
        return SKIP, "no holdings"
    cap = total * LINE_CAP_PCT / 100
    hot = [f"{s} £{v:,.0f} ({v / total * 100:.1f}%)"
           for s, v, sec in sorted(rows, key=lambda r: -r[1])
           if v >= cap * WARN_AT and sec not in CASH_SECTORS]
    if hot:
        return WARN, (f"at/above 90% of the {LINE_CAP_PCT:.0f}% line cap "
                      f"(market value £; grandfathered lines included): " + "; ".join(hot))
    return OK, f"no risk line at 90% of the {LINE_CAP_PCT:.0f}% cap (cash excluded)"


def check_nav_consistency():
    _, total, _ = load_holdings()
    path = os.path.join(OUTPUT_DIR, "data", f"xray_{today()}.md")
    if not os.path.exists(path):
        return SKIP, f"no xray_{today()}.md"
    m = re.search(r"NAV £([\d,]+)", open(path, encoding="utf-8").read())
    if not m:
        return FAIL, f"xray_{today()}.md carries no NAV line"
    xnav = float(m.group(1).replace(",", ""))
    if abs(xnav - total) > max(1.0, total * 0.001):
        return FAIL, (f"xray NAV £{xnav:,.0f} ≠ broker CSV sum £{total:,.0f} "
                      f"— stale xray or changed export")
    return OK, f"xray NAV £{xnav:,.0f} matches broker CSV sum"


def radar_verdict():
    """(verdict, detail) — the machine-stamped radar age the Trader must quote."""
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "radar", "Heartbeat_Radar_*.md")))
    if not files:
        return "MISSING", "no radar file"
    newest = files[-1]
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(newest))
    fdate = datetime.date.fromisoformat(m.group(1)) if m else None
    body = open(newest, encoding="utf-8").read()
    b = re.search(r"Newest bar in data:\s*\*{0,2}(\d{4}-\d{2}-\d{2})", body)
    bar = b.group(1) if b else "unknown"
    tdy = datetime.date.today()
    # trading-day distance (weekends don't count)
    age = 0
    if fdate:
        d = fdate
        while d < tdy:
            d += datetime.timedelta(days=1)
            if d.weekday() < 5:
                age += 1
    verdict = "FRESH" if age < RADAR_STALE_DAYS else f"STALE({age}td)"
    return verdict, (f"file {os.path.basename(newest)}, newest bar {bar}, "
                     f"{age} trading day(s) old")


def check_radar_age():
    verdict, detail = radar_verdict()
    if verdict == "MISSING":
        return FAIL, detail
    if verdict.startswith("STALE"):
        return WARN, f"{verdict} — {detail} (evaluation must carry the caveat)"
    return OK, f"{verdict} — {detail} (evaluation must NOT claim staleness)"


def check_radar_snapshot():
    """The dated numeric snapshot exists and covers the run (backlog item 4).

    WARN, never FAIL, in every branch. Nothing consumes this file yet — item 3's
    delta tooling is the consumer and does not exist. A retention file that could
    stop a run would be the item-1 trap rebuilt: a check with a failing state and
    no deliverable behind it.

    But it must not lapse silently either. The whole value of a snapshot is the
    *series*; a gap is only discoverable later, when a delta reaches back for a
    day that was never written and the answer is a shrug.
    """
    d = os.path.join(OUTPUT_DIR, ".state")
    path = os.path.join(d, f"radar_snapshot_{today()}.json")
    if not os.path.exists(path):
        have = sorted(f for f in os.listdir(d) if f.startswith("radar_snapshot_")) \
            if os.path.isdir(d) else []
        return WARN, (f"no radar_snapshot_{today()}.json — today's numbers survive "
                      f"only as prose in the radar markdown"
                      + (f" (latest on disk: {have[-1]})" if have else
                         " (none on disk at all)"))
    try:
        snap = json.load(open(path, encoding="utf-8"))
    except ValueError as e:
        return WARN, f"radar_snapshot_{today()}.json does not parse: {e}"
    if snap.get("date") != today():
        return WARN, (f"radar_snapshot_{today()}.json carries date "
                      f"{snap.get('date')!r} — do not compare it")
    n = len(snap.get("tickers") or {})
    g = sum(len(v) for v in (snap.get("gauges") or {}).values())
    kept = len([f for f in os.listdir(d)
                if re.fullmatch(r"radar_snapshot_\d{4}-\d{2}-\d{2}\.json", f)])
    if not n:
        return WARN, "radar snapshot is present but holds no tickers"
    return OK, (f"{n} tickers · {g} gauge reads · {kept} day(s) retained "
                f"({'delta-capable' if kept > 1 else 'first day — no delta yet'})")


def check_status_honesty():
    """A green check on an absent leg is the 'silent gap' DATA_SOURCES rule 3
    prohibits — observed 2026-08-18: 'conviction ✅ (none — no feed)'."""
    hits = []
    for path in (os.path.join(OUTPUT_DIR, f"evaluation_{today()}.md"),):
        if not os.path.exists(path):
            continue
        body = open(path, encoding="utf-8").read()
        for m in re.finditer(r"(\w[\w\s-]{0,24})✅\s*\(\s*(?:none|absent|no)\b[^)]*\)",
                             body, re.I):
            hits.append(m.group(0).strip())
        break
    if hits:
        return FAIL, ("absent leg rendered as ✅ (must be ⚫ ABSENT): "
                      + " · ".join(sorted(set(hits))))
    return OK, "no ✅-on-absent-leg in the current evaluation"


# A universe that shrinks this much between runs is reported. 10% is roughly
# three names on a ~120-name roster — below a normal week's watchlist churn,
# above the noise of one name being retired.
UNIVERSE_DROP_WARN = 0.10
UNIVERSE_DROP_FAIL = 0.25
TOMBSTONE = "<!-- LOST:"


def check_universe_size():
    """Today's screened universe against the last run's.

    WHY THIS EXISTS. `engine/heartbeat_radar.py:load_watchlists` swallows every
    exception per file and returns whatever it managed to parse. A truncated or
    malformed `input/watchlist.md` therefore shrinks the universe silently:
    measured 2026-08-23, a half-truncated file took the watchlist leg from 87
    candidates to 45, and a garbage file to 0. Nothing downstream noticed —
    coverage reports N/N against the *shrunken* roster, so the report is
    internally consistent, plausible, and missing names nobody asked it to drop.

    That is the same signature as the ledger outage (docs/BACKLOG.md item 20):
    a parse failure indistinguishable from a real empty result. The fix there
    was to make "could not read it" louder than "found nothing". Here the parse
    is per-file and best-effort by design, so the guard is a magnitude check
    instead — a universe that shrinks sharply between runs is either a real
    watchlist edit or a broken parse, and both deserve a human look.
    """
    snaps = sorted(glob.glob(os.path.join(OUTPUT_DIR, ".state",
                                          "radar_snapshot_*.json")))
    if len(snaps) < 2:
        return SKIP, "need two radar snapshots to compare universe size"
    def count(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        n = d.get("universe")
        if isinstance(n, int):
            return n
        t = d.get("tickers")
        return len(t) if hasattr(t, "__len__") else None
    cur, prev = count(snaps[-1]), count(snaps[-2])
    cur_d = os.path.basename(snaps[-1])[15:25]
    prev_d = os.path.basename(snaps[-2])[15:25]
    if cur is None or prev is None:
        return SKIP, "a radar snapshot is unreadable — cannot compare"
    if prev == 0:
        return SKIP, f"prior snapshot {prev_d} screened 0 names"
    drop = (prev - cur) / prev
    if drop >= UNIVERSE_DROP_FAIL:
        return FAIL, (f"universe shrank {prev}→{cur} ({drop:.0%}) since {prev_d}. "
                      f"Either a deliberate watchlist edit or a parse failure in "
                      f"input/watchlist*.md — load_watchlists() drops what it "
                      f"cannot parse without complaining. Confirm the edit, or "
                      f"check the file for a truncation or a broken table.")
    if drop >= UNIVERSE_DROP_WARN:
        return WARN, (f"universe shrank {prev}→{cur} ({drop:.0%}) since {prev_d} "
                      f"— small, but check it was an intended watchlist edit")
    return OK, (f"universe {cur} name(s) screened, {prev} on {prev_d} "
                f"({cur - prev:+d})")


def h1_dates(head):
    """Every date an evaluation's H1 states, normalised to YYYY-MM-DD.

    Three spellings, because the H1 is written by an agent from a template and the
    exact wording has never been contractual — only the date it carries is. The
    corpus uses the prose form ("— Monday 24 August 2026"); the template asks for
    ISO ("— 2026-08-25"); both are unambiguous and both are accepted.

    This replaces a `day in head and month in head and year in head` substring test
    (2026-08-25). That test failed every ISO H1 — "August" appears nowhere in
    "2026-08-25" — which is how a reviewed, ledger-written evaluation came to trip
    a ⛔ on nothing but its own date format. It was also weak in the other
    direction: the day matched on any stray "25" anywhere in the line, so three
    incidental substrings could clear a date that was never actually stated.
    """
    out = set()
    for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", head):
        out.add(m.group(0))
    for pat, fmt in ((r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b", "%d %B %Y"),
                     (r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b", "%B %d %Y")):
        for m in re.finditer(pat, head):
            try:
                d = datetime.datetime.strptime(" ".join(m.groups()), fmt)
            except ValueError:
                continue
            out.add(d.strftime("%Y-%m-%d"))
    return out


def check_eval_dates():
    """No dated evaluation carries somebody else's date in its H1.

    WHY THIS EXISTS. `output/latest.md` used to be a symlink. An agent told to
    "sync the pointer" wrote a file *to* that path; the write followed the link
    and overwrote the evaluation it was aimed at. On 2026-08-23 that destroyed
    `evaluation_2026-08-22.md`, and a failed `ln -s` had already destroyed
    `evaluation_2026-08-15.md` on the 18th. There is no VCS here.

    The pointers were retired outright on 2026-08-25 rather than kept as copies:
    nothing read them programmatically, every consumer knows the run date, and a
    file whose whole job is to duplicate another is one more thing a run can get
    wrong. What survives is the half that was never about the pointer — an
    evaluation whose H1 date is not its filename date has been written over, and
    that is worth catching however the write arrived.
    """
    problems, historic = [], []

    # An evaluation whose H1 date is not its filename date has been written over.
    for name in sorted(os.listdir(OUTPUT_DIR)):
        m = re.fullmatch(r"evaluation_(\d{4}-\d{2}-\d{2})\.md", name)
        if not m:
            continue
        stamped = m.group(1)
        try:
            with open(os.path.join(OUTPUT_DIR, name), encoding="utf-8") as f:
                head = f.readline()
        except OSError:
            continue
        if head.startswith(TOMBSTONE):
            continue                    # already acknowledged as lost
        try:
            d = datetime.datetime.strptime(stamped, "%Y-%m-%d")
        except ValueError:
            continue
        # H1 reads e.g. "# Trading Sleeve Evaluation — Sunday 23 August 2026", or
        # the template's "# <Sleeve> Evaluation — 2026-08-25". Either states a date;
        # the only question this check asks is whether it is THIS file's date.
        if head.strip() and stamped not in h1_dates(head):
            msg = (f"{name} carries an H1 that is not its own date "
                   f"({head.strip()[:60]!r}) — it was probably overwritten")
            (problems if stamped == today() else historic).append(msg)

    if problems:
        return FAIL, " · ".join(problems)
    if historic:
        # Past damage, unrecoverable and not caused by this run. WARN, not FAIL:
        # a check that can never go green again is a check people learn to skip.
        # Acknowledge one by making its first line start with the TOMBSTONE
        # marker, which records what was lost instead of pretending otherwise.
        return WARN, (f"{len(historic)} evaluation(s) overwritten in the past "
                      f"(unrecoverable; tombstone the file to silence): "
                      + " · ".join(historic))
    return OK, "every dated evaluation carries its own date"


def check_ledger_touched():
    eval_path = os.path.join(OUTPUT_DIR, f"evaluation_{today()}.md")
    if not os.path.exists(eval_path):
        return SKIP, "no evaluation for today yet"
    ledger = os.path.join(OUTPUT_DIR, "ledger", "Gate_Ledger.csv")
    led_today = (os.path.exists(ledger)
                 and any(ln.startswith(today()) for ln in open(ledger, encoding="utf-8")))
    if led_today:
        return OK, "Gate_Ledger.csv has row(s) dated today"
    # No WARN tier here any more. The draft-then-commit step this used to allow
    # for is gone (append_gate_ledger.py writes straight through), so "evaluation
    # on disk, ledger untouched" has exactly one meaning: the step did not run.
    return FAIL, ("today's evaluation exists but the ledger was not touched — "
                  "run tools/append_gate_ledger.py")


# ---------------------------------------------------------------- publish sweep

def check_publish_leaks():
    _, total, _ = load_holdings()
    demo = hr.discover_holdings_files()[1]
    if not total:
        return SKIP, "no holdings to derive leak strings from"
    # A demo book has no real NAV to leak, and its total is £100,000 — the nominal
    # sleeve CONFIG.md, DISCLAIMER.md and the rules files quote on nearly every
    # page. Sweeping for it reports every one of those as a breach. This is the
    # same reasoning `_add_needle` in tools/publish.py applies to round figures:
    # a worked example is not a secret, and a gate that fires on one is a gate
    # nobody reads. The discriminator is the roster itself, not the number —
    # raise the nominal to £250,000 and this still holds.
    if demo:
        return SKIP, "running on the demo book — no real NAV to sweep for"
    needles = {f"{total:,.0f}", f"{total:,.2f}", f"{total:.0f}"}
    # `.rerun` is skipped in the PRIVATE tree only (2026-08-23). Sandboxes there
    # are gitignored copies of `output/` and carry the real NAV by design, so
    # sweeping them reports a leak that is not one. In a published tree the same
    # skip is a blind spot: a `.rerun/` that got copied is exactly what this
    # sweep exists to catch, and it would pass unread. tools/publish.py now
    # excludes `.rerun/` and fails its own post-conditions if one appears —
    # this is the independent second opinion on that, and a backstop that trusts
    # the thing it backstops is not a backstop. The discriminator is the same one
    # check_no_private_providers() uses: a tree with private providers on disk is
    # the private one, and `--publish` there already FAILs on that check.
    skip_dirs = {".git", "node_modules", ".state", "__pycache__", "input",
                 "_to_delete", ".venv", "venv"}
    if providers.private_providers():
        skip_dirs.add(".rerun")
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if not fn.endswith((".md", ".csv", ".json", ".txt")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                body = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for n in needles:
                if n in body:
                    hits.append(os.path.relpath(p, ROOT))
                    break
    if hits:
        return FAIL, (f"real NAV (£{total:,.0f}) appears outside input/ in: "
                      + ", ".join(sorted(set(hits))[:12])
                      + (" …" if len(set(hits)) > 12 else "")
                      + " — regenerate output/ from anonymised holdings before pushing")
    return OK, "no real-NAV strings outside input/ and .state/"


def check_gitignore_sanity():
    path = os.path.join(ROOT, ".gitignore")
    if not os.path.exists(path):
        return FAIL, "no .gitignore"
    lines = open(path, encoding="utf-8").read().splitlines()
    problems = []
    if not any(ln.strip() == "node_modules/" for ln in lines):
        problems.append("node_modules/ not ignored")
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#") and "#" in s and "  #" in ln:
            problems.append(f"inline comment breaks pattern: {s[:40]!r}")
    if problems:
        return FAIL, "; ".join(problems)
    return OK, "node_modules covered; no inline-comment patterns"


# ---------------------------------------------------------------- runner

def check_rerun():
    """Is this the day's first run? Reports; never fails.

    WHY THIS IS A WARN AND NOT A FAIL (decision 2026-08-23). Running the
    pipeline twice in a day is a legitimate thing to want — the morning capture
    arrived late, a provider was down, the watchlist was edited. Blocking it
    would push the human to `rerun.py --in-place` (which rolls the day back and
    rewrites the append-only ledger) for what should be an ordinary repeat. So
    the four real same-day collisions were fixed at source instead:

      radar_state.json      rotates to radar_state.prev.json on the day's first
                            run, so run 2 still diffs against the previous DAY
      trader_timings_<date> a closed run moves to previous_runs[] instead of
                            being appended past
      evaluation_<date>.md  copied to .state/evaluation_<date>.run<N>.md before
                            the Trader overwrites it
      Gate_Ledger.csv       already de-duped on Date+Ticker+Action, draft and
                            commit alike

    What is left is worth SAYING, because nothing else in the output makes it
    visible: run 2 looks exactly like a first run. rotation_history.json and
    nav_history.json de-dupe on date, so run 2 replaces today's point rather
    than adding one — correct, but it does mean run 1's numbers are gone.
    """
    mp = os.path.join(OUTPUT_DIR, ".state", "run_manifest.json")
    if not os.path.exists(mp):
        return OK, "first run (no manifest yet)"
    try:
        with open(mp, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        return WARN, f"run_manifest.json unreadable ({e.__class__.__name__}) — cannot tell which run this is"
    today = datetime.date.today().isoformat()
    if m.get("date") != today:
        return OK, f"first run today (manifest last stamped {m.get('date')})"
    nxt = int(m.get("run") or 1) + 1
    return WARN, (f"run {nxt} of {today} — supported, not an error. Radar keeps "
                  f"the previous DAY's baseline; the prior evaluation is "
                  f"archived to .state/evaluation_{today}.run{nxt - 1}.md; the "
                  f"ledger de-dupes. rotation/NAV history REPLACE today's point")


SUITES = {
    "pre": [("re-run", check_rerun),
            ("providers discover", check_providers_discover),
            ("capture freshness", check_capture_freshness),
            ("sector-map dupes", check_sector_map_dupes),
            ("sector-map ambiguity", check_sector_map_ambiguous),
            ("brokers readable", check_brokers_readable),
            ("held classified", check_held_classified),
            ("provider config", check_provider_config)],
    "post": [("ticker identity", check_ticker_identity),
             ("bloc ceiling", check_bloc_ceiling),
             ("line caps", check_line_caps),
             ("NAV consistency", check_nav_consistency),
             ("radar age", check_radar_age),
             ("radar snapshot", check_radar_snapshot),
             ("universe size", check_universe_size),
             ("status honesty", check_status_honesty),
             ("eval dates", check_eval_dates),
             ("ledger touched", check_ledger_touched)],
    "publish": [("private providers", check_no_private_providers),
                ("leak sweep", check_publish_leaks),
                ("gitignore sanity", check_gitignore_sanity)],
}

ICON = {OK: "✅", WARN: "🟡", FAIL: "⛔", SKIP: "⚪"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    ap.add_argument("--pre", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    suites = [k for k, on in (("pre", a.pre), ("post", a.post),
                              ("publish", a.publish)) if on] or ["pre", "post"]

    failed = 0
    for suite in suites:
        print(f"\n[checks] —— {suite} ——")
        for name, fn in SUITES[suite]:
            try:
                status, msg = fn()
            except Exception as e:                      # a broken check must be loud
                status, msg = FAIL, f"check crashed: {e!r}"
            print(f"[checks] {ICON[status]} {status:4s} {name}: {msg}")
            failed += status == FAIL
    print(f"\n[checks] {'FAIL' if failed else 'OK'} — {failed} failing check(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
