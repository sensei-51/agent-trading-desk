#!/usr/bin/env python3
"""
test_gate_clause_truncation.py — cases for `append_gate_ledger.GATE_CLAUSE`.

The prose fallback lifts a gate verdict out of a board row's note column by
running from `GATE:` to the end of the clause. "End of the clause" used to mean
the first period of any kind, and that is wrong in a file full of prices,
percentages and LSE tickers — all of which contain periods that end nothing.

On the 2026-08-24 run LNG's verdict reached `Gate_Ledger.csv` as

    GATE: S fail #6 only (AT-PEAK) — ... **overrides it**: LNG is +11

severed at the "." of "+11.3%". That string is not a truncated sentence a reader
can recognise as truncated — it reads as a complete, if odd, verdict, in the one
file this system never regenerates. The same edge cuts "trigger 9.09p" to
"trigger 9" and "IUES.L" to "IUES".

Both directions matter, which is why this is a spec and not a one-line diff:

  * TOO LOOSE and the clause runs past its own sentence into the next one,
    dragging unrelated prose ("Blocked by Gold bloc ceiling", "Tight trigger —
    see Notes") into a field that is supposed to hold a gate verdict;
  * TOO LITERAL and it severs decimals and dotted tickers again.

The fixture half is the regression itself: every gate note that parsed
CORRECTLY before the fix must parse byte-identically after it. A fix that
improves two rows and quietly rewrites eighty is not a fix.

Run: python3 tools/test_gate_clause_truncation.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from append_gate_ledger import GATE_CLAUSE            # noqa: E402

RE = re.compile(r"GATE:\s*[SE]" + GATE_CLAUSE)

# (name, note, expected capture)
CASES = [
    # --- the regression: periods that end nothing ---
    ("decimal percent",
     "GATE: S fail #6 only (AT-PEAK) — LNG is +11.3% above its own 150d. Next.",
     "GATE: S fail #6 only (AT-PEAK) — LNG is +11.3% above its own 150d"),
    ("dotted LSE ticker",
     "GATE: E 6/6 — same extension as IUES.L in this sector. Done.",
     "GATE: E 6/6 — same extension as IUES.L in this sector"),
    ("decimal price",
     "GATE: E fail #2 only (LOW-LIQ) — trigger 9.09p vs 150d 8.71p. Done.",
     "GATE: E fail #2 only (LOW-LIQ) — trigger 9.09p vs 150d 8.71p"),
    ("decimal inside parens",
     "GATE: S fail #6 (score 87, ACCEL, -2.9% off hi). Blocked by bloc ceiling",
     "GATE: S fail #6 (score 87, ACCEL, -2.9% off hi)"),

    # --- the other direction: it must still STOP ---
    ("stops at sentence period",
     "GATE: S fail #6 (score 87, ACCEL). Blocked by Gold bloc ceiling (23.6%)",
     "GATE: S fail #6 (score 87, ACCEL)"),
    ("stops at semicolon",
     "GATE: S 5/6 (score 62, RECORD); fails #6 only",
     "GATE: S 5/6 (score 62, RECORD)"),
    ("stops at end of field",
     "GATE: S 6/6 (score 81, ACCEL+RECORD)",
     "GATE: S 6/6 (score 81, ACCEL+RECORD)"),
    ("period then capital still stops",
     "GATE: E fail #3 (150d Falling). Tight trigger — see Notes",
     "GATE: E fail #3 (150d Falling)"),
    ("no period at all",
     "GATE: E fail #6 only (AT-PEAK) — gate3 has flipped to pass vs prior run",
     "GATE: E fail #6 only (AT-PEAK) — gate3 has flipped to pass vs prior run"),
    ("trailing period at very end",
     "GATE: S 6/6 but EXTENDED-RUN YTD+75.",
     "GATE: S 6/6 but EXTENDED-RUN YTD+75"),
]


def main():
    failures = []
    for name, note, want in CASES:
        m = RE.search(note)
        got = m.group(0) if m else None
        if got != want:
            failures.append((name, want, got))
    for name, want, got in failures:
        print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}", file=sys.stderr)
    print(f"{len(CASES) - len(failures)}/{len(CASES)} case(s) passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
