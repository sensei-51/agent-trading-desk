#!/usr/bin/env python3
"""
scorecard.py — the public track record, in counts and percentages only.

    python3 tools/scorecard.py              # regenerate the README block
    python3 tools/scorecard.py --check      # verify it is current; exit 1 if stale
    python3 tools/scorecard.py --offline    # skip live fetches (closed trades only)

WHY THIS EXISTS

The repo used to publish `output/` wholesale — evaluations, the ledger, the P&L
report — on the argument that a reader cannot audit the gates against an empty
folder. That argument is still right, and the way it was implemented was still
wrong: those files carry `Qty` and absolute cash, and a position size plus a
price is a sleeve size. Publishing the working papers to prove the method works
disclosed how much money was behind it, which is a personal-safety question and
not a design preference.

This script resolves the two. It reads the private ledger and emits **only
counts, percentages and ratios** — never a quantity, never a currency amount.
A 62% win rate over 80 trades reads identically whether the sleeve is £10k or
£10m, so the evidence survives intact while the number that matters to a
burglar does not exist anywhere in the output.

WHAT IS DELIBERATELY OMITTED, AND WHY

  Qty, Value, Cost, absolute P&L   a size. The whole point.
  entry and exit prices            not secret in themselves, but a cost basis
                                   per name is more personal than the % move
                                   and the % is what the reader actually needs.
  open positions, per name         a live holdings list with stop levels tells
                                   a reader what to front-run. Closed trades are
                                   history; open ones are a position. Only the
                                   COUNT of open lines is published.

The guard at the bottom is not decoration. It re-reads the rendered block and
refuses to write if a currency symbol or a bare quantity survived — because the
failure mode here is not a bug that shows up in a test, it is one line of a
future edit that quietly reintroduces a number nobody re-reads before pushing.

Output goes between the SCORECARD markers in README.md, so the track record
sits on the front page rather than in a file nobody opens.
"""

import argparse
import collections
import datetime
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# Reuse the P&L module's parsers rather than writing a second ledger reader.
# Two parsers for one file is how the private and public views drift apart.
import pnl  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "engine"))
import heartbeat_radar as hr  # noqa: E402

LEDGER = os.path.join(ROOT, "output", "ledger", "Gate_Ledger.csv")
README = os.path.join(ROOT, "README.md")
START = "<!-- SCORECARD:START -->"
END = "<!-- SCORECARD:END -->"

def day_precise(s):
    """True only if the ledger date names a specific day.

    `~2026-08-13` is a day the operator is fairly sure of; `~2026-07` is a month.
    Estimating an exit off a month-only date means picking one close out of ~22,
    and on a volatile name the choice can flip the sign of the result. A trade
    that cannot be dated is left unscored rather than guessed at.
    """
    t = (s or "").strip().lstrip("~")
    try:
        datetime.datetime.strptime(t, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def eod_close(ticker, on):
    """Close on `on`, or the last session before it. None if unavailable.

    Reuses the radar's `fetch_bars` rather than issuing a second kind of price
    request: it is cached, it is split-adjusted, and it already refuses to serve
    stale history as if it were current.
    """
    try:
        bars, err = hr.fetch_bars(ticker)
    except Exception:
        return None
    if not bars or err:
        return None
    best = None
    for t, c in zip(bars["ts"], bars["c"]):
        d = datetime.date.fromtimestamp(t)
        if d <= on:
            best = c
        else:
            break
    return best


def estimate_exits(rows, offline):
    """Exit prices the ledger never recorded, inferred from end-of-day closes.

    WHY THIS IS NOT WRITTEN BACK TO THE LEDGER. The ledger is append-only and it
    is the audit record — the one artefact whose whole value is that every row
    is something that actually happened. An estimate stored there becomes
    indistinguishable from a logged fact on the next read, by anyone, forever.
    So the estimate lives here, is recomputed on every build, and is marked `~`
    wherever it surfaces. If you want a real number in the ledger, put the real
    fill price in the ledger.

    Returns {ticker: (exit_price, exit_date)} for rows that can be estimated.
    """
    if offline:
        return {}
    out = {}
    for r in rows:
        act = (r.get("Action") or "").strip().upper()
        # EXITED only. `SELL` is a *signal* action in this ledger — the sibling of
        # BUY-TRIGGER — and the rows carrying it are still `Status: OPEN`, meaning
        # the call was made and the fill has not been recorded. Scoring one as a
        # completed trade invents an exit that never happened, in the one document
        # whose entire value is that it does not do that.
        if act not in pnl.EXIT_ACTIONS:
            continue
        if pnl.num(r.get("Exit_Price")) is not None:
            continue
        tk = r["Ticker"].strip()
        # An explicit Exit_Date wins; otherwise the exit row's own Date is when
        # the decision was taken, which is the best available stand-in.
        raw = r.get("Exit_Date") if day_precise(r.get("Exit_Date")) else r.get("Date")
        if not day_precise(raw):
            continue
        on = pnl.parse_date(raw)
        px = eod_close(tk, on)
        if px is not None:
            out[tk] = (px, on)
    return out


def closed_trades(rows, est=None):
    """Ticker-level closed trades: how long held, and what the trade did.

    `pnl.realised` already resolves the entry date from the earliest ENTERED row
    rather than the exit row's own date, which is the subtle part. Everything it
    returns that implies a size (`qty`, `pnl`) is dropped here.
    """
    est = est or {}
    out, seen = [], set()
    for t in pnl.realised(rows):
        seen.add(t["ticker"])
        out.append({"ticker": t["ticker"], "days": t["days"],
                    "pct": t["pct"], "approx": False})

    # Rows the ledger could not score, rescued by an end-of-day close.
    first_entry = {}
    for r in rows:
        if (r.get("Action") or "").strip().upper() in pnl.ENTRY_ACTIONS:
            tk, d = r["Ticker"].strip(), pnl.parse_date(r.get("Date"))
            e = pnl.num(r.get("Avg_Entry"))
            if d and e and (tk not in first_entry or d < first_entry[tk][0]):
                first_entry[tk] = (d, e)
    for tk, (px, on) in est.items():
        if tk in seen or tk not in first_entry:
            continue
        d_in, entry = first_entry[tk]
        out.append({"ticker": tk, "days": (on - d_in).days,
                    "pct": (px / entry - 1) * 100, "approx": True})
    return sorted(out, key=lambda x: x["pct"], reverse=True)


def unscorable_exits(rows, scored=()):
    """Closed positions that cannot be scored because no exit price was logged.

    Reported rather than skipped. A closed trade missing from the table looks
    like a trade that never happened, which flatters the record by omission —
    the same failure the ledger exists to prevent for blocks.

    `scored` is the set of tickers already in the table, and excluding it is not
    cosmetic. A completed trade occupies TWO rows: the ENTERED row, flipped to
    `Status: CLOSED` when the position came off, and the EXITED row carrying the
    exit price. Counting rows rather than positions therefore reported one
    "unscorable" per fully-scored trade — on the day this was fixed, seven trades
    were scored correctly above a warning that four could not be, and all four
    were their own entry legs. An alarm that fires on success is worse than none,
    because the next real one gets ignored.
    """
    seen = set(scored)
    n = 0
    for r in rows:
        act = (r.get("Action") or "").strip().upper()
        closed = (r.get("Status") or "").strip().upper() == "CLOSED"
        if act not in pnl.EXIT_ACTIONS and not (closed and act in pnl.ENTRY_ACTIONS):
            continue
        if r["Ticker"].strip() in seen:
            continue
        if pnl.num(r.get("Exit_Price")) is None or pnl.num(r.get("Avg_Entry")) is None:
            n += 1
    return n


# The two gate cards, from rules/02_SLEEVE_RULES.md. Checks 3, 4, 5 and 7 are the
# same test on both; 1, 2 and 6 are deliberately different, and 8 is ETF-only —
# which is exactly why the counts below are kept apart. Summing "#6" across both
# cards would add "valuation headroom" to "premium / extension" and report a
# number describing neither.
CARD_CHECKS = {
    "S": {1: "Composite score", 2: "Pillar floors", 3: "MA gatekeeper",
          4: "Volume character", 5: "Event window", 6: "Valuation headroom",
          7: "Entry discipline"},
    "E": {1: "Sector thesis", 2: "Fund structure", 3: "MA gatekeeper",
          4: "Volume character", 5: "Event window", 6: "Premium / extension",
          7: "Entry discipline", 8: "Overlap"},
}
CARD_NAME = {"S": "Stock", "E": "ETF"}


def rule_hits(rows):
    """Which gate check actually fires, split by card.

    The card letter is found by SEARCH, not by matching the start of the field.
    Roughly a sixth of the ledger's verdicts are written `GATE: S 6/7 — fail #6`
    rather than `S fail #6`, and anchoring to position 0 filed every one of them
    under an unknown card — 13 of 33 fails, silently, in a table whose whole
    purpose is to say which rules bind.
    """
    c = collections.Counter()
    for r in rows:
        g = r.get("Gate_Result") or ""
        m = re.search(r"\b([SE])\b", g)
        if not m:
            continue
        card = m.group(1)
        for n in re.findall(r"#(\d+)", g):
            c[(card, int(n))] += 1
    return c.most_common()


def bar(n, scale, width=18):
    """A █/░ magnitude bar in the x-ray's house style.

    Used for unsigned counts, where a colour would imply a verdict the number
    does not carry: "this check blocked 12 things" is neither good nor bad.
    """
    filled = 0 if scale <= 0 else min(width, int(round(n / scale * width)))
    return "█" * filled + "░" * (width - filled)


def diverging(pct, span, blocks="🟩", loss_blocks="🟥", width=7):
    """(left_cell, right_cell) for a centre-out bar across two table columns.

    Markdown cannot colour a cell, but it can align one — so the split is the
    mechanism, not a workaround. The left column is right-aligned and the right
    column left-aligned, which puts both bars against the shared border and lets
    losses grow outward to the left while gains grow to the right. Reading down
    the middle of the table then shows the sign at a glance, before any number
    is parsed.

    A non-zero result always gets at least one block: rounding a real +1.6% to
    an empty cell would render a win as nothing at all.
    """
    if span <= 0 or pct == 0:
        return "", ""
    n = max(1, min(width, int(round(abs(pct) / span * width))))
    return (loss_blocks * n, "") if pct < 0 else ("", blocks * n)


def count_evaluations():
    """Dated evaluations that still hold an evaluation.

    A tombstone counts as a file but not as evidence. `evaluation_2026-08-22.md`
    is a marker left where an agent wrote today's report through a stale symlink
    and destroyed the day's work; publishing it in the run count would overstate
    the coverage this track record rests on by exactly one day.
    """
    out = os.path.join(ROOT, "output")
    if not os.path.isdir(out):
        return 0
    n = 0
    for f in os.listdir(out):
        if not (f.startswith("evaluation_") and f.endswith(".md")):
            continue
        try:
            with open(os.path.join(out, f), encoding="utf-8") as fh:
                head = fh.read(200)
        except OSError:
            continue
        if head.lstrip().startswith("<!-- LOST:"):
            continue
        n += 1
    return n


def coverage(rows):
    dates = [d for d in (pnl.parse_date(r.get("Date")) for r in rows) if d]
    evals = count_evaluations()
    open_lines = len({r["Ticker"].strip() for r in rows
                      if (r.get("Status") or "").strip().upper() == "OPEN"
                      and (r.get("Action") or "").strip().upper() in pnl.ENTRY_ACTIONS})
    return {
        "decisions": len(rows),
        "names": len({r["Ticker"].strip() for r in rows}),
        "first": min(dates) if dates else None,
        "days": (datetime.date.today() - min(dates)).days if dates else 0,
        "evals": evals,
        "open_lines": open_lines,
    }


def render(rows, prices, min_age, today, est=None):
    L = [START, "", "## Track record", "",
         "*Counts and percentages only — no position sizes and no cash figures appear "
         "anywhere in this section, by construction. Regenerated by "
         "[`tools/scorecard.py`](tools/scorecard.py) from the private gate ledger; "
         f"last built {today.isoformat()}.*", ""]

    cov = coverage(rows)
    L += [f"**{cov['decisions']} decisions logged** across **{cov['names']} names** "
          f"over **{cov['days']} days** · {cov['evals']} published evaluations · "
          f"{cov['open_lines']} lines currently open", ""]

    # ---- closed trades -----------------------------------------------------
    est = est or {}
    ct = closed_trades(rows, est)
    missing = unscorable_exits(rows, {t['ticker'] for t in ct})
    L += ["### Closed trades", ""]
    if ct:
        span = max(abs(t["pct"]) for t in ct) or 1
        L += ["| Ticker | Held | Loss | Gain | Result |",
              "|---|---|---:|:---|---:|"]
        for t in ct:
            days = f"{t['days']}d" if t["days"] is not None else "—"
            mark = "~" if t["approx"] else ""
            lo, hi = diverging(t["pct"], span)
            L.append(f"| **{t['ticker']}** | {days} | {lo} | {hi} "
                     f"| {mark}{t['pct']:+.1f}% |")
        wins = [t["pct"] for t in ct if t["pct"] > 0]
        loss = [t["pct"] for t in ct if t["pct"] <= 0]
        held = [t["days"] for t in ct if t["days"] is not None]
        if any(t["approx"] for t in ct):
            L += ["", "*`~` marks a result whose exit price was not logged and has "
                      "been inferred from the end-of-day close on the exit date. "
                      "Estimated at build time and never written back to the "
                      "ledger — the ledger records what happened, not what was "
                      "reconstructed afterwards.*"]
        L += ["", f"🟩 **{len(wins)} up** / 🟥 **{len(loss)} down** — "
                  f"win rate {100 * len(wins) / len(ct):.0f}%"
                  + (f" · average winner {statistics.mean(wins):+.1f}%" if wins else "")
                  + (f" · average loser {statistics.mean(loss):+.1f}%" if loss else "")
                  + (f" · median hold {statistics.median(held):.0f}d" if held else "")]
    else:
        L += ["*No closed trade carries both an entry and an exit price yet, so none "
              "can be scored.*"]
    if missing > 0:
        L += ["", f"> **{missing} closed position(s) remain unscorable** — the exit row "
                  "carries no `Exit_Price`. They are counted here rather than dropped, "
                  "because a trade that silently vanishes from a track record flatters "
                  "it. Fill the exit prices in and they appear above."]
    L += [""]

    # ---- gate effectiveness ------------------------------------------------
    scored, unscorable = pnl.gate_scoring(rows, prices, min_age)
    L += ["### Gate effectiveness", "",
          "*Every row is an idea the rules **refused**. The question is not whether "
          "each call was right, but whether the rate justifies the rules — a gate that "
          "blocks winners costs money silently.*", ""]
    if scored:
        rose = [s for s in scored if s["pct"] > 0]
        gspan = max(abs(x["pct"]) for x in scored) or 1
        L += ["| Ticker | Blocked by | Since | Rule saved | Rule cost | Moved |",
              "|---|---|---|---:|:---|---:|"]
        for s in scored:
            # Colour is INVERTED against the trades table, deliberately. A
            # blocked idea that rose is the gate costing money (🟥); one that
            # fell is the gate earning its place (🟩). The bar answers "was the
            # RULE right", which is the only question this section asks.
            lo, hi = diverging(-s["pct"], gspan, blocks="🟩", loss_blocks="🟥")
            L.append(f"| **{s['ticker']}** | {s['gate'] or '—'} | {s['days']}d "
                     f"| {hi} | {lo} | {s['pct']:+.1f}% |")
        L += ["", f"**{len(rose)} of {len(scored)} blocked ideas rose anyway** "
                  f"({100 * len(rose) / len(scored):.0f}%) — "
                  f"the gates avoided {len(scored) - len(rose)}."]
    else:
        blocked = sum(1 for r in rows
                      if (r.get("Action") or "").strip().upper() in pnl.BLOCK_ACTIONS)
        L += [f"*{blocked} blocked decisions are logged with a decision price, but none "
              f"is yet {min_age} days old — too recent to have been right or wrong. "
              "This section fills itself in as they age.*"]
    if unscorable:
        L += ["", f"> {len(unscorable)} blocked decision(s) carry no price and can "
                  "never be scored."]
    L += [""]

    # ---- rule hits ---------------------------------------------------------
    hits = rule_hits(rows)
    if hits:
        top = hits[0][1]
        L += ["### Which rules actually bind", "",
              "*Gate-card checks by how often they were the reason for a refusal — "
              "stock and ETF cards counted separately, because checks 1, 2 and 6 "
              "are different tests on each. No name attached: this is about the "
              "rules, not the roster.*", "",
              "| Card | Check | Blocked | |", "|---|---|---:|---|"]
        for (card, n), c in hits:
            icon = "📈" if card == "S" else "🧺"
            name = CARD_CHECKS.get(card, {}).get(n, "—")
            L.append(f"| {icon} {CARD_NAME.get(card, card)} | **#{n}** {name} "
                     f"| {c} | `{bar(c, top, 14)}` |")
        L += [""]

    L += [END]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# the guard

CURRENCY = re.compile(r"[£$€]\s?\d|\b\d[\d,]*\.\d{2}\b")
QTY_WORDS = re.compile(r"\b(qty|quantity|book cost|market value|nav|sleeve size)\b", re.I)


def guard(block):
    """Refuse to emit anything that implies a size.

    Structural, and deliberately paranoid about its own future: the risk is not
    today's code but a later edit that adds one helpful column. A `%` and a count
    can never reconstruct a sleeve; a price times a quantity always can.
    """
    problems = []
    for m in CURRENCY.finditer(block):
        problems.append(f"currency-shaped figure {m.group(0)!r}")
    for m in QTY_WORDS.finditer(block):
        problems.append(f"size-implying word {m.group(0)!r}")
    return problems


def splice(readme_text, block):
    if START not in readme_text or END not in readme_text:
        raise ValueError(f"README.md has no {START} / {END} markers")
    head, rest = readme_text.split(START, 1)
    _, tail = rest.split(END, 1)
    return head + block + tail


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    ap.add_argument("--check", action="store_true",
                    help="verify the README block is current; exit 1 if stale")
    ap.add_argument("--offline", action="store_true",
                    help="skip live price fetches (closed trades still scored)")
    ap.add_argument("--min-age", type=int, default=pnl.MIN_AGE_DAYS)
    a = ap.parse_args()

    rows = pnl.load_ledger(LEDGER)
    prices = {}
    if not a.offline:
        blocked = {r["Ticker"].strip() for r in rows
                   if (r.get("Action") or "").strip().upper() in pnl.BLOCK_ACTIONS}
        prices = pnl.fetch_all(sorted(blocked))

    est = estimate_exits(rows, a.offline)
    if est:
        print(f"[scorecard] inferred {len(est)} exit price(s) from end-of-day closes: "
              + ", ".join(sorted(est)))
    block = render(rows, prices, a.min_age, datetime.date.today(), est)

    problems = guard(block)
    if problems:
        print("⛔ scorecard guard FAILED — refusing to write:", file=sys.stderr)
        for p in sorted(set(problems)):
            print(f"   - {p}", file=sys.stderr)
        return 1

    text = open(README, encoding="utf-8").read()
    updated = splice(text, block)
    if a.check:
        if updated != text:
            print("OUT  README scorecard block is stale — run: "
                  "python3 tools/scorecard.py", file=sys.stderr)
            return 1
        print("OK   README scorecard block is current")
        return 0
    if updated == text:
        print("OK   README scorecard block already current")
        return 0
    open(README, "w", encoding="utf-8").write(updated)
    print(f"WROTE README scorecard block ({len(block.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
