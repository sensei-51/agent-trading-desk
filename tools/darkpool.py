#!/usr/bin/env python3
"""
darkpool.py — the darkpool and conviction legs, rendered for the agents to read.

WHAT THIS STEP DOES AND DELIBERATELY DOES NOT DO
  It reads the two whole-book legs (`darkpool`, `conviction`) from whichever
  providers `input/config/providers.json` names, and writes them to
  `output/data/darkpool_<date>.md`.

  It changes **no gate, no cap, no signal and no tag**. No gate card reads this
  file, by decision: darkpool is a permanent optional overlay (`docs/BACKLOG.md`
  D5) and the radar's rotation read is what ETF gate 1 consults. That is not a
  phase waiting to end — it is the settled shape of the leg.

WHAT THIS LEG MEASURES, AND WHAT IT DOES NOT
  It measures **unusual options premium**. It does not measure dark-pool block
  accumulation. The dark-pool leaderboard is the *discovery route* — how tickers
  are found — and the quantity recorded against each one is options premium
  (`method: basis=unusual_options; discovery=darkpool_leaderboard_...`).

  Direction is **inferred, not observed**: the platform assigns the initiating
  side from where a print landed against the bid/ask. A bought call may be a
  hedge against a short, or one leg of a spread priced separately. Observed
  20 Aug 2026: SLV showed $28M of calls against $18M of puts while the single
  largest print was a $12M December put.

  So a `bullish` cell means *"options premium leaned this way, at this size, in
  this session"* — never *"institutions are quietly accumulating."* See
  `docs/DARK_POOL_CAPTURE_SPEC.md` §9.

GBP LINES ARE RESOLVED THROUGH THE TWIN TABLE, AND LABELLED AS PROXIES
  Darkpool is US market structure: `SILG.L` has no darkpool, `SIL` does. Most of
  this sleeve is GBP lines, so without resolution the report cannot see the book
  at all — the Held column stayed empty for every UK holding.

  The table is `docs/DARK_POOL_CAPTURE_SPEC.md` §10, parsed at run time, the same
  way seven modules read `input/tracking/sector_map.md`. ONE copy, human-readable
  and machine-readable, which is the whole point of extracting it there.

  Every twin-sourced row is marked `via <LSE line>` and never a bare ✅. The
  earlier refusal to resolve twins was right about the risk — "pretending to have
  them now would put a proxy in the report unlabelled" — and wrong only about the
  remedy, which is the label, not the wait.

THE SIGNIFICANCE FLOOR IS RENDERED HERE, OWNED ELSEWHERE
  A percentage without a size is noise. Observed 2026-08-20: URA rendered
  "100% bullish" on ONE $84K print, in the same table as GLD's 86% on $131M.
  Rows below the floor are marked `THIN` — not bullish, not bearish, *not
  enough money to constitute an observation*.

  The number lives here as a rendering constant only. No gate consults it and
  none is going to (D5), so it stays a display threshold on an overlay — a wrong
  value mislabels a row rather than deciding a trade. `docs/BACKLOG.md` item 10
  demoted it for exactly that reason. If it ever does move, it moves to the
  capture spec, not to `rules/`.

STALENESS
  Both legs are `browser`-ingested, so both carry `max_age_days`. The check
  fires on `read_at` (when you looked), never on `session_date` / `signal_date`
  (what the data describes) — a fortnight-old regime signal read this morning
  is current; this morning's darkpool read a fortnight ago is not.

Inputs   input/config/providers.json        provider selection, per leg
         docs/DARK_POOL_CAPTURE_SPEC.md     §10, the GBP→US twin table
         input/capture/darkpool_<date>.md       for browser/file darkpool providers
         input/capture/conviction_<date>.md
         input/*.csv                        broker export, to mark held names
Output   output/data/darkpool_<date>.md
         output/data/darkpool_<date>.md         the file the agents read

Usage    python3 tools/darkpool.py
         python3 tools/darkpool.py --list-providers
         python3 tools/darkpool.py --provider darkpoolsource      # override config
         python3 tools/darkpool.py --conviction-provider none
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


TWIN_SPEC = os.path.join(ROOT, "docs", "DARK_POOL_CAPTURE_SPEC.md")
# Any dotted exchange suffix, not just `.L`. The table began as LSE-only and the
# `\.L` that encoded that assumption made `KNT.TO` (TSX) invisible to this parser —
# documented in §10, unreadable here, which §10 itself calls no better than
# describing a line in a sentence.
_TWIN_ROW = re.compile(r"^\|\s*`([A-Z0-9]+\.[A-Z]{1,3})`\s*\|\s*(?:`([A-Z]+)`|—|-)\s*\|"
                       r"\s*(\w+)\s*\|")


def load_twins():
    """({LSE: US|None}, {LSE: tier}, [warning]) — from the capture spec's §10 table.

    A key present with a `None` value means "checked, no usable twin" and is NOT
    the same as an absent key: an absent LSE line falls through, gets looked up
    under its own ticker, finds nothing, and is recorded as "no darkpool" —
    indistinguishable from a name that was checked and was genuinely quiet. The
    spec says so in prose; this function is where it has to be true.
    """
    if not os.path.exists(TWIN_SPEC):
        return {}, {}, [f"{os.path.relpath(TWIN_SPEC, ROOT)} missing — GBP lines cannot "
                        f"be resolved to US twins; every UK holding will read as unheld"]
    out, tiers, section = {}, {}, False
    with open(TWIN_SPEC, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                section = line.startswith("## 10.")
                continue
            if not section:
                continue
            m = _TWIN_ROW.match(line.strip())
            if m:
                out[m.group(1)] = m.group(2) or None
                tiers[m.group(1)] = m.group(3)
    if not out:
        return {}, {}, [f"{os.path.relpath(TWIN_SPEC, ROOT)} §10 parsed to zero rows — the "
                        f"table shape changed. GBP lines are UNRESOLVED, not twin-free"]
    return out, tiers, []


def held_symbols():
    """Bare symbols from every broker CSV in input/. No resolution here — see
    `twin_index()`, which maps them onto US tickers for the report."""
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


def twin_index(held, twins, tiers):
    """{US ticker: [LSE lines held that read through it]}.

    Several GBP lines share a twin — four uranium lines all read `URA` — so the
    value is a list, and the report names them all rather than picking one.

    BROKER EXPORTS CARRY BARE SYMBOLS. `input/AJ Bell.csv` lists the gold ETC as
    `SGLN`, not `SGLN.L`, so an exact-key lookup matches NOTHING and every UK
    holding reads as unheld — silently, which is the failure mode this whole
    table exists to prevent. So a bare symbol is accepted as its suffixed line,
    whatever the exchange suffix is.

    BUT NOT FOR SINGLE STOCKS. `BA.L` is BAE Systems and `BA` is Boeing; `RR.L`
    is Rolls-Royce and `RR` is a US listing too. Bare-matching those would read a
    US holding through a UK company's sector proxy and label it as the book's own
    position. The `single` tier is therefore exact-match only. The ETF tiers have
    no such collisions — `SGLN`, `XLVP`, `CNX1` are not US tickers — which is
    what makes the tier column in §10 load-bearing rather than decorative.
    """
    out = {}
    for lse, us in sorted(twins.items()):
        if not us or us in held:
            continue
        exact = lse in held
        # rsplit, NOT lse[:-2]: the old slice hardcoded a two-character `.L` and
        # turns `KNT.TO` into `KNT.`, which matches nothing and would do it silently.
        bare = tiers.get(lse) in ("index", "gauge") and lse.rsplit(".", 1)[0] in held
        if exact or bare:
            out.setdefault(us, []).append(lse)
    return out


# ---------------------------------------------------------------- the book
#
# SEVEN STATES, AND WHY NONE OF THEM MAY BE COLLAPSED
#   The `### Book` table below is keyed by ROSTER TICKER — the `.L`-suffixed form
#   the Trader's board uses — so a darkpool cell can be copied out rather than
#   derived by hand from a US-keyed table plus a second lookup into §10. That
#   second lookup is the one a hurried reader fudges to "—", and the fudge is
#   indistinguishable from a real absence.
#
#   | Cell           | Means                                                    |
#   |----------------|----------------------------------------------------------|
#   | bullish $144M  | direct read, at or above the floor                       |
#   | via GLD: …     | PROXY — a non-US line read through its §10 twin          |
#   | `THIN` $0      | in the capture, below the floor — CHECKED, quiet         |
#   | `no twin`      | §10 maps it to None — CHECKED, cannot ever be seen       |
#   | `unseen`       | no row in the capture. Says nothing about the bridge     |
#   | `unmapped` ⚠️  | a dotted line ABSENT from §10 — nobody ever decided      |
#   | —              | the whole leg is ABSENT this run                         |
#
#   `unseen` and `unmapped` are the pair that matters. Measured 26 Aug 2026, of
#   the 20 book lines with no capture row, ZERO were bridge failures: nine were
#   plain US tickers, which never consult §10 at all; three crossed the bridge
#   perfectly and then found the twin itself missing from the capture; and the
#   rest were not tickers at all. So `unseen` is a property of
#   the CAPTURE, not of the bridge.
#
#   `unmapped` is the guard for item 9.1's still-open half: an unlisted `.L` line
#   otherwise falls through, is looked up under its own LSE ticker, finds nothing
#   and renders exactly like a name that was checked and found quiet. Zero roster
#   lines are in that state today; nothing warned if one appeared. Now something
#   does.
#
#   A NOTE ON THE FOURTH STATE'S HONESTY. `unseen` is genuinely ambiguous — the
#   capture format uses two conventions at once. 23 of its 120 rows are explicit
#   zeros (`ESEA`, `EWJ`, `XLY`…), which is the vendor saying "looked, found
#   nothing"; other roster names are simply absent despite the method line
#   claiming a roster sweep. Nothing can separate "swept, quiet" from "never
#   swept" for those. Fixing that is a capture-spec change, not a code change.

def direction_read(pb):
    """Four-way premium-lean read (decision 2026-08-27): strength is still lean,
    never conviction — the §9 caveat applies to a 🟩🟩 exactly as it did to bold."""
    if pb is None:
        return "—"
    if pb >= 80:
        return "🟩🟩 **bullish-strong**"
    if pb >= 60:
        return "🟩 **bullish-weak**"
    if pb <= 20:
        return "🟥🟥 **bearish-strong**"
    if pb <= 40:
        return "🟥 **bearish-weak**"
    return "mixed"


READ_LEGEND = ("*Reads: 🟩🟩 ≥80% bullish · 🟩 60–79% · mixed 41–59% · "
               "🟥 21–40% · 🟥🟥 ≤20% — premium lean, per the caveat above.*")


def book_cell(ticker, rows, twins, leg_ok):
    """(cell, state) for one roster line. The seven states above, never fewer."""
    if not leg_ok:
        return "—", "leg-absent"

    look, proxy = ticker, None
    if "." in ticker:                       # a non-US line has to cross the bridge
        if ticker not in twins:
            return "`unmapped` ⚠️", "unmapped"
        if twins[ticker] is None:
            return "`no twin`", "no-twin"
        look, proxy = twins[ticker], ticker

    r = rows.get(look)
    if r is None:
        return "`unseen`", "unseen"

    tot = r.get("premium_usd") or 0.0
    if tot < SIGNIFICANCE_FLOOR_USD:
        body, state = f"`THIN` {money(tot)}", "thin"
    else:
        pb = r.get("pct_bullish")
        body = direction_read(pb) + f" {money(tot)}"
        state = "read"
    # In a book-keyed table the row IS the held line, so naming it again says
    # nothing — name the TWIN that was actually read instead.
    return (f"via {look}: {body}", "proxy-" + state) if proxy else (body, state)


def load_book():
    """[(roster ticker, membership)] — the same assembly the radar and facts use.

    Deliberately NOT `held_symbols()`. Broker exports carry bare symbols and,
    worse, SEDOL-style codes and cash lines. Those are not tickers, darkpool
    cannot have an opinion on them, and keying the book table on them renders
    rows of confident `unseen` about a cash balance.
    The roster loader resolves to the `.L`-suffixed ticker the board uses.
    """
    try:
        sys.path.insert(0, os.path.join(ROOT, "engine"))
        import heartbeat_radar as hr                        # noqa: PLC0415
        smap = hr.load_sector_map()
        seen, out = set(), []
        for tk, _sector, _sym, _basis in hr.load_roster(smap=smap)[0]:
            if tk not in seen:
                seen.add(tk)
                out.append((tk, "held"))
        for tk, _src, spec in hr.load_watchlists(smap=smap):
            if tk not in seen:
                seen.add(tk)
                out.append((tk, "spec" if spec else "watch"))
        return out, []
    except Exception as e:                                  # noqa: BLE001
        return [], [f"roster unavailable ({type(e).__name__}: {e}) — the Book table "
                    f"cannot be rendered; the By-ticker table below is unaffected"]


def held_mark(ticker, held, via):
    """✅ for a direct holding · `via XXX.L` for one reached through a twin.

    Never the same glyph for both: a proxy that renders identically to a direct
    measurement is the exact failure this table was withheld to avoid.
    """
    if ticker in held:
        return "✅"
    lines = via.get(ticker)
    return "via " + ", ".join(lines) if lines else ""


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

def render(darkpool, fl_name, conv, cv_name, held, via, book, warnings):
    today = datetime.date.today().isoformat()
    L = [f"# 🐋 Darkpool & conviction — {today}", ""]
    L += ["*Whole-book legs, rendered for the agents as **context only**. No gate "
          "card reads this file, by decision — darkpool is a permanent optional "
          "overlay and the rotation read drives ETF gate 1 (`docs/BACKLOG.md` D5). "
          "Capture format: `docs/DARK_POOL_CAPTURE_SPEC.md`.*", "",
          "> **What this leg measures.** **Unusual options premium — not dark-pool "
          "block accumulation.** The dark-pool leaderboard is the *discovery route*; "
          "the recorded quantity is options premium. Direction is **inferred**, not "
          "observed: the platform assigns the initiating side from where a print "
          "landed against the bid/ask, and a bought call may be a hedge against a "
          "short or one leg of a spread priced separately. On 20 Aug 2026 SLV showed "
          "$28M of calls against $18M of puts while the single largest print was a "
          "$12M December put. **Read a `bullish` cell as \"premium leaned this way, "
          "at this size, this session\" — never as \"institutions are accumulating.\"** "
          "`docs/DARK_POOL_CAPTURE_SPEC.md` §9.", ""]

    # ---- darkpool -----------------------------------------------------------
    L += ["## 🐋 Darkpool", ""]
    if not darkpool or darkpool.get("status") == "NONE":
        L += [f"**ABSENT** — provider `{fl_name}`. "
              + ((darkpool or {}).get("notes") or ["no provider configured"])[0], ""]
    else:
        age = age_days(darkpool.get("read_at"))
        cap = getattr(providers.get("darkpool", fl_name), "max_age_days", None)
        stale = (age is not None and cap is not None and age > cap)
        L += [f"**{darkpool['status']}** · provider `{fl_name}` · session "
              f"**{darkpool.get('session_date') or '?'}** · read {darkpool.get('read_at') or '?'}"
              + (f" · ⚠️ **STALE** ({age}d > {cap}d)" if stale else ""), ""]
        m = darkpool.get("method")
        L += [f"*Method: {m.get('raw') if m else '**unrecorded — do not pool with another capture**'}*", ""]

        mk = darkpool.get("market")
        if mk:
            L += ["### Market", "",
                  f"**{pct(mk.get('pct_bullish'))} bullish / {pct(mk.get('pct_bearish'))} bearish"
                  f" — {money(mk.get('call_premium_usd'))} calls vs "
                  f"{money(mk.get('put_premium_usd'))} puts"
                  + (f". {mk['label']}.**" if mk.get("label") else ".**"), ""]

        rows = darkpool.get("tickers") or {}
        if rows:
            L += ["### By ticker", "",
                  f"*`THIN` = under {money(SIGNIFICANCE_FLOOR_USD)} aggregate premium: "
                  f"not bullish, not bearish, not enough money to be an observation.* "
                  f"*Held: ✅ = the book holds this line · `via XXX.L` = the book holds a "
                  f"GBP line that has no US darkpool of its own, read here through its twin "
                  f"(`docs/DARK_POOL_CAPTURE_SPEC.md` §10) — a **proxy**, never a direct "
                  f"measurement.* " + READ_LEGEND, "",
                  "| Ticker | Held | Bullish | Calls | Puts | Total | Read |",
                  "|---|---|---|---|---|---|---|"]
            for t, d in sorted(rows.items(),
                               key=lambda kv: -(kv[1].get("premium_usd") or 0)):
                tot = d.get("premium_usd") or 0.0
                if tot < SIGNIFICANCE_FLOOR_USD:
                    read = "`THIN`"
                else:
                    read = direction_read(d.get("pct_bullish"))
                L.append(f"| {t} | {held_mark(t, held, via)} | {pct(d.get('pct_bullish'))} "
                         f"| {money(d.get('call_premium_usd'))} | {money(d.get('put_premium_usd'))} "
                         f"| {money(tot)} | {read} |")
            L.append("")
        for n in darkpool.get("notes") or []:
            L.append(f"- {n}")
        L.append("")

    # ---- book ---------------------------------------------------------------
    # OUTSIDE the if/else above, deliberately. A run with `darkpool: none` must
    # still produce a complete book — every row reading `—`, none blank, none
    # missing. That is D5's standing test and 29.1's acceptance criterion: the
    # run loses the reading, never the row.
    if book:
        leg_ok = bool(darkpool and darkpool.get("status") != "NONE")
        rows = (darkpool or {}).get("tickers") or {}
        twins = book["twins"]
        L += ["### Book", "",
              "*Keyed by **roster ticker** — the form the Trader's board uses — so a "
              "darkpool cell is copied out, not derived. `via XXX` names the US twin "
              "a non-US line was read through: a **proxy**, never a direct "
              "measurement. The seven states are distinct on purpose — `THIN` and "
              "`no twin` mean **checked**, `unseen` means the capture has no row, and "
              "`unmapped` means the line is absent from "
              "`docs/DARK_POOL_CAPTURE_SPEC.md` §10 and nobody ever decided.* "
              + READ_LEGEND, "",
              "| Line | In book | 🐋 Darkpool |", "|---|---|---|"]
        tally, held_tally = {}, {}
        for ticker, membership in book["rows"]:
            cell, state = book_cell(ticker, rows, twins, leg_ok)
            tally[state] = tally.get(state, 0) + 1
            if membership == "held":
                held_tally[state] = held_tally.get(state, 0) + 1
            L.append(f"| {ticker} | {membership} | {cell} |")
        L.append("")

        # The abstention rate, per run rather than hand-computed once. This is the
        # number that governs whether item 29.3 may ever be built, and it is
        # reported over HELD LINES — D5's reason is that a backbone cannot abstain
        # on the majority of the book, and the watchlist is not the book. Quoting a
        # roster-wide figure is what made 29.2's premise ("67 above the floor") read
        # the opposite way from the truth.
        def line(tal, label):
            n = sum(tal.values())
            direct = tal.get("read", 0)
            proxy = sum(v for k, v in tal.items() if k.startswith("proxy-"))
            return (f"**{label}: {n} lines — {direct} direct "
                    f"({direct * 100 // n if n else 0}%), {proxy} via a proxy, "
                    f"{n - direct - proxy} no reading.**")

        L += [line(held_tally, "Coverage of the book (held)"), "",
              line(tally, "Coverage of the roster (held + watchlist)"), "",
              "*States: " + " · ".join(f"`{k}` {v}" for k, v in sorted(tally.items()))
              + ".*", "",
              "> A **direct** read is the only kind that is first-hand. Proxies are "
              "sector context, and several book lines can share one — four separate "
              "Nasdaq-100 lines all read the same `QQQ` row. "
              "**Display may repeat an observation; arithmetic may not.**", ""]
    for w in book.get("warnings", []) if book else []:
        L.append(f"- ⚠️ {w}")

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
                         f"| {held_mark(p['ticker'], held, via)} |")
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
    ap = argparse.ArgumentParser(description="Render the darkpool and conviction legs.")
    ap.add_argument("--provider", help="override the configured darkpool provider")
    ap.add_argument("--conviction-provider", help="override the configured conviction provider")
    ap.add_argument("--session-date", help="ask the darkpool provider for a specific session")
    ap.add_argument("--out-dir", default=DATA_DIR)
    ap.add_argument("--list-providers", action="store_true")
    a = ap.parse_args()

    if a.list_providers:
        for leg in ("darkpool", "conviction"):
            print(f"{leg}: {', '.join(providers.names(leg)) or '(none installed)'}")
        for e in providers.errors():
            print(f"  ⚠️  {e}")
        return 0

    warnings = list(providers.errors())
    cfg = read_config()

    fl, fl_name, n1 = resolve("darkpool", a.provider, cfg)
    cv, cv_name, n2 = resolve("conviction", a.conviction_provider, cfg)
    warnings += n1 + n2

    ctx = {"root": ROOT, "input_dir": INPUT_DIR}
    if a.session_date:
        ctx["session_date"] = a.session_date

    darkpool = conv = None
    if fl:
        darkpool, w = call(fl, ctx)
        warnings += w
    if cv:
        conv, w = call(cv, ctx)
        warnings += w

    held = held_symbols()
    twins, tiers, tw_warn = load_twins()
    warnings += tw_warn
    via = twin_index(held, twins, tiers)

    book_rows, book_warn = load_book()
    book = {"rows": book_rows, "twins": twins, "warnings": book_warn} if book_rows else None
    warnings += book_warn
    # An unmapped dotted line is item 9.1's silent gap. It renders `unmapped` in the
    # table; it also has to reach the operator, or the table is the only place it
    # is ever said and nobody re-reads a 99-row table.
    unmapped = sorted(t for t, _ in book_rows if "." in t and t not in twins)
    if unmapped:
        warnings.append(f"{len(unmapped)} roster line(s) absent from the §10 twin table "
                        f"— darkpool cannot resolve them and never said so until now: "
                        f"{', '.join(unmapped)}")

    text = render(darkpool, fl_name, conv, cv_name, held, via, book, warnings)

    os.makedirs(a.out_dir, exist_ok=True)
    today = datetime.date.today().isoformat()
    dated = os.path.join(a.out_dir, f"darkpool_{today}.md")
    with open(dated, "w", encoding="utf-8") as f:
        f.write(text)

    fs = (darkpool or {}).get("status", "NONE")
    cs = (conv or {}).get("status", "NONE")
    print(f"darkpool={fl_name}:{fs}  conviction={cv_name}:{cs}  "
          f"tickers={len((darkpool or {}).get('tickers') or {})}  "
          f"twins={len(twins)} ({len(via)} held via twin)")
    for w in warnings:
        print(f"  ⚠️  {w}")
    print(f"Wrote {os.path.relpath(dated, ROOT)}")
    # A configured-but-absent leg is a normal published state, not a failure.
    # Only a broken provider is worth halting the pipeline for.
    return 1 if any("contract violation" in w or "raised" in w for w in warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
