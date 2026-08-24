#!/usr/bin/env python3
"""
P&L and gate scoring, derived entirely from the gate ledger.

Three questions, in ascending order of how much they matter:

  1. Realised P&L   — what did closed trades actually make?
  2. Unrealised P&L — where do open positions stand, and how close to their stops?
  3. GATE SCORING   — of the ideas the gates BLOCKED, how many went up afterwards?

(3) is the one the ledger exists for and the only one your broker cannot tell you.
Every rulebook accumulates gates, each added after a loss, and none of them are ever
measured. A gate that blocks winners is costing money silently; a gate that blocks
losers is earning money invisibly. Without a decision log carrying a price at the
moment of the decision, both look identical -- and unmeasured rules eventually get
relaxed on vibes, usually right before they would have paid off.

This is why Price_At_Decision is mandatory on non-ENTERED rows. A blocked idea with
no recorded price can never be scored, and is simply lost evidence.

Inputs   output/ledger/Gate_Ledger.csv   (append-only; see templates/)
         live prices, fetched over HTTP
Output   output/reports/PnL_<date>.md    + latest.md pointer

Usage    python3 tools/pnl.py
         python3 tools/pnl.py --min-age 30 --out somewhere.md
         python3 tools/pnl.py --offline      # skip fetches; realised P&L only
"""

import argparse
import csv
import datetime
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.environ.get("TP_INPUT", os.path.join(ROOT, "input"))
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))

MIN_AGE_DAYS = 30      # a decision younger than this has not had time to be right or wrong
TIMEOUT = 20

# Ledger actions that put money to work. Everything else is a decision NOT to.
ENTRY_ACTIONS = {"ENTERED", "ADDED"}
EXIT_ACTIONS = {"EXITED"}
# Verdicts worth scoring: the gates said no, or said "less than you wanted".
BLOCK_ACTIONS = {"BLOCKED", "WATCHLIST", "WAIT", "STARTER-CAP", "DEFERRED"}


# ---------------------------------------------------------------------------
# price fetch


def fetch_price(ticker):
    """Latest close. Returns None on any failure -- never raises, never guesses."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?range=5d&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            d = json.load(r)
        res = d["chart"]["result"][0]
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
        return closes[-1] if closes else None
    except Exception:
        return None


def fetch_all(tickers):
    out = {}
    if not tickers:
        return out
    with ThreadPoolExecutor(max_workers=8) as ex:
        for tk, px in zip(tickers, ex.map(fetch_price, tickers)):
            out[tk] = px
    return out


# ---------------------------------------------------------------------------
# ledger


def parse_date(s):
    """Dates prefixed '~' are back-filled approximations. Accept several formats."""
    s = (s or "").strip().lstrip("~")
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def num(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").replace("£", "").strip())
    except (TypeError, ValueError):
        return None


def load_ledger(path):
    if not os.path.exists(path):
        sys.exit(f"No ledger at {path}\n"
                 f"Start one: cp templates/gate_ledger.template.csv {path}")
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if (r.get("Ticker") or "").strip()]


# ---------------------------------------------------------------------------
# sections


def realised(rows):
    """Closed trades, using the exit row's entry/exit prices.

    Holding period is measured from the *earliest ENTERED row for that ticker*, not
    from the exit row's own Date -- an exit row is usually dated the day it happened,
    so using it would report every trade as zero days held.
    """
    first_entry = {}
    for r in rows:
        if (r.get("Action") or "").strip().upper() == "ENTERED":
            tk, d = r["Ticker"].strip(), parse_date(r.get("Date"))
            if d and (tk not in first_entry or d < first_entry[tk]):
                first_entry[tk] = d

    out = []
    for r in rows:
        if (r.get("Action") or "").strip().upper() not in EXIT_ACTIONS:
            continue
        entry, exit_px = num(r.get("Avg_Entry")), num(r.get("Exit_Price"))
        qty = num(r.get("Qty"))
        if entry is None or exit_px is None:
            continue
        tk = r["Ticker"].strip()
        d_out = parse_date(r.get("Exit_Date"))
        d_in = first_entry.get(tk) or parse_date(r.get("Date"))
        out.append({
            "ticker": tk,
            "ccy": (r.get("Ccy") or "").strip(),
            "entry": entry, "exit": exit_px, "qty": qty,
            "pnl": (exit_px - entry) * qty if qty else None,
            "pct": (exit_px / entry - 1) * 100,
            "days": (d_out - d_in).days if d_in and d_out else None,
            "note": (r.get("Notes") or "").strip(),
        })
    return sorted(out, key=lambda x: x["pct"], reverse=True)


def unrealised(rows, prices):
    """Open positions, netted across ENTERED/ADDED rows and cost-weighted."""
    pos = {}
    for r in rows:
        act = (r.get("Action") or "").strip().upper()
        if act not in ENTRY_ACTIONS:
            continue
        if (r.get("Status") or "").strip().upper() not in ("OPEN", ""):
            continue
        tk, qty, entry = r["Ticker"].strip(), num(r.get("Qty")), num(r.get("Avg_Entry"))
        if qty is None or entry is None:
            continue
        p = pos.setdefault(tk, {"qty": 0.0, "cost": 0.0,
                                "ccy": (r.get("Ccy") or "").strip(),
                                "date": parse_date(r.get("Date"))})
        p["qty"] += qty
        p["cost"] += qty * entry

    closed = {r["Ticker"].strip() for r in rows
              if (r.get("Action") or "").strip().upper() in EXIT_ACTIONS}

    out = []
    for tk, p in pos.items():
        if tk in closed or p["qty"] <= 0:
            continue
        avg = p["cost"] / p["qty"]
        px = prices.get(tk)
        out.append({
            "ticker": tk, "ccy": p["ccy"], "qty": p["qty"], "avg": avg,
            "cost": p["cost"], "px": px,
            "value": px * p["qty"] if px else None,
            "pnl": (px - avg) * p["qty"] if px else None,
            "pct": (px / avg - 1) * 100 if px else None,
            "days": (datetime.date.today() - p["date"]).days if p["date"] else None,
        })
    return sorted(out, key=lambda x: (x["pct"] is None, -(x["pct"] or 0)))


def ratchet_state(pct):
    """Where the trailing ratchet should have the stop, given gain on cost.

    Milestones per rules/02_SLEEVE_RULES.md: +10% -> breakeven, +20% -> lock ~+10%,
    beyond +20% -> trail at the higher of the rising MA or -15% from the highest close.
    Ratchet up only; this never suggests lowering a stop.
    """
    if pct is None:
        return "—"
    if pct > 20:
        return "trail: MA or −15% from high"
    if pct >= 20:
        return "lock ~+10%"
    if pct >= 10:
        return "→ breakeven"
    return "initial stops"


def gate_scoring(rows, prices, min_age):
    """The point of the exercise: did the blocks save money or cost it?"""
    today = datetime.date.today()
    scored, unscorable = [], []
    for r in rows:
        act = (r.get("Action") or "").strip().upper()
        if act not in BLOCK_ACTIONS:
            continue
        d = parse_date(r.get("Date"))
        if not d or (today - d).days < min_age:
            continue
        tk = r["Ticker"].strip()
        p0 = num(r.get("Price_At_Decision"))
        if p0 is None:
            unscorable.append((tk, r.get("Date", ""), act))
            continue
        px = prices.get(tk)
        if px is None:
            continue
        scored.append({
            "ticker": tk, "date": d, "action": act,
            "gate": (r.get("Gate_Result") or "").strip(),
            "p0": p0, "px": px, "pct": (px / p0 - 1) * 100,
            "days": (today - d).days,
            "note": (r.get("Notes") or "").strip(),
        })
    return sorted(scored, key=lambda x: x["pct"], reverse=True), unscorable


# ---------------------------------------------------------------------------
# report


def fmt(v, dp=2):
    return "—" if v is None else f"{v:,.{dp}f}"


def pct(v):
    return "—" if v is None else f"{v:+.1f}%"


def build(rows, prices, min_age, today):
    L = [f"# P&L & Gate Scoring — {today}", ""]
    L += ["*Derived from `output/ledger/Gate_Ledger.csv`. Prices fetched live. "
          "Figures are in each line's own trading currency and are **not** converted — "
          "totals across currencies are deliberately omitted rather than silently summed.*", ""]

    # --- realised ---
    rz = realised(rows)
    L += ["---", "", "## Realised — closed positions", ""]
    if rz:
        L += ["| Ticker | Ccy | In | Out | Days | P&L | % |", "|---|---|---|---|---|---|---|"]
        for r in rz:
            L.append(f"| {r['ticker']} | {r['ccy']} | {fmt(r['entry'])} | {fmt(r['exit'])} | "
                     f"{r['days'] if r['days'] is not None else '—'} | "
                     f"{fmt(r['pnl'], 0)} | {pct(r['pct'])} |")
        wins = [r for r in rz if r["pct"] > 0]
        avg_w = sum(r["pct"] for r in wins) / len(wins) if wins else 0
        losses = [r for r in rz if r["pct"] <= 0]
        avg_l = sum(r["pct"] for r in losses) / len(losses) if losses else 0
        bits = [f"**{len(wins)} up / {len(losses)} down**"]
        if wins:
            bits.append(f"average winner {avg_w:+.1f}%")
        if losses:
            bits.append(f"average loser {avg_l:+.1f}%")
        L += ["", " · ".join(bits)]
        if wins and losses and abs(avg_l) > avg_w:
            L += ["", "> ⚠️ **Average loser is larger than average winner.** With the two-stop "
                  "system and the trailing ratchet both in force, this should not happen. "
                  "Check whether stops were actually set at entry, and whether exits are "
                  "happening on the written level or on the second thought."]
    else:
        L += ["*No closed positions with both entry and exit prices recorded.*", "",
              "> Exits are the rows most often skipped, and the only ones that can never be "
              "reconstructed later. Record exit date and price in the same run that sells."]

    # --- unrealised ---
    uz = unrealised(rows, prices)
    L += ["", "---", "", "## Unrealised — open positions", ""]
    if uz:
        L += ["| Ticker | Ccy | Qty | Avg cost | Now | Value | P&L | % | Days | Ratchet says |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in uz:
            L.append(f"| {r['ticker']} | {r['ccy']} | {fmt(r['qty'], 0)} | {fmt(r['avg'])} | "
                     f"{fmt(r['px'])} | {fmt(r['value'], 0)} | {fmt(r['pnl'], 0)} | "
                     f"{pct(r['pct'])} | {r['days'] if r['days'] is not None else '—'} | "
                     f"{ratchet_state(r['pct'])} |")
        ext = [r for r in uz if (r["pct"] or 0) > 15]
        if ext:
            L += ["", f"**EXTENDED (>15% on cost):** {', '.join(r['ticker'] for r in ext)} — "
                  "check each against strategic conviction; up >15% with no corresponding "
                  "weight increase is the EXTENDED flag in the daily run."]
        ratchet_due = [r for r in uz if (r["pct"] or 0) >= 10]
        if ratchet_due:
            L += ["", f"**Ratchet check:** {', '.join(r['ticker'] for r in ratchet_due)} are past "
                  "a milestone. Confirm the stop was actually raised — the ratchet only works "
                  "if it is applied, and it is checked in every run's stop review for a reason."]
    else:
        L += ["*No open positions with quantity and entry price recorded.*"]

    # --- gate scoring ---
    sc, unscorable = gate_scoring(rows, prices, min_age)
    L += ["", "---", "", f"## Gate scoring — blocked ideas ≥{min_age} days old", ""]
    L += ["*Every row here is an idea the gates refused. The question is not whether "
          "each call was right, but whether the **rate** justifies the rules.*", ""]
    if sc:
        L += ["| Ticker | Blocked | Gate | Verdict | Price then | Now | Since | Days |",
              "|---|---|---|---|---|---|---|---|"]
        for r in sc:
            L.append(f"| {r['ticker']} | {r['date']} | {r['gate'] or '—'} | {r['action']} | "
                     f"{fmt(r['p0'])} | {fmt(r['px'])} | {pct(r['pct'])} | {r['days']} |")
        up = [r for r in sc if r["pct"] > 0]
        down = [r for r in sc if r["pct"] <= 0]
        n = len(sc)
        avg = sum(r["pct"] for r in sc) / n
        L += ["", f"**Blocked and went UP:   {len(up)} of {n}  ({len(up)/n*100:.0f}%)**",
              f"**Blocked and went DOWN: {len(down)} of {n}  ({len(down)/n*100:.0f}%)**",
              f"**Average move since the block: {avg:+.1f}%**", ""]
        if avg < 0:
            L += ["→ **The gates saved money over this sample.** The blocked set fell on average; "
                  "buying them would have cost you."]
        else:
            L += ["→ ⚠️ **The blocked set rose on average.** This does *not* automatically mean a "
                  "gate is wrong — a gate that avoids ruin will lose money most of the time and "
                  "still be worth keeping, and blocked names have no position sizing or stop "
                  "attached. But it is the signal to look at **which** gate is doing the "
                  "blocking. Group the rows above by the Gate column: a single check responsible "
                  "for most of the misses is a candidate for re-examination. A check that fires "
                  "rarely and blocks disasters is doing its job."]
        by_gate = {}
        for r in sc:
            by_gate.setdefault(r["gate"] or "unspecified", []).append(r["pct"])
        if len(by_gate) > 1:
            L += ["", "**By gate:**", "", "| Gate | Blocked | Avg move since |", "|---|---|---|"]
            for g, v in sorted(by_gate.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
                L.append(f"| {g} | {len(v)} | {sum(v)/len(v):+.1f}% |")
    else:
        L += [f"*No blocked decisions ≥{min_age} days old with a recorded price yet.*", "",
              "> This section stays empty until the ledger has history. That is expected early "
              "on — it is not a reason to stop logging blocks. It is the reason to start."]

    if unscorable:
        L += ["", f"**⚠️ {len(unscorable)} blocked rows cannot be scored — no "
              "`Price_At_Decision`:**", ""]
        for tk, d, act in unscorable[:15]:
            L.append(f"- {tk} ({d}, {act})")
        L += ["", "*These are permanently lost as evidence. `Price_At_Decision` is mandatory "
              "on every non-ENTERED row for exactly this reason.*"]

    missing = [tk for tk, px in prices.items() if px is None]
    if missing:
        L += ["", "---", "", f"**Price fetch failed:** {', '.join(sorted(missing))} — "
              "these are excluded above rather than estimated."]

    L += ["", "---", "",
          "*Generated by `tools/pnl.py` from the gate ledger. Not financial advice; "
          "verify against your broker before acting. See `DISCLAIMER.md`.*"]
    return "\n".join(L)


# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default=os.path.join(OUTPUT_DIR, "ledger", "Gate_Ledger.csv"))
    ap.add_argument("--out", default=None,
                    help="Default: <output>/reports/PnL_<date>.md")
    ap.add_argument("--min-age", type=int, default=MIN_AGE_DAYS,
                    help=f"Minimum age in days for a blocked row to be scored "
                         f"(default {MIN_AGE_DAYS})")
    ap.add_argument("--offline", action="store_true",
                    help="Skip price fetches. Realised P&L only.")
    ap.add_argument("--no-latest", action="store_true")
    a = ap.parse_args()

    rows = load_ledger(a.ledger)
    today = datetime.date.today().isoformat()

    tickers = set()
    if not a.offline:
        for r in rows:
            act = (r.get("Action") or "").strip().upper()
            if act in ENTRY_ACTIONS and (r.get("Status") or "OPEN").strip().upper() == "OPEN":
                tickers.add(r["Ticker"].strip())
            elif act in BLOCK_ACTIONS:
                d = parse_date(r.get("Date"))
                if d and (datetime.date.today() - d).days >= a.min_age:
                    tickers.add(r["Ticker"].strip())
    prices = fetch_all(sorted(tickers))

    body = build(rows, prices, a.min_age, today)

    outfile = a.out or os.path.join(OUTPUT_DIR, "reports", f"PnL_{today}.md")
    os.makedirs(os.path.dirname(os.path.abspath(outfile)), exist_ok=True)
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(body)

    # Plain copy, not a symlink — a write *to* a symlinked pointer follows the
    # link and destroys the dated file behind it (docs/BACKLOG.md item 19).
    # Every latest*.md in this repo is a copy for that reason.
    if not a.no_latest:
        latest = os.path.join(os.path.dirname(os.path.abspath(outfile)), "latest.md")
        try:
            if os.path.islink(latest):
                os.remove(latest)            # migrate an older symlinked pointer
            with open(latest, "w", encoding="utf-8") as f:
                f.write(body)
        except OSError:
            pass

    print(f"written: {outfile}")
    print(f"  {len(rows)} ledger rows · {len(tickers)} priced · "
          f"{sum(1 for _ in realised(rows))} closed")


if __name__ == "__main__":
    main()
