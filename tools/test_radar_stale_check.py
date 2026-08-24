#!/usr/bin/env python3
"""
test_radar_stale_check.py — cases for `eval_reviewer.asserts_radar_stale`.

The radar-age check ([+] in eval_reviewer.py) is the one check written in
response to a specific incident: on 2026-08-18 a Trader wrote "3 trading days
stale, all prices Friday's close" into the header while the radar's own header
said newest bar = that day, and every chart read in that report carried a false
caveat.

Its original predicate was `radar[^\n]{0,120}stale` over the whole report. On
2026-08-21 that fired on a report whose only matches were its own disclaimer
("No other radar age, staleness or price-date claim is asserted anywhere") and
the record explaining why the defect was declined — the check firing on its own
audit trail, with each round of explanation adding another match.

Narrowing a check that exists because of an incident is exactly the change that
needs a re-runnable test, because the failure it guards against is silence. The
MUST-NOT-FIRE half is the convenience; the MUST-FIRE half is the safety, and
every case in it is either the incident's own wording or a variant a reviewer
found slipping through an earlier, looser narrowing.

Usage    python3 tools/test_radar_stale_check.py
Exit     0 = all cases behave, 1 = at least one case does not.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_reviewer import asserts_radar_stale          # noqa: E402

# Sentences the check MUST flag when the machine verdict is FRESH. A silent
# result here means a Trader can write a false age claim and the run will pass.
MUST_FIRE = [
    ("control",
     "The radar is stale."),
    ("2026-08-18 incident, verbatim",
     "**Radar:** `Heartbeat_Radar_2026-08-15.md` — 3 trading days stale, "
     "all prices Friday's close."),
    ("incident with a full stop instead of an em-dash (the .md dot must not "
     "split the sentence)",
     "**Radar:** `Heartbeat_Radar_2026-08-15.md`. 3 trading days stale, "
     "all prices Friday's close."),
    ("'no' earlier in the sentence in an unrelated role",
     "No live re-check was possible, so the radar is 3 trading days stale."),
    ("'no other <thing>' that is not the disclaimer",
     "No other sector is affected; the radar is 3 days stale."),
    ("'no fresh radar' — how the false claim would actually be written",
     "There is no fresh radar today — the radar is 3 trading days stale "
     "and prices are Friday's close."),
    ("genuine claim that happens to use the word 'defect'",
     "Radar 3 trading days stale — a known defect in the Phase A fetch, "
     "carried into this run."),
    ("genuine claim that happens to mention the checker",
     "The checker will flag it: the radar is 3 trading days stale and "
     "every price is Friday's close."),
    ("listing noun later in the sentence is not predication",
     "Radar is stale — every row on it is Friday's close."),
    ("possessive with a listing noun four words away",
     "The radar's newest bar is 3 days stale for every ticker in the book."),
    ("listing noun after the claim",
     "The radar is stale; no member is priced later than Wednesday."),
    ("blockquote — the degraded header is where the incident was written",
     "> **Degraded header:** the radar is stale (2 trading days old); "
     "every chart read carries that caveat."),
    ("verdict-style claim",
     "Radar STALE(3) — the radar is stale by three trading days."),
    ("mid-report caveat",
     "Bear in mind the radar data is stale, so treat every chart read "
     "as Friday's."),
    ("ticker dots must not split the sentence",
     "PRTC.L and SPAG.L aside, the radar is 3 trading days stale."),
]

# Sentences a correct report must be able to write about this check without
# tripping it. A fire here is the false positive that prompted the narrowing.
MUST_NOT_FIRE = [
    ("verbatim manifest quote followed by the disclaimer",
     '> **Manifest radar verdict, quoted verbatim:** `FRESH` — *"file '
     'Heartbeat_Radar_2026-08-21.md, newest bar 2026-08-21, 0 trading day(s) '
     'old"*. No other radar age, staleness or price-date claim is asserted '
     'anywhere in this report.'),
    ("roster pointer — 'radar' and 'stale' in different sentences",
     "- **Healthcare (CHASING)** → radar names **PRTC.L**, which is no longer "
     "held or on the roster (exited 20 Aug). The listed line has gone stale "
     "against the book."),
    ("declined-defect record explaining why 'stale' was not claimed",
     "2. and 3. Two statements that the radar's **listed investable vehicle** "
     '(PRTC.L) has **"gone stale against the book"** — a statement about the '
     "sector map's roster pointer, not about the radar's data age."),
    ("defect table row quoting the check's own message",
     '| 4 | checker [+] — "report claims the radar is stale but the machine '
     'verdict is FRESH" | **DECLINED — checker false positive.** |'),
    ("possessive directly on a listing noun",
     "The radar's listed vehicle has gone stale against the book."),
    ("audit prose naming this script",
     "`eval_reviewer.py` reports that the radar is stale, which is a "
     "false positive."),
]


def main():
    bad = 0
    for label, cases, want in (("MUST FIRE", MUST_FIRE, True),
                               ("MUST NOT FIRE", MUST_NOT_FIRE, False)):
        print(label)
        for name, text in cases:
            got = bool(asserts_radar_stale(text))
            ok = got is want
            print(("  ok    " if ok else "  FAIL  ") + name)
            bad += not ok
    total = len(MUST_FIRE) + len(MUST_NOT_FIRE)
    print(f"\n{total - bad}/{total} cases behave as specified.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
