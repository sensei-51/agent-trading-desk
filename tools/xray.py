#!/usr/bin/env python3
"""
xray.py — sector X-ray and NAV growth for the daily evaluation.

Deterministic arithmetic over the broker holdings CSVs and the sector map. This
is the "graphics" leg of the daily report: where the book sits, by sector, with
bars; and whether it is growing, from a running NAV history. It never judges —
it sums the broker's own numbers and draws what they say.

The price/weight work the evaluation used to do by hand each run — "Index is
23.7% of NAV, Defence 7.7%" — is exactly the arithmetic this script exists to
take over (docs/SYSTEM_MAP.md, "The bar for adding another one").

  1. NAV total, per-currency split and day move.
  2. Sector X-ray — value and % NAV per sector, with an ASCII weight bar
     (each █ = 1% of NAV), sector mapping from input/tracking/sector_map.md.
   3. Portfolio growth — a running NAV history in output/.state/nav_history.json,
      rendered as a sparkline plus a braille line chart (a real line in monospace,
      no images), so growth stays visible in a terminal document.

The value column used is the broker's own sterling conversion per line
("Market Value £"). Rows whose value cell carries no £ are reported as
unconverted and excluded from the totals rather than silently summed.

Inputs   input/*.csv                    broker exports (sterling value per line)
         input/tracking/sector_map.md   ticker -> sector (authoritative)
         output/.state/nav_history.json running NAV history (appended each run)
Output   output/data/xray_<date>.md     dated report (human)
         output/data/xray_<date>.json   structured sidecar (machines — see BACKLOG item 2)
         output/data/xray_latest.md     pointer (a copy, like facts.py)

Usage    python3 tools/xray.py
         python3 tools/xray.py --check-history    # verify only; exit 1 on drift
"""

import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
import heartbeat_radar as hr  # noqa: E402 — path set above

INPUT_DIR = os.environ.get("TP_INPUT", os.path.join(ROOT, "input"))
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))
STATE_DIR = os.path.join(OUTPUT_DIR, ".state")
HISTORY_PATH = os.path.join(STATE_DIR, "nav_history.json")
POSITIONS_PATH = os.path.join(STATE_DIR, "position_history.json")

# No QTY constant exists in the radar's header tables, so it lives here.
QTY_HEADERS = ("qty", "quantity", "shares", "units", "holding")
MOVERS_SHOWN = 12       # rows in the movers table; the rest fold into a total
WEEK_DAYS = 7           # lookback for the second delta column

BAR_SCALE = 30          # sector bar width; each cell = 1% of NAV
GROWTH_BAR = 20         # growth bar width; normalized to the window max
HISTORY_WINDOW = 60     # keep this many NAV points
GROWTH_ROWS = 14        # render this many in the chart
CHART_HEIGHT = 5        # braille chart height in rows (4 dot-rows each)

SPARK_CHARS = "▁▂▃▄▅▆▇█"     # 8-level sparkline ramp, low to high
BRAILLE_OFFSET = 0x2800        # U+2800 + dot bits
BRAILLE_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))


# ---------------------------------------------------------------------------
# holdings values


def parse_qty(cell):
    """Quantity as a float, or None. Needed only to tell a price move from a
    trade: if the share count changed, the value delta is not a gain."""
    if cell is None:
        return None
    txt = re.sub(r"[,\s]", "", str(cell))
    try:
        return float(txt)
    except ValueError:
        return None


def load_rows():
    """[(symbol, value_gbp, sector, currency)] from every real holdings CSV."""
    files, demo = hr.discover_holdings_files()
    smap = hr.load_sector_map()
    out, unconverted, no_sector, detections = [], [], [], []

    for path in files:
        base = os.path.basename(path)
        rows = hr.read_csv_rows(path)
        if not rows:
            detections.append((base, "empty"))
            continue
        heads = list(rows[0].keys())
        tkcol = hr.pick_column(heads, hr.TICKER_HEADERS)
        if not tkcol:
            detections.append((base, "no ticker column"))
            continue
        qcol = hr.pick_column(heads, QTY_HEADERS)
        vcol, native = hr.find_sterling_column(heads)
        if not vcol:
            detections.append((base, f"no market-value column ({len(rows)} rows, skipped)"))
            continue
        detections.append((base, f"value={vcol!r}" + (" (native, unconverted)" if native else "")))

        for row in rows:
            sym = (row.get(tkcol) or "").strip().upper()
            if not sym:
                continue  # the "Totals" / currency-split rows
            val, conv = hr.parse_pounds(row.get(vcol))
            if val is None:
                continue
            if not conv:
                unconverted.append((sym, row.get(vcol)))
                continue
            sec = smap.get(sym) or smap.get(sym + ".L")
            if not sec:
                no_sector.append(sym)
            out.append((sym, val, sec or "Unclassified", base, parse_qty(
                row.get(qcol) if qcol else None)))
    return out, unconverted, no_sector, detections, demo


# ---------------------------------------------------------------------------
# NAV history


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f).get("history", [])
    except (ValueError, OSError):
        return []


def record_history(nav, date_str=None):
    """Append a NAV point keyed on the DATA date (dedupe on date), persist.

    The key is the broker export's date, not the run date. A Tuesday run over
    Monday evening's export updates Monday's point instead of writing a
    duplicate flat Tuesday point — the chart shows what the data says, not how
    often the script ran. (Observed 2026-08-18: the same NAV recorded for both
    the 17th and 18th off one unchanged export, rendering a -0.0% day that
    never happened.)
    """
    hist = load_history()
    key = date_str or datetime.date.today().isoformat()
    # Drop the keyed date AND any point later than the data date — a later
    # point can only be a leftover from the old run-date keying (the bogus
    # flat point this change removes).
    hist = [p for p in hist if p.get("date") != key and p.get("date", "") <= key]
    hist.append({"date": key, "nav_gbp": round(nav, 2)})
    hist.sort(key=lambda p: p.get("date", ""))
    hist = hist[-HISTORY_WINDOW:]
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump({"history": hist}, f, indent=1)
    return hist


def load_positions_history():
    if not os.path.exists(POSITIONS_PATH):
        return []
    try:
        with open(POSITIONS_PATH, encoding="utf-8") as f:
            return json.load(f).get("history", [])
    except (ValueError, OSError):
        return []


def record_positions(rows, date_str=None):
    """Append {symbol: {v, q}} keyed on the DATA date.

    Same keying rule as `record_history`, for the same reason: a Tuesday run
    over Monday's unchanged export must update Monday's point, not invent a
    flat Tuesday one. Symbols are aggregated across accounts — a line held in
    two brokers is one exposure for the purposes of "what moved".
    """
    agg = {}
    for sym, val, _sec, _base, *rest in rows:
        qty = rest[0] if rest else None
        e = agg.setdefault(sym, {"v": 0.0, "q": None})
        e["v"] += val
        if qty is not None:
            e["q"] = (e["q"] or 0.0) + qty
    for e in agg.values():
        e["v"] = round(e["v"], 2)

    hist = load_positions_history()
    key = date_str or datetime.date.today().isoformat()
    hist = [p for p in hist if p.get("date") != key and p.get("date", "") <= key]
    hist.append({"date": key, "positions": agg})
    hist.sort(key=lambda p: p.get("date", ""))
    hist = hist[-HISTORY_WINDOW:]
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(POSITIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({"history": hist}, f, indent=1)
    return hist


def _point_before(hist, key):
    """Most recent entry strictly before `key`, or None."""
    prior = [p for p in hist if p.get("date", "") < key]
    return prior[-1] if prior else None


def _point_on_or_before(hist, key):
    """Most recent entry at or before `key`, or None when history predates it."""
    got = [p for p in hist if p.get("date", "") <= key]
    return got[-1] if got else None


def movers_section(rows, poshist, data_date):
    """Per-position move since the previous export, and over ~a week.

    THE TRAP THIS AVOIDS: value change is not P&L. Buy £5,000 of a name and its
    value rises £5,000 with no gain whatsoever. So quantity is stored alongside
    value, and any line whose share count moved is marked `TRADE` and reported
    on its per-unit price instead — never as a £ gain.
    """
    key = data_date or datetime.date.today().isoformat()
    cur = {}
    for sym, val, _sec, _base, *rest in rows:
        qty = rest[0] if rest else None
        e = cur.setdefault(sym, {"v": 0.0, "q": None})
        e["v"] += val
        if qty is not None:
            e["q"] = (e["q"] or 0.0) + qty

    L = ["", "---", "", "## Movers — what changed since the last export", ""]

    prev = _point_before(poshist, key)
    if not prev:
        L += ["*No prior position snapshot — this run establishes the baseline. "
              "The next export produces the first deltas.*", ""]
        return L

    wk_cut = (datetime.date.fromisoformat(key)
              - datetime.timedelta(days=WEEK_DAYS)).isoformat()
    wk = _point_before(poshist, wk_cut) or _point_on_or_before(poshist, wk_cut)

    pp, wp = prev.get("positions", {}), (wk or {}).get("positions", {})
    moved, new, exited, traded = [], [], [], []

    for sym, e in cur.items():
        old = pp.get(sym)
        if old is None:
            new.append((sym, e["v"]))
            continue
        qty_changed = (e["q"] is not None and old.get("q") is not None
                       and abs(e["q"] - old["q"]) > 1e-9)
        dv = e["v"] - old["v"]
        dp = (dv / old["v"] * 100) if old.get("v") else None
        # per-unit move survives a trade; £ delta does not
        pu = None
        if e["q"] and old.get("q"):
            a, b = e["v"] / e["q"], old["v"] / old["q"]
            pu = (a - b) / b * 100 if b else None
        wold = wp.get(sym)
        wdp = None
        if wold and wold.get("v"):
            if e["q"] and wold.get("q"):
                a, b = e["v"] / e["q"], wold["v"] / wold["q"]
                wdp = (a - b) / b * 100 if b else None
            elif not qty_changed:
                wdp = (e["v"] - wold["v"]) / wold["v"] * 100
        rec = (sym, e["v"], dv, dp, pu, wdp, qty_changed)
        (traded if qty_changed else moved).append(rec)

    for sym, old in pp.items():
        if sym not in cur:
            exited.append((sym, old.get("v")))

    L += [f"*Against the **{prev['date']}** export"
          + (f"; week column against **{wk['date']}**" if wk else "")
          + ". A line whose share count changed is marked `TRADE` and shown on "
            "**price per unit**, because buying more is not a gain.*", "",
          "| Line | Value £ | Δ £ | Δ % | Week % | |",
          "|---|---|---|---|---|---|"]

    ordered = sorted(moved, key=lambda r: -abs(r[2] or 0))
    shown, rest = ordered[:MOVERS_SHOWN], ordered[MOVERS_SHOWN:]
    for sym, v, dv, dp, pu, wdp, _ in shown:
        arrow = "▲" if (dv or 0) > 0 else ("▼" if (dv or 0) < 0 else "·")
        L.append(f"| {sym} | {fmt(v)} | {dv:+,.0f} | {pct(dp)} | {pct(wdp)} | {arrow} |")
    for sym, v, dv, dp, pu, wdp, _ in sorted(traded, key=lambda r: -abs(r[2] or 0)):
        L.append(f"| {sym} | {fmt(v)} | `TRADE` | {pct(pu)} | {pct(wdp)} | ⇄ |")
    if rest:
        tot = sum(r[2] or 0 for r in rest)
        L.append(f"| *{len(rest)} smaller move(s)* | | {tot:+,.0f} | | | |")

    net = sum(r[2] or 0 for r in moved)
    L += ["", f"**Net move on unchanged lines: £{net:+,.0f}.** "
          f"Traded lines are excluded — their value change mixes price with "
          f"the trade itself."]
    if new:
        L.append("**New:** " + ", ".join(f"{s} ({fmt(v)})" for s, v in
                                         sorted(new, key=lambda r: -r[1])) + ".")
    if exited:
        L.append("**Gone:** " + ", ".join(f"{s} (was {fmt(v)})" for s, v in
                                          sorted(exited, key=lambda r: -(r[1] or 0))) + ".")
    L.append("")
    return L


def sparkline(vals):
    """8-level unicode sparkline over vals (lowest char to highest char)."""
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    return "".join(SPARK_CHARS[min(7, round((v - lo) / span * 7))] for v in vals)


def braille_line_chart(vals, height=CHART_HEIGHT):
    """Connected line through vals as a braille pre-block; None if < 2 points.

    Each braille cell is a 2x4 dot grid; one dot-column per point, dots joined
    with Bresenham, so the result is an actual line in pure unicode/monospace.
    """
    n = len(vals)
    if n < 2:
        return None
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    rows = height * 4
    pts = []
    for i, v in enumerate(vals):
        x = 2 * i
        y = rows - 1 - round((v - lo) / span * (rows - 1))
        pts.append((x, y))

    dots = set()

    def put(x, y):
        if 0 <= x and 0 <= y < rows:
            dots.add((x, y))

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
        dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
        err, x, y = dx + dy, x0, y0
        while True:
            put(x, y)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    maxx = max(x for x, _ in dots)
    ccols = maxx // 2 + 1
    grid = [[0] * ccols for _ in range(rows // 4)]
    for x, y in dots:
        cr, cc = y // 4, x // 2
        br, bc = y % 4, x % 2
        grid[cr][cc] |= BRAILLE_BITS[br][bc]
    return ["".join(chr(BRAILLE_OFFSET + cell) for cell in row) for row in grid]


def growth_points(hist):
    """[(date, nav, delta_pct, spark)] rendered rows for the growth table."""
    window = hist[-GROWTH_ROWS:]
    if not window:
        return []
    if len(window) == 1:
        return [(window[0]["date"], window[0]["nav_gbp"], None, "█")]
    lo = min(p["nav_gbp"] for p in window)
    hi = max(p["nav_gbp"] for p in window)
    span = (hi - lo) or 1
    spark = sparkline([p["nav_gbp"] for p in window])
    out = []
    for i, p in enumerate(window):
        if i == 0:
            delta = None
        else:
            prev = window[i - 1]["nav_gbp"]
            delta = (p["nav_gbp"] / prev - 1) * 100 if prev else None
        out.append((p["date"], p["nav_gbp"], delta, spark[i]))
    return out


# ---------------------------------------------------------------------------
# report


def fmt(v, dp=0, suffix=""):
    return f"{v:,.{dp}f}{suffix}" if isinstance(v, (int, float)) else "—"


def pct(v, dp=1):
    return "—" if v is None else f"{v:+.{dp}f}%"


def render(rows, hist, demo, today, data_date=None, no_sector=None,
           poshist=None):
    total = sum(v for _, v, *_ in rows)
    by_sec = {}
    for _, v, sec, *_ in rows:
        by_sec[sec] = by_sec.get(sec, 0) + v
    ordered = sorted(by_sec.items(), key=lambda kv: kv[1], reverse=True)

    L = [f"# Sector X-ray — {today}", ""]
    if demo:
        L += ["> ⚠️ **DEMO DATA.** No real holdings CSV found; an *.example.csv file is in input/.", ""]
    if data_date and data_date != today:
        L += [f"> ⚠️ **STALE EXPORT.** Broker CSV last saved **{data_date}** — "
              f"values below are that day's, not today's. NAV history is keyed "
              f"on the export date, so no new point was recorded for {today}.", ""]
    if no_sector:
        names = ", ".join(sorted(set(no_sector)))
        L += [f"> ⛔ **{len(set(no_sector))} HELD name(s) have no `sector_map.md` row** "
              f"and read as Unclassified: {names}. Every sector weight below is "
              f"understated by their value. Add the rows before trusting this table.", ""]
    L += [f"**NAV £{total:,.0f}** over {len(rows)} holdings"
          + (f" *(export dated {data_date})*." if data_date else "."),
          "Value is the broker's own sterling conversion per line (`Market Value £`). "
          "Sector mapping: `input/tracking/sector_map.md`. **Each █ = 1% of NAV** "
          "(bar width 30).",
          "",
          "| Sector | Value £ | % NAV | Weights |",
          "|---|---|---|---|"]

    for sec, v in ordered:
        p = v / total * 100 if total else 0
        n = max(1, min(BAR_SCALE, round(p)))
        bar = "█" * n + "░" * (BAR_SCALE - n)
        L.append(f"| {sec} | {fmt(v)} | {p:5.1f}% | {bar} |")

    L += movers_section(rows, poshist or [], data_date)

    L += ["", "---", "", "## Portfolio growth", ""]
    g = growth_points(hist)
    if g:
        L += ["| Date | NAV £ | Δ | Run |", "|---|---|---|---|"]
        for d, nav, delta, spark in g:
            L.append(f"| {d} | {fmt(nav)} | {pct(delta)} | {spark} |")
        if len(hist) >= 2:
            chart = braille_line_chart([p[1] for p in g])
            first, last = g[0][0], g[-1][0]
            w = len(chart[0]) if chart else 1
            footer = f"{first} … {last}" if len(first) + len(last) + 1 > w \
                else first + " " * (w - len(first) - len(last)) + last
            L += ["", "<pre>", *[ln.rstrip() for ln in chart], footer, "</pre>"]
        if len(hist) == 1:
            L += ["", "*History starts with this run — the chart will grow one run at a time.*"]
    else:
        L += ["*No NAV history yet.*"]

    return "\n".join(L), total, ordered


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-history", action="store_true",
                    help="do not append to nav_history.json (report only)")
    ap.add_argument("--check-history", action="store_true",
                    help="verify nav_history.json parses and matches today; exit 1 if not")
    ap.add_argument("--allow-unclassified", action="store_true",
                    help="do not exit non-zero when a HELD name has no sector_map row")
    a = ap.parse_args()

    rows, unconverted, no_sector, detections, demo = load_rows()
    if not rows:
        print("no holdings rows found — is a broker CSV in input/?", file=sys.stderr)
        return 1

    for base, note in detections:
        print(f"[xray] {base}: {note}")
    if unconverted:
        print(f"[xray] ⚠️  {len(unconverted)} row(s) not in £ (excluded from totals): "
              + ", ".join(f"{s} {v}" for s, v in unconverted[:8]))
    if no_sector:
        print(f"[xray] ⛔  {len(set(no_sector))} HELD name(s) have no sector_map row → "
              "Unclassified: " + ", ".join(sorted(set(no_sector))))
        print("[xray]     a held name with no sector silently distorts every "
              "weight and the bloc-ceiling read — add the rows to "
              "input/tracking/sector_map.md")

    # The data date is the broker export's save date, not the run date. Stamp
    # it, key NAV history on it, and warn when it lags the run.
    files, _ = hr.discover_holdings_files()
    data_date = None
    if files:
        data_date = datetime.date.fromtimestamp(
            max(os.path.getmtime(p) for p in files)).isoformat()

    total = sum(v for _, v, *_ in rows)
    hist = load_history() if not a.check_history else load_history()
    if a.check_history:
        today = datetime.date.today().isoformat()
        present = any(p.get("date") == today for p in hist)
        if not hist:
            print("nav_history.json: empty or missing", file=sys.stderr)
            return 1
        print(f"nav_history.json: {len(hist)} points, "
              f"last={hist[-1].get('date')} nav=£{hist[-1].get('nav_gbp'):,.0f}")
        print(f"  today {today}: {'present' if present else 'absent'}")
        return 0

    # Read the position snapshot BEFORE recording today's, or the deltas are
    # all zero — today would be compared against itself.
    poshist = load_positions_history()

    if not a.no_history:
        hist = record_history(total, data_date)
        record_positions(rows, data_date)
    else:
        hist = load_history()

    body, total, ordered = render(rows, hist, demo, datetime.date.today().isoformat(),
                                  data_date=data_date, no_sector=no_sector,
                                  poshist=poshist)

    out_dir = os.path.join(OUTPUT_DIR, "data")
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.date.today().isoformat()
    for p in (os.path.join(out_dir, f"xray_{today}.md"),
              os.path.join(out_dir, "xray_latest.md")):
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)

    # ---- structured sidecar ------------------------------------------------
    # The .md is for a human; this is for the machines. `eval_reviewer` check
    # [16] used to assert the report reproduced each .md row BYTE-FOR-BYTE —
    # including the ████░░░ bar art and the irregular `|  23.9% |` padding — so
    # a re-render that changed one space read as a falsified table. It now
    # compares the numbers here instead, and the bar art is free to be art.
    #
    # Same pair as facts.py / fundamentals.py ship (.csv + .md). See
    # docs/BACKLOG.md item 2: the evaluation a human reads stays prose; every
    # other cross-agent handoff carries a structured form.
    payload = {
        "date": today,
        "export_date": data_date,
        "nav_gbp": round(total, 2),
        "holdings": len(rows),
        "unclassified": sorted(set(no_sector)),
        "sectors": [{"sector": sec,
                     "value_gbp": round(v, 2),
                     "pct_nav": round(v / total * 100, 2) if total else 0.0}
                    for sec, v in ordered],
    }
    for p in (os.path.join(out_dir, f"xray_{today}.json"),
              os.path.join(out_dir, "xray_latest.json")):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
            f.write("\n")

    top = ", ".join(f"{sec} {v/total*100:.0f}%" for sec, v in ordered[:3])
    print(f"Wrote {os.path.join(out_dir, 'xray_latest.md')}")
    print(f"  NAV £{total:,.0f} · {len(rows)} holdings · top: {top}"
          + (f" · export dated {data_date}" if data_date else ""))
    if no_sector and not a.allow_unclassified:
        # A held name with no sector row is bad input, not a cosmetic gap —
        # fail the step so run_daily halts instead of shipping a wrong table.
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
