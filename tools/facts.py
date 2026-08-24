#!/usr/bin/env python3
"""
Facts sheet — the deterministic half of the Analyst's price/analyst/earnings leg.

WHY THIS EXISTS
  The run needs six figures on every actionable name: current price, 52-week high
  and % below, analyst consensus PT and % upside, next earnings date, and any rating
  change in the last ~14 days. Done by hand that is one web search per name per leg,
  and on a ~30-name roster it is both the single most expensive part of the run and
  the least reliable: a paraphrased quote is a quote that can be wrong, and a search
  that quietly returns nothing looks exactly like a name with no upcoming earnings.

  None of it is judgement. It is lookup. This script does the lookup once, writes it
  to a file, and the evaluation reads the file. The gates, the sizing and the calls
  stay where they belong — with the reader of the rulebooks.

  The second-order win is bigger than the cost saving: the four PRE-ENTRY VALIDATION
  flags and two of the PROACTIVE SCREENING tests are pure arithmetic over these
  numbers, so they are computed here rather than judged. A flag that fires from a
  formula cannot be forgotten on a long roster at the end of a long report.

PRICE LEG COMES FROM THE RADAR'S OWN FETCHER, DELIBERATELY
  `engine/heartbeat_radar.py` already fetches a 2-year daily series per ticker over
  stdlib and computes `hi52` as the max close of the last 252 sessions. This script
  imports that same `fetch()` and repeats that same convention rather than sourcing
  price from anywhere else. Two files quoting two prices for one ticker on one day is
  a defect that surfaces as a contradiction inside the report, and whichever number
  loses the argument was never wrong in a way anyone could see.

  The analyst / earnings / ratings legs are not in the chart endpoint, so they use
  `yfinance` where it is installed. That import is OPTIONAL: without it every row
  still carries price, 52-week high and YTD, and every row is stamped PARTIAL naming
  the missing legs. Degrading loudly beats failing, and both beat a silent gap.

STATUS DISCIPLINE
  Every roster name appears in the output exactly once, including the ones that
  failed. `rules/03_DAILY_RUN.md` makes the roster the contract of the run, and a
  facts file that drops its failures would hand the evaluation a shorter roster than
  the one it is judged against. FAIL rows are listed twice — in the table and again
  under FAILURES — because a row in a 30-line table is easy to miss.

Inputs   input/*.csv           via heartbeat_radar's schema detection
         input/watchlist*.md    via heartbeat_radar's registry parser
         input/tracking/universe.md        only with --include-discovery
Output   output/data/facts_<date>.csv   machine-readable, one row per roster name
         output/data/latest.md          the file the evaluation reads

Usage    python3 tools/facts.py
         python3 tools/facts.py --include-discovery
         python3 tools/facts.py --workers 4
"""

import argparse
import csv
import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))

import heartbeat_radar as hr  # noqa: E402  — path set above

# Thresholds. These mirror the PRE-ENTRY VALIDATION and PROACTIVE SCREENING
# blocks of `agents/trader.md` §7. Changing one here changes what the
# report flags, so they are named rather than inlined.
BINARY_DAYS      = 7     # earnings within N days  -> no full-size entry
EARNINGS_WATCH   = 14    # earnings within N days  -> PROACTIVE SCREENING mention
AT_PEAK_PCT      = 10.0  # within N% of the 52-week high -> AT PEAK
EXTENDED_RUN_PCT = 50.0  # YTD gain above N%             -> EXTENDED RUN
RATING_WINDOW    = 14    # rating changes in the last N days

# Only genuine rating CHANGES count. Yahoo's Action codes also include "main"
# (maintained) and "reit" (reiterated), which are an analyst restating an existing
# view — on a widely-covered mega-cap those arrive in blocks of ten after every
# print and would bury the two actual downgrades underneath them. PROACTIVE
# SCREENING asks for "any downgrade in the past 14 days", and a reiteration is
# not one.
RATING_ACTIONS = {"up", "down", "init"}

try:
    import yfinance as yf
    # yfinance logs a 404 to stderr for every fund it asks for fundamentals on. That
    # is the expected answer for an ETF, not an error, and left on it prints a wall of
    # scary tracebacks above a clean run. Real failures still surface via row status.
    import logging
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    YF = True
except Exception:
    YF = False


# ---------------------------------------------------------------- price leg

def alt_form(ticker):
    """The other plausible Yahoo form of a ticker: NTAP.L <-> NTAP."""
    return ticker[:-2] if ticker.upper().endswith(".L") else ticker + ".L"


def price_leg(ticker):
    """Price, 52-week high and YTD from the radar's own 2-year series.

    Returns a dict, or {"error": ...}. `hi52` follows heartbeat_radar.analyse()
    exactly — max CLOSE over the last 252 sessions, not an intraday high — so the
    two files never disagree about how far below its high a name is sitting.

    RETRY IN THE OTHER FORM. Where the broker CSV has no currency column, the
    radar's `resolve_ticker()` has to guess the exchange suffix, and it guesses
    from the instrument name — so US lines held in a UK account can come through
    as NTAP.L, JCI.L, TEVA.L and 404. The radar's own contract is that "an
    inferred ticker that fails to fetch is retried in its other plausible form
    (bare <-> .L) before being written off, so a bad guess self-corrects against
    the price feed rather than becoming a holding with no exit line." That retry
    lives inside the radar's run loop, so this file has to repeat it or it would
    report a resolution guess as a data failure — three of them on the first real
    roster this ran against.
    """
    closes, vols, cur, ts = hr.fetch(ticker)
    resolved = None
    if not closes:
        alt = alt_form(ticker)
        closes, vols, cur2, ts = hr.fetch(alt)
        if not closes:
            return {"error": cur or "no data"}
        resolved = alt
        # `cur` currently holds the FIRST fetch's error string — hr.fetch() returns the
        # error message in the currency slot on failure. Carrying it forward printed
        # "HTTP Error 404: Not Found" in the Ccy column of a row that had fetched
        # perfectly well on the retry.
        cur = cur2

    px = closes[-1]
    hi52 = max(closes[-252:]) if len(closes) >= 252 else max(closes)
    pct_from_hi = (px / hi52 - 1) * 100

    # YTD from the last close of the previous calendar year where the series reaches
    # back that far. Falling back to the first available bar would silently report a
    # part-year return as YTD, which feeds straight into the EXTENDED RUN test.
    ytd = None
    if ts:
        jan1 = datetime.datetime(datetime.date.today().year, 1, 1).timestamp()
        prior = [c for c, t in zip(closes, ts) if t < jan1]
        if prior:
            ytd = (px / prior[-1] - 1) * 100

    return {
        "px": px,
        "cur": cur,
        "hi52": hi52,
        "pct_from_hi": pct_from_hi,
        "ytd": ytd,
        "bars": len(closes),
        "last_bar": datetime.date.fromtimestamp(ts[-1]).isoformat() if ts else "",
        "resolved": resolved,
    }


# ---------------------------------------------------- analyst / event legs

def analyst_leg(ticker):
    """Consensus PT, next earnings date and recent rating changes.

    Every field is independently optional — a name can have a PT and no earnings
    date, or ratings history and no coverage. Missing fields are returned as None
    and named in the row's status rather than defaulted, because a defaulted zero
    would read as "no upside" instead of "not known".
    """
    out = {"pt": None, "pt_n": None, "earnings": None, "ratings": [],
           "reiterations": 0, "is_fund": False, "quote_type": "", "miss": []}
    if not YF:
        out["miss"] = ["pt", "earnings", "ratings"]
        return out

    try:
        t = yf.Ticker(ticker)
    except Exception:
        out["miss"] = ["pt", "earnings", "ratings"]
        return out

    try:
        info = t.info or {}
        # A fund has no consensus PT and no earnings date BY DESIGN. Without this
        # check every ETF on the roster reports two missing legs and lands in the
        # gaps section, and on an ETF-heavy sleeve that is most of the report —
        # which trains the reader to scroll past the section where the one name
        # that genuinely failed to fetch is sitting.
        out["is_fund"] = str(info.get("quoteType", "")).upper() in ("ETF", "MUTUALFUND")
        out["quote_type"] = str(info.get("quoteType", "") or "")
        # Median, not mean: `agents/trader.md` §7 tests "above median analyst
        # PT by >10%", and a single outlier target moves the mean enough to flip it.
        out["pt"] = info.get("targetMedianPrice")
        out["pt_n"] = info.get("numberOfAnalystOpinions")
    except Exception:
        out["miss"].append("pt")

    try:
        cal = t.calendar or {}
        ed = cal.get("Earnings Date") or []
        if isinstance(ed, list) and ed:
            out["earnings"] = min(ed)
        elif ed:
            out["earnings"] = ed
    except Exception:
        out["miss"].append("earnings")

    try:
        ud = t.upgrades_downgrades
        if ud is not None and len(ud):
            cutoff = datetime.datetime.now().date() - datetime.timedelta(days=RATING_WINDOW)
            for idx, row in ud.iterrows():
                d = idx.date() if hasattr(idx, "date") else None
                if not (d and d >= cutoff):
                    continue
                action = str(row.get("Action", "")).lower().strip()
                if action not in RATING_ACTIONS:
                    out["reiterations"] += 1
                    continue
                out["ratings"].append({
                    "date": d.isoformat(),
                    "firm": str(row.get("Firm", "")),
                    "action": action,
                    "from": str(row.get("FromGrade", "")),
                    "to": str(row.get("ToGrade", "")),
                })
    except Exception:
        out["miss"].append("ratings")

    return out


# ---------------------------------------------------------------- assembly

def flags_for(row):
    """The deterministic subset of PRE-ENTRY VALIDATION and PROACTIVE SCREENING.

    These are computed, never judged. Everything here is arithmetic over figures
    already in the row; the assessment each flag then requires ("momentum vs a
    pullback entry", "fundamentals-driven or momentum-driven") is explicitly NOT
    done here and stays with the evaluation.
    """
    # NO SPACES INSIDE A FLAG TOKEN. The CSV stores these space-joined in one cell, so
    # a space inside a token silently splits it — "EXTENDED-RUN(YTD +79.9%)" parsed as
    # three flags, two of which were "+79.9%)" and a stray paren, and any downstream
    # count of how often a flag fires came out wrong without ever erroring.
    f = []
    days = row.get("days_to_earnings")
    if days is not None and 0 <= days <= BINARY_DAYS:
        f.append(f"BINARY-RISK({days}d)")
    elif days is not None and 0 <= days <= EARNINGS_WATCH:
        f.append(f"EARNINGS-{days}D")

    if row.get("pct_from_hi") is not None and row["pct_from_hi"] >= -AT_PEAK_PCT:
        f.append(f"AT-PEAK({row['pct_from_hi']:+.1f}%)")

    up = row.get("pt_upside")
    if up is not None and up < 0:
        f.append(f"CONSENSUS-EXCEEDED({-up:.1f}%>PT)")

    if row.get("ytd") is not None and row["ytd"] > EXTENDED_RUN_PCT:
        f.append(f"EXTENDED-RUN(YTD{row['ytd']:+.1f}%)")

    downs = [r for r in row.get("ratings", []) if r["action"] == "down"]
    if downs:
        f.append(f"DOWNGRADE-{RATING_WINDOW}D({len(downs)})")
    ups = [r for r in row.get("ratings", []) if r["action"] == "up"]
    if ups:
        f.append(f"UPGRADE-{RATING_WINDOW}D({len(ups)})")

    return f


def build_row(entry):
    ticker, membership, sector = entry
    row = {"ticker": ticker, "requested": ticker, "membership": membership,
           "sector": sector, "ratings": [], "status": "OK", "notes": []}

    p = price_leg(ticker)
    if "error" in p:
        row["status"] = "FAIL"
        row["notes"].append(f"price fetch failed: {p['error']}")
        return row
    row.update(p)

    # The suffix was guessed wrong and the price feed corrected it. Say so — a silent
    # correction leaves sector_map.md still holding the bad form, so tomorrow's run
    # pays the same two fetches again and the radar may still screen the wrong line.
    if p.get("resolved"):
        ticker = p["resolved"]
        row["ticker"] = ticker
        row["notes"].append(
            f"resolved as **{ticker}** after {row['requested']} returned 404 — the "
            f"broker CSV has no currency column, so the exchange suffix was inferred. "
            f"Add `{ticker}` to `input/tracking/sector_map.md` to make it stable.")

    a = analyst_leg(ticker)
    row["pt"], row["pt_n"] = a["pt"], a["pt_n"]
    row["ratings"] = a["ratings"]
    row["reiterations"] = a["reiterations"]
    row["is_fund"] = a["is_fund"]

    if a["earnings"]:
        row["earnings"] = a["earnings"].isoformat() if hasattr(a["earnings"], "isoformat") \
            else str(a["earnings"])
        try:
            ed = a["earnings"] if hasattr(a["earnings"], "toordinal") else None
            if ed:
                row["days_to_earnings"] = (ed - datetime.date.today()).days
        except (TypeError, ValueError, OverflowError):
            # Narrowed from `except Exception` 2026-08-23. days_to_earnings
            # feeds stock-card gate #5; an unexpected error here should surface
            # rather than quietly leave the field absent and pass the gate.
            pass

    # A "next earnings date" in the past means the feed's calendar has not rolled
    # forward. Left alone it is worse than no date at all: BINARY RISK tests
    # "earnings within 7 days", a negative number quietly fails that test, and a name
    # reporting on Tuesday would clear the gate on the strength of last quarter's
    # date. The flag that exists to stop full-size entries into a print is exactly
    # the one that must never fail silently — so this downgrades the row to PARTIAL
    # and says to check it live.
    d = row.get("days_to_earnings")
    if d is not None and d < 0:
        row["earnings_stale"] = row["earnings"]
        row["earnings"] = None
        row["days_to_earnings"] = None
        row["status"] = "PARTIAL"
        row["notes"].append(
            f"earnings calendar is stale — the feed still returns "
            f"{row['earnings_stale']} ({abs(d)}d ago) as the next date. "
            f"**Confirm the next report date live before any full-size entry.**")

    if row["pt"] and row.get("px"):
        row["pt_upside"] = (row["pt"] / row["px"] - 1) * 100

    # Vehicle classification, which decides whether a missing PT is a gap or a fact.
    #   FUND      — Yahoo says ETF/mutual fund. No PT or earnings by design.
    #   UNCOVERED — tagged EQUITY, yet zero analyst opinions AND no earnings calendar.
    #               This is the ETC/ETP/trust signature: SGLN.L, a physical gold ETC,
    #               is legally a debt security and so comes back EQUITY, which would
    #               otherwise put a plain tracker in the failures list every single
    #               day. A genuinely uncovered micro-cap lands here too — hence the
    #               note asks the reader to confirm rather than asserting a vehicle.
    #               Getting this wrong is not cosmetic: the vehicle-first rule
    #               (`agents/trader.md` §4, `rules/02_SLEEVE_RULES.md`) forbids
    #               running a fund through the stock card at all.
    #   STOCK     — covered single name. A missing leg here IS a gap.
    if a["miss"]:
        row["status"] = "PARTIAL"
        row["vehicle"] = "?"
        row["notes"].append("legs unavailable: " + ", ".join(sorted(set(a["miss"]))))
    elif row["is_fund"]:
        row["vehicle"] = "FUND"
        row["notes"].append("fund — no analyst PT or earnings date by design; "
                            "ETF card, never the stock card")
    elif (not row.get("pt") and not row.get("earnings") and not a["pt_n"]
            and not row.get("earnings_stale")):
        row["vehicle"] = "UNCOVERED"
        row["notes"].append(
            f"no analyst coverage and no earnings calendar, but Yahoo tags it "
            f"{a['quote_type'] or 'EQUITY'} — typical of an ETC/ETP/trust. "
            f"**Confirm the vehicle before picking a gate card.**")
    else:
        row["vehicle"] = "STOCK"
        for leg, key in (("consensus PT", "pt"), ("earnings date", "earnings")):
            # A stale date already has its own, more specific note — saying "no
            # earnings date published" as well would describe the wrong problem.
            if key == "earnings" and row.get("earnings_stale"):
                continue
            if not row.get(key):
                row["status"] = "PARTIAL"
                row["notes"].append(f"no {leg} published")

    row["flags"] = flags_for(row)
    return row


MEMBERSHIP_RANK = {"HELD": 0, "SPECULATIVE": 1, "WATCHLIST": 2, "DISCOVERY": 3}


def dedupe_resolved(rows):
    """Collapse names that became identical only after the suffix was corrected.

    Roster assembly dedupes on the ticker as GUESSED, which is one form too early. A
    name held as `TEVA.L` and watchlisted as `TEVA` passes that check as two distinct
    entries, and both then correct to `TEVA` against the price feed — so the same
    position is counted twice.

    That is invariant 3 of `docs/SYSTEM_MAP.md`: "A name may exist in only one
    membership source; leaving it in two double-counts it in the rotation read and
    corrupts the momentum calculation." It also shifts every other name's RS
    percentile, because RS is ranked across the universe and the universe just grew
    by a phantom.

    The duplicate is reported, never silently merged — the real fix is upstream, in
    the files: a name that has been bought belongs in the holdings CSV and its
    watchlist row should have been deleted on the fill.
    """
    best, collapsed = {}, []
    for r in rows:
        t = r["ticker"]
        if t not in best:
            best[t] = r
            continue
        a, b = best[t], r
        keep, drop = ((a, b) if MEMBERSHIP_RANK.get(a["membership"], 9)
                      <= MEMBERSHIP_RANK.get(b["membership"], 9) else (b, a))
        keep.setdefault("notes", []).append(
            f"listed as `{keep['requested']}` ({keep['membership']}) and as "
            f"`{drop['requested']}` ({drop['membership']}) — both resolve to the same "
            f"line. **Delete the {drop['membership'].lower()} entry**; a name may live "
            f"in only one membership source.")
        best[t] = keep
        collapsed.append((keep, drop))
    return list(best.values()), collapsed


def load_membership(include_discovery):
    """Roster = holdings + watchlists, matching the radar's own assembly.

    Holdings and watchlists are the roster contract of the run. Discovery names are
    triaged, not evaluated, so they are off by default — pulling six legs on ~30
    universe names that will mostly screen themselves out silently is exactly the
    spend this script exists to avoid.
    """
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


# ---------------------------------------------------------------- rendering

def fmt(v, dp=2, suffix=""):
    return f"{v:,.{dp}f}{suffix}" if isinstance(v, (int, float)) else "—"


def render_md(rows, skipped, demo, include_discovery):
    today = datetime.date.today().isoformat()
    ok = sum(1 for r in rows if r["status"] == "OK")
    part = sum(1 for r in rows if r["status"] == "PARTIAL")
    fail = sum(1 for r in rows if r["status"] == "FAIL")

    src = ("yfinance" if YF else
           "UNAVAILABLE — install with `pip install yfinance`; price legs only this run")

    L = [f"# Facts sheet — {today}", ""]
    if demo:
        L += ["> ⚠️ **DEMO DATA.** No real holdings CSV found; an *.example.csv file is in input/.", ""]
    L += [
        f"**Coverage: {len(rows)} names** — {ok} OK, {part} PARTIAL, {fail} FAIL.",
        f"Analyst/earnings/ratings source: **{src}**.",
        "Price, 52-week high and YTD come from the same fetcher and the same "
        "252-session close convention as `engine/heartbeat_radar.py`.",
        "",
        "> Figures are a lookup, not a judgement. Gates, sizing and signals stay in "
        "the evaluation. Flags below are arithmetic only — each still needs the "
        "assessment the evaluation's required sections ask for.",
        "",
        "| Ticker | Held | Veh | Px | Ccy | 52wH | %52wH | PT (med) | %Upside | "
        "Earnings | In | YTD | Flags | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in sorted(rows, key=lambda x: (x["membership"] != "HELD", x["ticker"])):
        if r["status"] == "FAIL":
            L.append(f"| **{r['ticker']}** | {r['membership']} | — | — | — | — | — | "
                     f"— | — | — | — | — | — | ⛔ FAIL |")
            continue
        d = r.get("days_to_earnings")
        veh = r.get("vehicle", "?")
        na = "n/a" if veh in ("FUND", "UNCOVERED") else "—"
        L.append(
            f"| **{r['ticker']}** | {r['membership']} | {veh} | {fmt(r.get('px'))} | "
            f"{r.get('cur', '')} | {fmt(r.get('hi52'))} | "
            f"{fmt(r.get('pct_from_hi'), 1, '%')} | "
            f"{fmt(r.get('pt')) if r.get('pt') else na} | "
            f"{fmt(r.get('pt_upside'), 1, '%')} | "
            f"{r.get('earnings') or ('⚠️ stale' if r.get('earnings_stale') else na)} | "
            f"{str(d) + 'd' if d is not None else '—'} | "
            f"{fmt(r.get('ytd'), 1, '%')} | {' '.join(r.get('flags', [])) or '—'} | "
            f"{'✅' if r['status'] == 'OK' else '⚠️ PARTIAL'} |")

    fails = [r for r in rows if r["status"] == "FAIL"]
    partials = [r for r in rows if r["status"] == "PARTIAL"]
    uncov = [r for r in rows if r.get("vehicle") == "UNCOVERED"]

    L += ["", "## Failures and gaps", ""]
    if not fails and not partials and not skipped:
        L.append("None — every roster name returned every leg it should have.")
    for r in fails:
        L.append(f"- ⛔ **{r['ticker']}** ({r['membership']}) — {'; '.join(r['notes'])}. "
                 f"**Check this name live before writing its call.**")
    for r in partials:
        L.append(f"- ⚠️ **{r['ticker']}** — {'; '.join(r['notes'])}.")
    for sym, reason in skipped:
        L.append(f"- ⏭️ **{sym}** — {reason}; excluded by the radar on the same test.")

    dupes = [r for r in rows if any("both resolve to the same" in n
                                    for n in r.get("notes", []))]
    if dupes:
        L += ["", "## Duplicate membership — fix in the input files", ""]
        for r in dupes:
            note = [n for n in r["notes"] if "both resolve to the same" in n][0]
            L.append(f"- ♻️ **{r['ticker']}** ({r['membership']}) — {note} "
                     f"*Until then the radar counts it twice in the rotation read and "
                     f"in the RS percentile base.*")

    fixed = [r for r in rows if r.get("resolved")]
    if fixed:
        L += ["", "## Ticker resolution corrected", ""]
        for r in fixed:
            L.append(f"- 🔁 **{r['requested']} → {r['ticker']}** ({r['membership']}) — "
                     f"the guessed suffix 404'd and the other form fetched. "
                     f"**Add `{r['ticker']}` to `input/tracking/sector_map.md`** so the radar "
                     f"and this sheet stop guessing.")

    if uncov:
        L += ["", "## Vehicle unconfirmed — check before picking a gate card", ""]
        for r in uncov:
            L.append(f"- ❓ **{r['ticker']}** ({r['membership']}) — {r['notes'][0]}")

    rated = [r for r in rows if r.get("ratings")]
    reit = sum(r.get("reiterations", 0) for r in rows)
    L += ["", f"## Rating changes, last {RATING_WINDOW} days", ""]
    if not rated:
        L.append("None.")
    for r in rated:
        for c in r["ratings"]:
            arrow = {"up": "⬆️", "down": "⬇️", "init": "🆕"}.get(c["action"], "•")
            L.append(f"- {arrow} **{r['ticker']}** {c['date']} — {c['firm']}: "
                     f"{c['from'] or '—'} → {c['to']}")
    if reit:
        L.append("")
        L.append(f"*{reit} reiteration(s)/maintained rating(s) in the window are "
                 f"excluded — a restated view is not a rating change.*")

    if not include_discovery:
        L += ["", "*Discovery names excluded — they are triaged from the radar, not "
              "evaluated. Run with `--include-discovery` to pull them too.*"]
    L += ["", f"*Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} by "
          f"`tools/facts.py`. Not financial advice — see `DISCLAIMER.md`.*"]
    return "\n".join(L)


CSV_COLS = ["ticker", "requested", "membership", "sector", "vehicle", "px", "cur", "hi52",
            "pct_from_hi", "pt", "pt_n", "pt_upside", "earnings",
            "days_to_earnings", "earnings_stale", "ytd", "bars", "last_bar",
            "flags", "status", "notes"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-discovery", action="store_true",
                    help="also pull the discovery universe (off by default)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out-dir", default=os.path.join(hr.OUTPUT_DIR, "data"))
    a = ap.parse_args()

    members, skipped, detections, demo = load_membership(a.include_discovery)
    if not members:
        print("No roster found. Expected holdings CSVs in input/ "
              "or watchlists matching input/watchlist*.md.", file=sys.stderr)
        return 1

    print(f"Roster: {len(members)} names "
          f"({sum(1 for m in members if m[1] == 'HELD')} held). "
          f"Analyst legs: {'yfinance' if YF else 'UNAVAILABLE'}.")
    for base, detail in detections:
        print(f"  · {base}: {detail}")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(build_row, members))

    rows, collapsed = dedupe_resolved(rows)
    for keep, drop in collapsed:
        print(f"  ⚠️  {keep['ticker']} appeared twice — as {keep['requested']} "
              f"({keep['membership']}) and {drop['requested']} ({drop['membership']}). "
              f"Kept the {keep['membership']} row.")

    os.makedirs(a.out_dir, exist_ok=True)
    today = datetime.date.today().isoformat()

    csv_path = os.path.join(a.out_dir, f"facts_{today}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r = dict(r)
            r["flags"] = " ".join(r.get("flags", []))
            r["notes"] = "; ".join(r.get("notes", []))
            w.writerow(r)

    md = render_md(rows, skipped, demo, a.include_discovery)
    for p in (os.path.join(a.out_dir, f"facts_{today}.md"),
              os.path.join(a.out_dir, "latest.md")):
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)

    fail = sum(1 for r in rows if r["status"] == "FAIL")
    print(f"Wrote {csv_path}")
    print(f"Wrote {os.path.join(a.out_dir, 'latest.md')}")
    if fail:
        print(f"⛔ {fail} name(s) failed and are listed under FAILURES — "
              f"check these live before writing their calls.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
