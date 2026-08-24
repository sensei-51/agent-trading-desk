#!/usr/bin/env python3
"""
test_chasing_qualifier_check.py — cases for `eval_reviewer.chasing_qualifier_defects`.

Check 11 asserts what `agents/manager.md` rule 11 asserts: a CHASING sector's
"wait for a pullback to the 150-day, then re-check gates 1-8" qualifier must
appear on **every CHASING gate card**, not just some. A gate card is a ticker
row. The check read sector *headings*, and so was wrong in both directions on
the 2026-08-22 run:

  * a FALSE NEGATIVE — `### Healthcare`'s heading carried the literal phrase, so
    the block passed while XLVP.L, TEVA and IHCU.L underneath carried nothing
    (the `manager` subagent caught it; the script did not);
  * IMPRECISE DEFECTS — `### Rail`, `### Energy` and `### Financials` fired
    because their headings paraphrased ("qualifier applies"), while the actual
    bare rows one level down went unnamed.

Widening a check to a finer grain is exactly the change that needs a
re-runnable spec, because the two ways it can go wrong are opposite: too loose
and it goes silent again; too literal and it fires on the two forms a
compliant row is *allowed* to take —

  * LEVEL-SUBSTITUTED — a trigger price embedded mid-phrase, "wait for pullback
    to 150d @ 1,023.65p, then re-check gates 1-8";
  * MOOT — the qualifier stated and then marked spent because another gate
    already blocks the name, "(moot — gate 8 blocks regardless)", written on
    2026-08-21 as "Recorded for completeness; gate 1 fails …".

The fixture half is the same argument against a real file: evaluation_2026-08-22.md
must return 0 defects, and the same file with the qualifier stripped from one
row under a compliant heading must name that row.

Usage    python3 tools/test_chasing_qualifier_check.py
Exit     0 = all cases behave, 1 = at least one case does not.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from eval_reviewer import (chasing_qualifier_defects,             # noqa: E402
                           _QUALIFIER, _CHASING_BLOCK, _GATE_CARD_ROW)

HDR = ("### Energy *(CHASING · STRENGTHENING · ACCELERATING — streak 3 · "
       "qualifier: wait for pullback to 150d, then re-check gates 1-8)*")
BARE_HDR = "### Energy *(CHASING · STRENGTHENING · ACCELERATING — streak 3)*"
COLS = ("\n\n| Ticker | Px | 150d | OffHigh | RS | YTD | Signal | Note |\n"
        "|---|---|---|---|---|---|---|---|\n")


def block(heading, *rows):
    return heading + COLS + "\n".join(rows) + "\n"


# Blocks the check MUST flag. Silence here is the 2026-08-22 false negative
# coming back: a Trader omits the qualifier on a gate card and the run passes.
MUST_FIRE = [
    ("the 2026-08-22 false negative — compliant heading, bare rows beneath",
     block(HDR,
           "| **XLVP.L** | 63,820p | 4,250.00 R | -11.0% | 64 | +12.0% | "
           "🟠 HOLD-no-add | GATE: E 8/8 — corrected today. Cap now £5,000 |",
           "| **TEVA** | $37.34 | 33.11 R | -0.3% | 84 | +19.6% | 🟠 HOLD-no-add | "
           "GATE: S 0/7 usable. Exit written: close < $33.11 |")),
    ("one bare row among compliant ones — the consistency FAIL rule 11 names",
     block(HDR,
           "| **CVX** | $205.27 | 187.00 R | -2.8% | 50 | +34.7% | 🟠 HOLD-no-add | "
           "GATE: S 6/7. CHASING qualifier: wait for pullback to 150d, then "
           "re-check gates 1-8 |",
           "| LNG | $277.51 | 248.43 R | -6.5% | 56 | +42.8% | 🟠 WAIT | "
           "GATE: S 6/7 → starter-max. Sizes to the CHASING cap |")),
    ("heading paraphrases AND the row is bare — the defect is the row",
     block(BARE_HDR + " qualifier applies",
           "| XOM | $165.11 | 150.45 R | -3.7% | 62 | +37.2% | 🟤 AVOID | "
           "GATE: S fail #1 + #6. Two fails |")),
    ("row paraphrases instead of stating the qualifier",
     block(HDR,
           "| **UIFS.L** | 1,246.50p | 1,163.13 R | -19.9% | 46 | +3.6% | "
           "🟠 HOLD-no-add | GATE: E 8/8 — corrected today. Qualifier applies |")),
    ("row names the level but never says to re-check",
     block(HDR,
           "| IUES.L | $13.45 | 11.91 R | -0.4% | 70 | +42.8% | 🟠 WAIT | "
           "GATE: E 8/8 — blocked by the qualifier, not a gate. "
           "Pullback to 150d @ $11.89, then re-run |")),
    ("'moot' alone, with the qualifier never stated, is an omission",
     block(HDR,
           "| IHCU.L | 1,036.00p | 923.14 R | +0.0% | 66 | +11.9% | 🟤 AVOID | "
           "GATE: E fail #8 — overlap. CHASING qualifier moot — gate 8 blocks "
           "regardless |")),
    ("prose-format CHASING block with no qualifier anywhere (no table to read)",
     "### Financials *(CHASING · NEW — streak 1)*\n\n"
     "**PNC** — 🟠 **HOLD.** GATE: S fail #1 (no ACCEL/RECORD data).\n"),
    ("the qualifier sits in a neighbouring cell, not on the row that needs it",
     block(HDR,
           "| **CVX** | $205.27 | 187.00 R | -2.8% | 50 | +34.7% | 🟠 HOLD-no-add | "
           "GATE: S 6/7. CHASING qualifier: wait for pullback to 150d, then "
           "re-check gates 1-8 |",
           "| XOM | $165.11 | 150.45 R | -3.7% | 62 | +37.2% | 🟤 AVOID | "
           "GATE: S fail #1 (score 49) + #6 (consensus +3.0%). Two fails |")),
]

# Blocks a compliant report must be able to write without tripping the check.
# A fire here is the "flagged the right block for the wrong reason" defect.
MUST_NOT_FIRE = [
    ("plain literal qualifier on every row",
     block(HDR,
           "| **CVX** | $205.27 | 187.00 R | -2.8% | 50 | +34.7% | 🟠 HOLD-no-add | "
           "GATE: S 6/7. CHASING qualifier: wait for pullback to 150d, then "
           "re-check gates 1-8 — blocks the add |")),
    ("LEVEL-SUBSTITUTED — pence trigger embedded mid-phrase, comma and all",
     block(HDR,
           "| ISF.L | 1,060.00p | 1,023.65 R | -0.7% | 35 | +9.7% | 🟠 WAIT | "
           "GATE: E 7/8 — but Index is CHASING: qualifier — wait for pullback "
           "to 150d @ 1,023.65p, then re-check gates 1-8 |")),
    ("LEVEL-SUBSTITUTED — dollar trigger embedded mid-phrase",
     block(HDR,
           "| LNG | $277.51 | 248.43 R | -6.5% | 56 | +42.8% | 🟠 WAIT | "
           "GATE: S 6/7 → starter-max. CHASING qualifier: wait for pullback to "
           "150d @ $248.43, then re-check gates 1-8 |")),
    ("MOOT — qualifier stated, then marked spent by another gate",
     block(HDR,
           "| IHCU.L | 1,036.00p | 923.14 R | +0.0% | 66 | +11.9% | 🟤 AVOID | "
           "GATE: E fail #8 — overlap, never starter-eligible. CHASING "
           "qualifier: wait for pullback to 150d, then re-check gates 1-8 "
           "(moot — gate 8 blocks regardless) |")),
    ("MOOT, 2026-08-21 wording — 'Recorded for completeness; gate 1 fails …'",
     block(HDR,
           "| **PNC** | $243.13 | 228.78 R | -5.4% | 44 | +16.5% | 🟠 HOLD | "
           "GATE: S fail #1. **Financials is CHASING: qualifier — wait for "
           "pullback to 150d, then re-check gates 1-8.** Recorded for "
           "completeness; gate 1 fails on absent ACCEL/RECORD data, so no "
           "pullback unlocks a fill here either |")),
    ("rulebook's own wording — 'a pullback to the 150-day, then re-check'",
     block(HDR,
           "| **ICE** | $161.25 | 153.38 F | -10.7% | 19 | -0.4% | 🟠 HOLD-no-add | "
           "GATE: S fail #1 + #6. Wait for a pullback to the 150-day, then "
           "re-check gates 1-8 |")),
    ("en-dash in 'gates 1–8'",
     block(HDR,
           "| AFRM | $77.03 | 64.37 F | -16.4% | 68 | +3.5% | 🟤 AVOID | "
           "GATE: S fail #1 + #2 + #3. CHASING qualifier: wait for pullback to "
           "150d, then re-check gates 1–8 (moot — three fails already) |")),
    ("heading PARAPHRASES but every row states it — rule 11 is about the cards",
     block(BARE_HDR + " qualifier applies",
           "| **CVX** | $205.27 | 187.00 R | -2.8% | 50 | +34.7% | 🟠 HOLD-no-add | "
           "GATE: S 6/7. CHASING qualifier: wait for pullback to 150d, then "
           "re-check gates 1-8 |")),
    ("a non-CHASING sector's bare rows are none of this check's business",
     block("### Shipping *(STRONG-IN · STABLE · ACCELERATING — streak 3)*",
           "| **ESEA** | $75.03 | 67.30 R | -5.5% | 44 | +37.4% | 🟠 HOLD-no-add | "
           "GATE: S fail #1 → Tier 2. Unstopped by design |")),
    ("prose-format CHASING block that does carry the qualifier",
     "### Financials *(CHASING · NEW — streak 1 · qualifier: wait for pullback "
     "to 150d, then re-check gates 1-8)*\n\n"
     "**PNC** — 🟠 **HOLD.** GATE: S fail #1 (no ACCEL/RECORD data).\n"),
]


def heading_only_predicate(body):
    """The check as it stood before 2026-08-23, verbatim — kept as the control.

    The negative fixture's whole point is that THIS returns nothing on it. Pin
    it here rather than describe it in a comment: if someone later widens the
    fixture until the old predicate would have caught it too, the fixture has
    stopped testing the thing the change was made for, and this says so.
    """
    return [m.group(1).strip() for m in _CHASING_BLOCK.finditer(body)
            if "pullback" not in (m.group(1) + m.group(2)).lower()]


def negative_fixture(body):
    """(mutated body, ticker) — one gate card stripped, under a compliant heading.

    Chosen structurally, not by ticker name, so the fixture cannot quietly
    decay into stripping a row somewhere else in the report: the block must be
    CHASING, its HEADING must already state the qualifier (that is what made
    2026-08-22's Healthcare block pass while its rows were bare), and the row
    must be one that currently states it.
    """
    for m in _CHASING_BLOCK.finditer(body):
        heading, blk = m.group(1), m.group(2)
        if not _QUALIFIER.search(heading):
            continue                      # heading must be the compliant kind
        for line in blk.splitlines():
            rm = _GATE_CARD_ROW.match(line)
            if rm and _QUALIFIER.search(line):
                return (body.replace(line, _QUALIFIER.sub("qualifier applies", line)),
                        rm.group(1))
    return None, None


def fixtures():
    """The file-level halves: the 22 Aug report clean, and one gate card stripped."""
    path = os.path.join(os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output")),
                        "evaluation_2026-08-22.md")
    print("\nFIXTURES")
    if not os.path.exists(path):
        print(f"  SKIP  {path} not present")
        return 0
    body = open(path, encoding="utf-8").read()
    bad = 0

    def case(ok, label, notes=()):
        nonlocal bad
        print(("  ok    " if ok else "  FAIL  ") + label)
        for n in notes:
            print(f"          {n}")
        bad += not ok

    # POSITIVE. All 18 CHASING gate cards on this report state the qualifier —
    # 2 of them level-substituted, 12 marked moot. Any defect here is a false
    # positive against a file known to be compliant.
    got = chasing_qualifier_defects(body)
    case(not got,
         f"evaluation_2026-08-22.md returns 0 defects (got {len(got)})", got)

    # NEGATIVE. One gate card stripped under a heading that keeps the qualifier
    # — the exact shape the heading-only check waved through on 22 Aug.
    mutated, victim = negative_fixture(body)
    if mutated is None:
        case(False, "could not build the negative fixture — no CHASING block "
                    "with a compliant heading and a qualifier-bearing row")
        return bad
    got = chasing_qualifier_defects(mutated)
    case(any(victim in d for d in got),
         f"stripping the qualifier from the {victim} gate card fires "
         f"and names it", got)
    case(len(got) == 1,
         f"…and flags nothing else (got {len(got)} defect(s))")
    # The control: silence here is why the change was needed.
    case(not heading_only_predicate(mutated),
         f"…and the pre-2026-08-23 heading-only predicate stays silent on it "
         f"(the {victim} false negative)")
    return bad


def main():
    bad = 0
    for label, cases, want in (("MUST FIRE", MUST_FIRE, True),
                               ("MUST NOT FIRE", MUST_NOT_FIRE, False)):
        print(label)
        for name, text in cases:
            got = bool(chasing_qualifier_defects(text))
            ok = got is want
            print(("  ok    " if ok else "  FAIL  ") + name)
            bad += not ok
    total = len(MUST_FIRE) + len(MUST_NOT_FIRE)
    bad += fixtures()
    print(f"\n{total + 4 - bad}/{total + 4} cases behave as specified "
          f"({total} unit + 4 fixture).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
