#!/usr/bin/env python3
"""
calibrate_derived.py — score the `derived` provider against a curated run.

The derived provider's band edges (providers/fundamentals/derived.py) are proxies; the
gate thresholds they feed (60 floor, CF ≥ 7, Stab ≥ 5, Quality ≥ 13) were
calibrated on the curated scale. This script measures how often the two
providers agree on the decisions that matter — gate 1 and gate 2 verdicts —
on YOUR roster, and writes the evidence to docs/, so a public-repo reader
can see what "approximate" means in numbers rather than taking it on trust.

Run it on a machine with network access (the same one the radar runs on):

    python3 tools/fundamentals.py                 # a fresh curated run first
    python3 tools/calibrate_derived.py            # then this

It reads the newest output/data/fundamentals_<date>.csv (curated side),
re-fetches every OK/PARTIAL equity through the derived provider (Yahoo), and
writes docs/DERIVED_CALIBRATION_<date>.md with per-name composites, pillar
deltas, and the gate-1/gate-2 confusion counts. FUND-VEHICLE and FAIL rows
are excluded — no basis for comparison.

READING THE RESULT. The number that matters is the FALSE-PASS count: names
where derived passes a gate the curated source fails. The provider's bands are meant to
be conservative near the floors; if false passes appear, tighten the band
edges in tools/fundamentals.py (they are all in one place) and re-run this
until false passes hit zero, accepting the false-fail cost. A false FAIL
costs a look; a false PASS moves money.

Requires yfinance. Standard library otherwise.
"""

import csv
import datetime
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
import fundamentals as F  # noqa: E402
import providers          # noqa: E402


def newest_curated_csv():
    cands = sorted(glob.glob(os.path.join(F.hr.OUTPUT_DIR, "data",
                                          "fundamentals_*.csv")))
    return cands[-1] if cands else None


def main():
    src = newest_curated_csv()
    if not src:
        print("no fundamentals_<date>.csv found — run tools/fundamentals.py "
              "with a curated provider first", file=sys.stderr)
        return 1
    with open(src, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r.get("status") in ("OK", "PARTIAL") and r.get("score")]
    if not rows:
        print(f"{src} has no scored rows — was it a curated run?",
              file=sys.stderr)
        return 1
    print(f"curated side: {len(rows)} scored names from {os.path.basename(src)}")

    results, g1_conf, g2_conf = [], {}, {}
    for i, r in enumerate(rows, 1):
        t = r["ticker"]
        print(f"  [{i}/{len(rows)}] {t} …", end="", flush=True)
        d = providers.get("fundamentals", "derived").fetch(t)
        dg1, dg2 = F.gate1(d), F.gate2(d)
        wg1 = r.get("gate1", "") or r.get("g1", "")
        wg2 = r.get("gate2", "") or r.get("g2", "")

        def verdict(flag):
            return ("PASS" if "PASS" in flag else
                    "FAIL" if "FAIL" in flag else "OTHER")
        k1 = (verdict(wg1), verdict(dg1))
        k2 = (verdict(wg2), verdict(dg2))
        g1_conf[k1] = g1_conf.get(k1, 0) + 1
        g2_conf[k2] = g2_conf.get(k2, 0) + 1
        results.append({
            "ticker": t, "w_score": r["score"], "d_score": d.get("score"),
            "w_g1": wg1, "d_g1": dg1, "w_g2": wg2, "d_g2": dg2,
            "d_status": d.get("status"),
        })
        print(f" w{r['score']} / d{d.get('score')} · g1 {k1[0]}→{k1[1]}")

    today = datetime.date.today().isoformat()
    out = os.path.join(ROOT, "docs", f"DERIVED_CALIBRATION_{today}.md")
    scored = [x for x in results if x["d_score"] is not None]
    diffs = [int(x["d_score"]) - int(x["w_score"]) for x in scored]
    mean = sum(diffs) / len(diffs) if diffs else 0

    def conf_table(conf, gate):
        L = [f"### Gate {gate} agreement", "",
             "| curated \\ derived | PASS | FAIL | OTHER |",
             "|---|---|---|---|"]
        for w in ("PASS", "FAIL", "OTHER"):
            L.append(f"| **{w}** | " + " | ".join(
                str(conf.get((w, d), 0)) for d in ("PASS", "FAIL", "OTHER"))
                + " |")
        fp = sum(v for (w, d), v in conf.items() if w == "FAIL" and d == "PASS")
        L += ["", f"**FALSE PASSES (curated FAIL → derived PASS): {fp}** — "
              "this is the number to drive to zero by tightening bands.", ""]
        return L

    L = [f"# Derived-provider calibration — {today}", "",
         f"Curated side: `{os.path.basename(src)}` ({len(rows)} scored names). "
         f"Derived side fetched live from Yahoo the same day.", "",
         f"**Composite bias: derived − curated = {mean:+.1f} points on average** "
         f"over {len(scored)} comparable names.", ""]
    L += conf_table(g1_conf, 1)
    L += conf_table(g2_conf, 2)
    L += ["## Per-name", "",
          "| Ticker | W score | D score | Δ | W gate1 | D gate1 | W gate2 | D gate2 |",
          "|---|---|---|---|---|---|---|---|"]
    for x in sorted(results, key=lambda x: x["ticker"]):
        d = ("—" if x["d_score"] is None
             else f"{int(x['d_score']) - int(x['w_score']):+d}")
        L.append(f"| {x['ticker']} | {x['w_score']} | {x['d_score'] or '—'} | {d} "
                 f"| {x['w_g1']} | {x['d_g1']} | {x['w_g2']} | {x['d_g2']} |")
    L += ["", "*Generated by tools/calibrate_derived.py. Re-run after any "
          "band-edge change in tools/fundamentals.py.*"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"\nwrote {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
