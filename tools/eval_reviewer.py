#!/usr/bin/env python3
"""
eval_reviewer.py — the mechanical half of the Reviewer's check pass.

`agents/manager.md` defines nineteen checks (eighteen when this script was
written); a human (or the manager subagent) was tracing all of them by hand
each run (docs/PROBLEMS_AND_SOLUTIONS.md §4.1 — "the only place where the user
is currently transcribing 18 checks by hand"). Most of them are grep-and-count
over files this repo already writes. This script runs that mechanical subset in
seconds and emits numbered defects in the manager's output format.

Plus one check that exists ONLY here: **[20], the coverage floor** — it has no
counterpart in `agents/manager.md` because it audits this script rather than
the report. Checks 7, 8, 10, 11, 12 and 18 are all derived from the
conviction-ranked board, so a board this script cannot parse makes all six pass
vacuously. [20] asserts the board carries a row for every roster name, which is
the one failure the other six cannot report (docs/BACKLOG.md item 21.2).

THE TRADER RUNS THIS TOO, since 2026-08-23 (`agents/trader.md` step 8). It is
deterministic, so a second run cannot launder a defect past the Reviewer — it
just means the cheap defects are gone before the expensive audit starts.

WHAT STAYS WITH THE REVIEWER AGENT. Checks that need judgement: price
spot-checks against live sources, whether an explanation for a facts-sheet
mismatch is adequate, whether the action attached to a flag is the right
one (check 5 verifies only that it is there), narrative consistency.
The agent now runs *after* this script and starts from its defect list —
it verifies rather than transcribes. Manager checklist numbering is kept so
the two outputs line up.

Checks mechanised (manager numbering):
   1/2  roster reconciliation + Coverage-header honesty
   20   the board yielded a row per roster name (the floor under 7/8/10/11/12/18)
   3    facts-sheet ⛔ FAIL names visibly handled
   5    every deterministic facts.py flag reaches Pre-entry validation or
        Proactive screening (added 2026-08-23 — see KNOWN_FLAGS)
   7    gate results prefixed S/E
   8    card matches vehicle (FUND-VEHICLE rows never on the S card)
  10    ROUND-TRIP-RISK held names have a review row
  11    every CHASING **gate card** (ticker row) carries the pullback
        qualifier — not merely the sector heading (fixed 2026-08-23)
  12    🔴 only on held names
  13    every buy/add/starter carries a Trading + Investing stop pair,
        Trading at or above Investing (added 2026-08-23)
  16    Sector X-ray table verbatim vs xray_<date>.md
  18    board sector headings exist in sector_map.md
  19    report sections match `templates/evaluation.template.md` exactly
       (added 2026-08-20 — `## Held positions (summary)` table mandatory)
   +    radar-age claim matches the machine verdict (the 2026-08-18 false
        "3 trading days stale" claim is the reason this check exists)

Usage    python3 tools/eval_reviewer.py [--date YYYY-MM-DD]
Exit     0 = no defects, 1 = defects found. Standard library only.
"""

import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, HERE)
import heartbeat_radar as hr  # noqa: E402
import checks as chk          # noqa: E402 — radar_verdict lives there
import handoff                # noqa: E402 — structured handoff sidecars

INPUT_DIR = os.environ.get("TP_INPUT", os.path.join(ROOT, "input"))
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))


def read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def load_roster():
    """(held set, watchlist set) mechanically, per manager check 1."""
    held = {s for s, _, _ in chk.load_holdings()[0]}
    wl = set()
    import glob as g
    for p in g.glob(os.path.join(INPUT_DIR, "[Ww]atchlist*.md")):
        for m in re.finditer(r"^\|\s*\*\*([A-Z0-9.\-]+)\*\*\s*\|", read(p) or "",
                             re.M):
            wl.add(m.group(1))
    return held, wl




def canonical_forms():
    """{broker_symbol -> yahoo ticker} from output/.state/ticker_resolution.json.

    The roster's held names come from the broker CSV, which spells LSE lines
    bare (`CNX1`); the board uses the Yahoo form (`CNX1.L`). `heartbeat_radar.py`
    already records the mapping every run and `tools/checks.py` already reads it,
    so this reuses that record rather than re-deriving a ".L" rule here — the
    twin-form logic in `resolve_ticker` is more subtle than a suffix.

    Absent or unreadable → {}, and the caller accepts either form. That keeps a
    missing sidecar from inventing 10 defects, per this repo's standing rule that
    an absent handoff is never a failure.
    """
    path = os.path.join(OUTPUT_DIR, ".state", "ticker_resolution.json")
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f).get("resolution") or []
    except (OSError, ValueError):
        return {}
    return {r["broker_symbol"]: r["ticker"] for r in rows
            if isinstance(r, dict) and r.get("broker_symbol") and r.get("ticker")}


# ---------------------------------------------------------------- the board
#
# WHY THIS IS A FUNCTION. The report carries two sections whose names once read
# as near-duplicates: `## Action summary` (3 columns, gate cards in prose Notes)
# and `## Conviction-ranked action board` (8 columns, one table per sector).
# Every consumer here wants the second one. The old regex was
#     r"^## (?:Conviction-ranked )?Action board.*?$(.*?)(?=^## (?!Action)|\Z)"
# which is case-sensitive against a heading the template spells lowercase, and
# `re.search` bound it to whichever came first. Result: `board_signals` (check 12),
# the check-18 sector-heading scan and `tools/append_gate_ledger.py` all read the
# 3-column summary with an 8-column row regex and silently saw nothing — for four
# days, exit 0 throughout. A section this load-bearing must never resolve to "".
BOARD_RE = re.compile(r"^##\s+Conviction-ranked action board\s*$(.*?)(?=^##\s|\Z)",
                      re.M | re.S | re.I)


def board_section(body):
    """The 8-column per-sector board, or None. Never guesses at a near-match."""
    hits = BOARD_RE.findall(body)
    if len(hits) != 1:
        return None
    return hits[0]

def board_signals(body):
    """{ticker: [(signal, sector)]} from the conviction-ranked board."""
    out = {}
    section = board_section(body)
    if section is None:
        return out
    for sec_m in re.finditer(r"^### (.+?)$(.*?)(?=^### |\Z)", section,
                             re.M | re.S):
        sector, block = sec_m.group(1).strip(), sec_m.group(2)
        for r in re.finditer(r"^\|\s*\*{0,2}([A-Z0-9.\-]+)\*{0,2}\s*\|(?:[^|]*\|){5}\s*([^|]*?)\s*\|",
                             block, re.M):
            t, sig = r.groups()
            if t.lower() not in ("ticker", "---"):
                out.setdefault(t, []).append((sig, sector))
    return out


# ---------------------------------------------------------------- [+] radar age
#
# WHY THIS IS A FUNCTION AND NOT A REGEX. It was
#     re.search(r"radar[^\n]{0,120}stale", body, re.I)
# — a substring test over the whole report with no sense of what a sentence
# asserts. It fired on the Trader's own MANDATORY provenance disclaimer ("No
# other radar age, staleness or price-date claim is asserted anywhere"), on
# roster-pointer notes ("the listed line has gone stale against the book"), and
# finally on the paragraph written to explain the previous false positive —
# every round of explanation adding another match. No report carrying the
# required disclaimer could pass, so the check blocked every run instead of
# guarding one.
#
# Narrowing a check that exists because of an incident is exactly the change
# that needs a re-runnable test, because the failure it guards against is
# SILENCE: tools/test_radar_stale_check.py. The MUST-NOT-FIRE half is the
# convenience; the MUST-FIRE half is the safety, and every case in it is either
# the 2026-08-18 incident's own wording or a variant found slipping through an
# earlier, looser narrowing. Re-run it after any edit here.

# Meta-discussion *of this check* — never a claim about the data.
_STALE_META = ("false positive", "declined", "report claims the radar is stale")

# A listed *reference* — a roster pointer, an investable line. One of these
# between "radar" and "stale" means the sentence is about a stale pointer, not
# a stale bar: "the radar's listed vehicle has gone stale against the book".
_STALE_LISTING = re.compile(r"\b(vehicles?|lines?|listings?|pointers?|rosters?)\b",
                            re.I)

# A terminator ends a sentence only when whitespace AND an uppercase start
# follow. So "`Heartbeat_Radar_2026-08-15.md`. 3 trading days stale" stays ONE
# sentence — that is the incident's wording with a full stop instead of an
# em-dash — and "PRTC.L" never splits at all, its dot having no space after it.
_STALE_SPLIT = re.compile(r"(?<=[.;!?])\s+(?=[>*`_#\[\-]*[A-Z])")
_RADAR_STALE = re.compile(r"radar\b(.{0,160}?)\bstale", re.I | re.S)


def asserts_radar_stale(body):
    """The sentence in which the report PREDICATES staleness of the radar, or None.

    Deliberately not "the words 'radar' and 'stale' co-occur". Returns the
    offending sentence so a defect can quote it back.
    """
    for sent in (s for s in _STALE_SPLIT.split(body) if s.strip()):
        low = sent.lower()
        if any(m in low for m in _STALE_META):
            continue
        # The mandatory disclaimer. Guarded on "no other" AND an assertion verb,
        # so "No other sector is affected; the radar is 3 days stale" still fires.
        if "no other" in low and ("asserted" in low or "claim" in low):
            continue
        if "gone stale against the book" in low:
            continue
        m = _RADAR_STALE.search(sent)
        if m and not _STALE_LISTING.search(m.group(1)):
            return sent.strip()
    return None


# ----------------------------------------------- [11] the CHASING qualifier
#
# WHY THE HEADING IS NOT THE UNIT. `agents/manager.md` rule 11 puts the
# requirement on the GATE CARD — "the qualifier must appear on every CHASING
# gate card in the report, not just some" — and a gate card is a ticker row,
# not a sector heading. This check tested `"pullback" in heading + block`,
# which any single mention anywhere in the block satisfied. Measured on the
# 2026-08-22 run:
#
#   * FALSE NEGATIVE. `### Healthcare`'s heading happened to carry the full
#     literal phrase, so the block passed — while XLVP.L, TEVA and IHCU.L
#     underneath carried no qualifier at all. The `manager` subagent caught
#     that independently; this script did not.
#   * IMPRECISE DEFECTS. `### Rail`, `### Energy` and `### Financials` were
#     flagged because their headings *paraphrased* the qualifier ("qualifier
#     applies") rather than stating it — but the real defect in each was one
#     level down, on ticker rows carrying no qualifier in any form. Right
#     blocks, wrong reason: a Trader who rewrites the heading fixes nothing.
#
# TWO COMPLIANT FORMS THE PREDICATE MUST NOT MISREAD.
#   * LEVEL-SUBSTITUTED. A row may name its trigger price mid-phrase — "wait
#     for pullback to 150d @ 1,023.65p, then re-check gates 1-8". A literal
#     string match steps straight over these: it finds 26 occurrences on the
#     22 Aug file and none of them is one of the two level-substituted rows,
#     so the count it yields is wrong in both directions. Hence an anchored
#     pattern with a bounded, same-cell gap in the middle.
#   * MOOT. A row already blocked by another gate states the qualifier and
#     marks it spent — "… then re-check gates 1-8 (moot — gate 8 blocks
#     regardless)"; `output/evaluation_2026-08-21.md` writes the same
#     discipline as "Recorded for completeness; gate 1 fails …". Both are
#     compliant *because the qualifier is still stated*; the moot marker is an
#     addition, so an anchored match tolerates them by construction. A row
#     that says only "moot" and never states the qualifier is an omission and
#     still fires.
#
# Both halves are live cases in tools/test_chasing_qualifier_check.py, with
# evaluation_2026-08-22.md as the positive fixture (0 defects) and that file
# with one row stripped as the negative. Re-run it after any edit here.

_QUALIFIER = re.compile(
    r"pullback\s+to\s+(?:the\s+)?150[\s-]*(?:d\b|day)"   # the level to wait for
    r"[^|\n]{0,40}?"                                       # "@ 1,023.65p", "@ $248.43"
    r"then\s+re-?\s*check",                                # …and what to do on arrival
    re.I)

# A gate-card row: `| **XLVP.L** | 63,820p | … | GATE: E 8/8 … |`. The all-caps
# ticker shape excludes the `| Ticker |` header and the `|---|` rule without
# special-casing either.
_GATE_CARD_ROW = re.compile(r"^\|\s*\*{0,2}([A-Z][A-Z0-9.\-]*)\*{0,2}\s*\|(.*)$",
                            re.M)

_CHASING_BLOCK = re.compile(r"^### ([^\n]*CHASING[^\n]*)$(.*?)(?=^### |^## |\Z)",
                            re.M | re.S)


def chasing_qualifier_defects(body):
    """Manager check 11 — the qualifier on every CHASING gate card. List of defects."""
    out = []
    for m in _CHASING_BLOCK.finditer(body):
        heading, block = m.group(1).strip(), m.group(2)
        sector = heading.split("*(")[0].strip() or heading
        rows = _GATE_CARD_ROW.findall(block)
        if not rows:
            # No gate-card table — a prose-format block, or a stub. Fall back to
            # the block-level test so an older report is still checked rather
            # than passing silently for want of a table to read.
            if not _QUALIFIER.search(heading + block):
                out.append("[11] CHASING block states no pullback qualifier "
                           f"anywhere: ### {heading}")
            continue
        bare = [t for t, rest in rows if not _QUALIFIER.search(rest)]
        if bare:
            out.append(f"[11] CHASING gate cards with no pullback qualifier "
                       f"(### {sector}): " + ", ".join(bare))
    return out


def dated(rel_dir, stem, date, ext=".md"):
    """Read `<stem>_<date><ext>`. Dated only — there is no fallback.

    EVERY DATA READ IN THIS SCRIPT MUST GO THROUGH HERE. `--date` used to select
    only the *report*; the four data files it is judged against were always read
    as `_latest`. Reviewing any report but today's therefore compared it against
    today's data, and reported the differences as the report's defects.

    Measured 2026-08-22: check [16] flagged all 12 x-ray rows as "not carried
    verbatim" on the 18, 19 and 20 Aug evaluations. Against the correctly dated
    x-ray, all three match **exactly** — every one of those defects was an
    artefact of this. Since `agents/orchestrator.md` now feeds a non-zero exit
    into a 3-round Trader↔Reviewer loop, a false defect is not a cosmetic
    problem; it burns two subagent runs a round and ends in a HALT.

    The `_latest` fallback this used to carry was removed with the pointers on
    2026-08-25. It existed to cover a same-day run before the dated file landed —
    but every Phase A tool writes its dated file directly now, so the window it
    covered is gone, and a fallback to a file that may carry a DIFFERENT date is
    the exact defect this function was written to stop.
    """
    p = os.path.join(OUTPUT_DIR, rel_dir, f"{stem}_{date}{ext}")
    return read(p), os.path.basename(p)


# ------------------------------------------------- deterministic facts flags
#
# WHY THIS IS MECHANICAL NOW. `tools/facts.py:flags_for()` computes every flag
# below as pure arithmetic over figures already in the row, writes them
# space-joined into the `flags` column, and the report then owes each one an
# assessment (`agents/manager.md` check 5). Until 2026-08-23 nothing mechanical
# read that column — check [3] substring-tested the ⛔ FAIL tickers and stopped
# there — so the only thing between "facts.py computed a flag" and "the report
# acted on it" was an agent reading a CSV column by eye.
#
# Measured on the 23 Aug run: ~40 of 71 flag instances reached no section of the
# report while this script reported 0 defects across three rounds. Among them
# `UPGRADE-14D`, which flags_for() has always emitted and which no spec has ever
# named — an orphan flag, dropped in every run since it was added.
#
# THE INVENTORY IS ASSERTED, NOT ASSUMED. An unrecognised token is itself a
# defect. A ninth flag type added to facts.py without a spec is precisely the
# class-level failure this check exists to stop recurring, and staying silent
# about one would repeat it.
KNOWN_FLAGS = {
    "AT-PEAK", "BINARY-RISK", "CONSENSUS-EXCEEDED", "EXTENDED-RUN",
    "UPGRADE-14D", "DOWNGRADE-14D",
}
EARNINGS_FLAG_RE = re.compile(r"^EARNINGS-\d+D$")

# AT-PEAK fires on 35 of 83 names in a typical run — nearly half the roster.
# Requiring a written line for each is what drove the Trader to narrow the row
# to BUY-TRIGGER names and silently drop 33 of 35 (23 Aug). Per the user's
# decision that day it is required only where it can change a decision: held
# names, and names carrying an actionable signal. A name already AVOID on other
# stated gate reasons does not need one — the gate fail blocks it first.
SCOPED_FLAGS = {"AT-PEAK"}
ACTIONABLE = {"BUY-TRIGGER", "STARTER", "ADD", "SELL", "TRIM", "WAIT"}
BUY_SIGNALS = {"BUY-TRIGGER", "STARTER", "ADD"}


def facts_flags(date):
    """{ticker: [flag tokens]} from facts_<date>.csv, plus the filename used.

    The CSV rather than the .md: `flags` is one column there, space-joined, and
    facts.py guarantees no token contains a space (see its NO SPACES comment).
    """
    import csv
    for name in (f"facts_{date}.csv",):
        p = os.path.join(OUTPUT_DIR, "data", name)
        if not os.path.exists(p):
            continue
        out = {}
        try:
            with open(p, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    toks = (row.get("flags") or "").split()
                    t = (row.get("ticker") or "").strip()
                    if t and toks:
                        out[t] = toks
        except (OSError, ValueError):
            return {}, None
        return out, name
    return {}, None


def flag_base(token):
    """`AT-PEAK(-5.5%)` -> `AT-PEAK`."""
    return token.split("(", 1)[0].strip()


def one_section(body, heading):
    """Body of a single `## <heading>` section; '' when absent OR duplicated.

    Deliberately the same posture as board_section(): a heading that resolves
    twice is not a section, and guessing at one is how check 18's near-duplicate
    heading bug survived four runs.
    """
    hits = re.findall(r"^##\s+" + re.escape(heading) + r"[^\n]*$(.*?)(?=^##\s|\Z)",
                      body, re.M | re.S | re.I)
    return hits[0] if len(hits) == 1 else ""


def signal_map(body, emf):
    """{ticker: SIGNAL}. The eval_manifest when present, else the board.

    The manifest is preferred because it is what the Trader says it decided;
    the board is prose it wrote separately. Check [2] already reports the two
    disagreeing, so this does not re-litigate that here.
    """
    out = {}
    if emf:
        for g in emf.get("gates") or []:
            if isinstance(g, dict) and g.get("ticker"):
                out[g["ticker"]] = str(g.get("signal") or "").upper()
        if out:
            return out
    for t, ss in board_signals(body).items():
        for sig, _ in ss:
            out[t] = re.sub(r"[^A-Z\-]", "", sig.upper())
    return out


def ticker_forms(t, forms):
    """Both spellings of a ticker — broker (`CNX1`) and Yahoo (`CNX1.L`)."""
    return {x for x in (t, forms.get(t), t + ".L") if x}


def mentions(text, t, forms):
    return any(re.search(r"(?<![A-Z0-9.])" + re.escape(x) + r"(?![A-Z0-9])", text)
               for x in ticker_forms(t, forms))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()

    body = read(os.path.join(OUTPUT_DIR, f"evaluation_{a.date}.md"))
    if body is None:
        print(f"no evaluation for {a.date}", file=sys.stderr)
        return 1
    defects = []

    # -- the Trader's structured claims (BACKLOG item 2.3) -------------------
    # Absent is normal and costs nothing: every check below keeps its prose
    # path. Present-but-malformed is a real defect — a sidecar that lies is
    # worse than no sidecar. What it buys is that the checks which currently
    # infer the Trader's intent from English can instead read what the Trader
    # says it did, and compare two values.
    emf, emf_note = handoff.load("eval", a.date)
    if emf is not None:
        problems = handoff.validate("eval", emf, a.date)
        if problems:
            defects.append("[+] eval_manifest is present but invalid: "
                           + "; ".join(problems[:3]))
            emf = None      # do not compare against a malformed manifest

    # -- 1/2 roster + header ------------------------------------------------
    held, wl = load_roster()
    roster = held | wl
    missing = sorted(t for t in roster
                     if not re.search(r"\b" + re.escape(t) + r"\b", body))
    if missing:
        defects.append(f"[1] roster names with no line in the report: "
                       + ", ".join(missing))
    hm = re.search(r"Coverage:\s*(\d+)\s*/\s*(\d+)", body)
    if not hm:
        defects.append("[2] no `Coverage: N/N` header")
    elif int(hm.group(2)) != len(roster):
        defects.append(f"[2] header claims /{hm.group(2)} but mechanical roster "
                       f"is {len(roster)} ({len(held)} held + {len(wl)} wl)")
    if emf:
        cov = emf.get("coverage") or {}
        if cov.get("roster") != len(roster):
            defects.append(f"[2] eval_manifest coverage.roster is "
                           f"{cov.get('roster')} but mechanical roster is "
                           f"{len(roster)}")
        # The report and its own manifest disagreeing is worse than either being
        # wrong: it means the header was written by hand, separately.
        if hm and int(hm.group(2)) != cov.get("roster"):
            defects.append(f"[2] report header says /{hm.group(2)} but its own "
                           f"eval_manifest says /{cov.get('roster')}")

    # -- 20 the board actually yielded rows ---------------------------------
    #
    # THE FLOOR. Every other row-level check here is shaped "find each X in the
    # board, verify X". None of them assert that any X was found, so a board
    # that parses to nothing makes all of them vacuously green — checks 7, 8,
    # 10, 11 and 12 included. Check 19 catches a *missing* section; it cannot
    # catch a section that is present with its heading intact and yields zero
    # rows. That is exactly what happened for four days (docs/BACKLOG.md item
    # 20): the ledger drafter, board_signals() and the check-18 sector scan all
    # silently read an empty result and reported success.
    #
    # One assertion closes the whole class: the board must carry a row for every
    # roster name. The template already requires it ("Every roster name appears
    # exactly once across the sector tables"), so this is not a new rule — it is
    # the existing rule, enforced. It is deliberately stated against `roster`
    # rather than against the report's own `Coverage:` header, because a header
    # is a claim and the roster is derived.
    sigs = board_signals(body)
    forms = canonical_forms()
    def on_board(t):
        return (t in sigs or forms.get(t) in sigs
                or (not forms and (t + ".L") in sigs))
    if board_section(body) is None:
        defects.append("[20] cannot locate exactly one '## Conviction-ranked "
                       "action board' section — every board-derived check "
                       "(7, 8, 10, 11, 12, 18) is vacuous on this report")
    elif not sigs:
        defects.append(f"[20] the conviction-ranked board yielded 0 rows for a "
                       f"roster of {len(roster)} — the section exists but "
                       f"nothing parsed out of it, so every board-derived "
                       f"check passed without reading anything")
    else:
        no_row = sorted(t for t in roster if not on_board(t))
        if no_row:
            shown = ", ".join(no_row[:12]) + (f" (+{len(no_row) - 12} more)"
                                              if len(no_row) > 12 else "")
            defects.append(f"[20] {len(no_row)} roster name(s) have no board "
                           f"row: {shown}. A name mentioned in prose but absent "
                           f"from the board is not a call.")
        dupes = sorted(t for t, v in sigs.items() if len(v) > 1)
        if dupes:
            defects.append(f"[20] name(s) appearing in more than one sector "
                           f"table: {', '.join(dupes[:12])}")

    # -- 3 facts FAILs handled ---------------------------------------------
    facts, facts_src = dated("data", "facts", a.date)
    facts = facts or ""
    sources = [facts_src]
    fails = {m.group(1) for m in
             re.finditer(r"^\|\s*\*{0,2}([A-Z0-9.\-]+)\*{0,2}\s*\|[^\n]*⛔",
                         facts, re.M)}
    unhandled = sorted(t for t in fails if t not in body)
    if unhandled:
        defects.append("[3] facts-sheet ⛔ FAIL names not visibly handled: "
                       + ", ".join(unhandled))

    # -- 5 deterministic flags carried through -------------------------------
    #
    # Two halves, because the two failure modes are opposite. MISSING: a flag
    # facts.py computed that no section of the report acts on (23 Aug: 40 of 71).
    # FABRICATED: a flag the report asserts that facts.py never computed — which
    # is exactly how CVX acquired a "$221 PT, 2.2% over consensus" that belonged
    # to FCX, caught that day only because the Trader re-read the row by hand.
    fl, fl_src = facts_flags(a.date)
    if fl_src:
        sources.append(fl_src)
        pev = one_section(body, "Pre-entry validation")
        prosc = one_section(body, "Proactive screening")
        surfaced = pev + "\n" + prosc
        sig_by_ticker = signal_map(body, emf)

        if not surfaced.strip():
            defects.append("[5] neither `## Pre-entry validation` nor `## "
                           "Proactive screening` resolves to exactly one "
                           "section — the deterministic-flag check cannot run, "
                           "so nothing verifies facts.py's flags reached the "
                           "report")
        else:
            # What the run is REQUIRED to surface.
            required, unknown = {}, []
            for t, toks in fl.items():
                for tok in toks:
                    b = flag_base(tok)
                    if b not in KNOWN_FLAGS and not EARNINGS_FLAG_RE.match(b):
                        unknown.append(f"{t} {tok}")
                        continue
                    if b in SCOPED_FLAGS:
                        sig = sig_by_ticker.get(t, "")
                        if t not in held and not any(s in sig for s in ACTIONABLE):
                            continue      # scoped out — see SCOPED_FLAGS
                    required.setdefault(b, set()).add(t)
            if unknown:
                defects.append(
                    "[5] facts.py emits flag token(s) this check does not know, "
                    "so nothing verifies they reach the report — add them to "
                    "KNOWN_FLAGS here and to `agents/manager.md` check 5: "
                    + ", ".join(sorted(set(unknown))[:8]))

            # What the Trader SAYS it surfaced. Absent is not a failure (the
            # standing rule for handoffs) but it costs the strong per-flag test:
            # prose can only show that the name appears somewhere in the two
            # sections, which is what let NTAP through on 23 Aug — present for
            # its CONSENSUS-EXCEEDED row, silently missing its EXTENDED-RUN one.
            declared, decl_bad = {}, []
            raw = (emf or {}).get("flags_surfaced")
            if isinstance(raw, dict):
                for t, toks in raw.items():
                    if isinstance(toks, list):
                        declared[t] = {flag_base(str(x)) for x in toks}
                    else:
                        decl_bad.append(t)
            elif raw is not None:
                decl_bad.append("flags_surfaced is not an object")
            if decl_bad:
                defects.append("[5] eval_manifest `flags_surfaced` is malformed "
                               "(expected {ticker: [tokens]}): "
                               + ", ".join(map(str, decl_bad[:6])))
                declared = {}

            if declared:
                for b in sorted(required):
                    gone = sorted(t for t in required[b]
                                  if b not in declared.get(t, set()))
                    if gone:
                        shown = ", ".join(gone[:12]) + (
                            f" (+{len(gone) - 12} more)" if len(gone) > 12 else "")
                        defects.append(
                            f"[5] {b} computed in {fl_src} but not declared "
                            f"surfaced in eval_manifest: {shown}")
                # Over-declaration: a flag claimed that facts.py never computed.
                for t in sorted(declared):
                    computed = {flag_base(x) for x in fl.get(t, [])}
                    extra = sorted(declared[t] - computed)
                    if extra:
                        defects.append(
                            f"[5] eval_manifest claims {t} carries "
                            f"{', '.join(extra)}, but {fl_src} computes "
                            f"{', '.join(sorted(computed)) or 'no flags'} for it "
                            f"— a flag asserted that was never computed")
                    if not mentions(surfaced, t, forms):
                        defects.append(
                            f"[5] eval_manifest declares flags surfaced for {t}, "
                            f"but {t} appears in neither `## Pre-entry "
                            f"validation` nor `## Proactive screening`")
            else:
                weak = sorted({t for ts in required.values() for t in ts
                               if not mentions(surfaced, t, forms)})
                if weak:
                    shown = ", ".join(weak[:12]) + (
                        f" (+{len(weak) - 12} more)" if len(weak) > 12 else "")
                    defects.append(
                        f"[5] flagged in {fl_src} but absent from both `## "
                        f"Pre-entry validation` and `## Proactive screening`: "
                        + shown)
                if required:
                    defects.append(
                        "[5] no `flags_surfaced` in the eval_manifest — only "
                        "the weak per-name presence test ran. A name present "
                        "for one flag and missing another cannot be seen "
                        "(see agents/trader.md, deterministic flags)")

    # -- 7 gate prefixes ----------------------------------------------------
    bare = {m.group(0).strip() for m in
            re.finditer(r"GATE[ :]+(?![SE1-9]*[SE])[\d/]+", body)}
    bare |= {m.group(0).strip() for m in
             re.finditer(r"GATE:\s+(?![SE]\b)[a-z\d]", body)}
    if bare:
        defects.append("[7] gate results without an S/E prefix: "
                       + " · ".join(sorted(bare)[:6]))

    # -- 8 card matches vehicle --------------------------------------------
    fnd, fnd_src = dated("data", "fundamentals", a.date)
    fnd = fnd or ""
    sources.append(fnd_src)
    funds = {m.group(1) for m in
             re.finditer(r"^\|\s*\*{0,2}([A-Z0-9.\-]+)\*{0,2}\s*\|[^\n]*FUND-VEHICLE",
                         fnd, re.M)}
    wrong = sorted(t for t in funds
                   if re.search(r"\*\*" + re.escape(t) + r"\*\*[^\n]*GATE\s+S", body))
    if wrong:
        defects.append("[8] fund vehicles run through the STOCK card: "
                       + ", ".join(wrong))

    # -- 10 round-trip reviews ---------------------------------------------
    radar, radar_src = dated("radar", "Heartbeat_Radar", a.date)
    if radar is None:
        import glob as g
        rf = sorted(g.glob(os.path.join(OUTPUT_DIR, "radar", "Heartbeat_Radar_*.md")))
        radar, radar_src = (read(rf[-1]), os.path.basename(rf[-1])) if rf else ("", "—")
    sources.append(radar_src)
    rtr = {m.group(1) for m in
           re.finditer(r"^\|\s*\*{0,2}([A-Z0-9.\-]+)\*{0,2}\s*\|[^\n]*ROUND-TRIP-RISK",
                       radar, re.M)}
    rtr_held = rtr & held
    review = re.search(r"^## Stop loss review.*?$(.*?)(?=^## |\Z)", body,
                       re.M | re.S)
    review_body = review.group(1) if review else ""
    missing_rev = sorted(t for t in rtr_held if t not in review_body)
    if missing_rev:
        defects.append("[10] ROUND-TRIP-RISK holdings without a row in the "
                       "stop-loss review: " + ", ".join(missing_rev))

    # -- 11 CHASING qualifier, per gate card ---------------------------------
    defects.extend(chasing_qualifier_defects(body))

    # -- 12 red only on held ------------------------------------------------
    for t, sigs in board_signals(body).items():
        for sig, sector in sigs:
            if "🔴" in sig and t not in held:
                defects.append(f"[12] 🔴 on a name that is not held: {t} ({sector})")

    # -- 13 stops and sizing on every buy/add/starter -------------------------
    #
    # The pair is arithmetic, so it belongs here rather than in the agent's
    # judgement half: Trading Stop is tactical and first-to-fire, Investing Stop
    # is structural and wider, so an inverted pair makes the Trading Stop dead.
    # The presence half is why this exists at all — on 23 Aug eleven live buy
    # candidates carried triggers and sizes with no stop pair anywhere in the
    # report, and the only three `Trading Stop` mentions in the file were
    # ratchet updates on names already held.
    sig_by_ticker = signal_map(body, emf)
    buys = sorted(t for t, s in sig_by_ticker.items()
                  if any(b in s for b in BUY_SIGNALS))
    no_pair, inverted = [], []
    for t in buys:
        found = False
        # EVERY line, not the first. A level is typically written twice — once
        # in the Action-summary Notes and again in the board row — and the two
        # must agree. Breaking at the first match made an inversion in the
        # second mention invisible, which a fixture caught on 23 Aug.
        for line in body.splitlines():
            if "Trading Stop" not in line or "Investing Stop" not in line:
                continue
            if not mentions(line, t, forms):
                continue
            ts = re.search(r"Trading Stop.{0,80}?[£$€]\s*\*{0,2}\s*"
                           r"([\d,]+(?:\.\d+)?)", line)
            ins = re.search(r"Investing Stop.{0,80}?[£$€]\s*\*{0,2}\s*"
                            r"([\d,]+(?:\.\d+)?)", line)
            found = True
            if ts and ins:
                x = float(ts.group(1).replace(",", ""))
                y = float(ins.group(1).replace(",", ""))
                if x < y:
                    inverted.append(f"{t} (Trading {x:,.2f} < Investing {y:,.2f})")
        if not found:
            no_pair.append(t)
    inverted = sorted(set(inverted))
    if no_pair:
        defects.append("[13] buy/add/starter call(s) with no Trading Stop + "
                       "Investing Stop pair on any line naming them: "
                       + ", ".join(no_pair))
    if inverted:
        defects.append("[13] inverted stop pair — the structural stop would "
                       "fire before the tactical one, making the Trading Stop "
                       "dead: " + " · ".join(inverted))

    # -- 16 x-ray verbatim --------------------------------------------------
    xray, xray_src = dated("data", "xray", a.date)
    xray = xray or ""
    # The sidecar carries its own `date`, so it self-validates: one that turns out
    # to describe another day is DISCARDED rather than compared.
    xray_json, xray_json_src = dated("data", "xray", a.date, ".json")
    if xray_json:
        try:
            if json.loads(xray_json).get("date") != a.date:
                xray_json = None
        except ValueError:
            xray_json = None
    sources.append(xray_json_src if xray_json else xray_src)
    xrows = re.findall(r"^\|\s*[A-Za-z][^|]*\|\s*[\d,]+\s*\|[^|]*\|[^|]*\|$",
                       xray, re.M)
    sec_m = re.search(r"^## Sector X-ray.*?$(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not sec_m:
        defects.append("[16] no `## Sector X-ray` section in the report")
    elif xray_json:
        # Compare VALUES, from xray_<date>.json. The byte-exact path below
        # required the report to reproduce the ████░░░ bar art and the `|  23.9%
        # |` padding character for character, so a re-render that moved one
        # space read as a falsified table. What check 16 actually protects is
        # that the numbers were carried across unaltered.
        try:
            want = {s["sector"]: (round(float(s["value_gbp"])), float(s["pct_nav"]))
                    for s in json.loads(xray_json)["sectors"]}
        except (ValueError, KeyError, TypeError) as e:
            defects.append(f"[16] {xray_json_src} unreadable ({type(e).__name__}) "
                           f"— cannot verify the x-ray table")
            want = {}
        got = {}
        for r in re.finditer(r"^\|\s*([A-Za-z][^|]*?)\s*\|\s*([\d,]+)\s*\|"
                             r"\s*([\d.]+)\s*%\s*\|", sec_m.group(1), re.M):
            got[r.group(1)] = (int(r.group(2).replace(",", "")), float(r.group(3)))
        bad = []
        for sec, (v, p) in want.items():
            if sec not in got:
                bad.append(f"{sec} (missing)")
            elif got[sec][0] != v:
                bad.append(f"{sec} £{got[sec][0]:,} vs £{v:,}")
            elif abs(got[sec][1] - p) > 0.051:      # both render to 1 dp
                bad.append(f"{sec} {got[sec][1]}% vs {p}%")
        for sec in got.keys() - want.keys():
            bad.append(f"{sec} (in the report, not in the x-ray)")
        if bad:
            defects.append("[16] x-ray values do not match "
                           f"{xray_json_src}: " + ", ".join(sorted(bad)))
    else:
        # No sidecar (a report predating it). Byte-exact fallback, kept so an
        # older evaluation is still reviewable rather than silently unchecked.
        rep = sec_m.group(1)
        gone = [r.split("|")[1].strip() for r in xrows if r not in rep]
        if gone:
            defects.append("[16] x-ray rows not carried verbatim (changed, "
                           "missing or reformatted; no "
                           f"xray_{a.date}.json sidecar): " + ", ".join(gone))

    # -- 18 sector headings exist in the map ---------------------------------
    smap_labels = set(hr.load_sector_map().values()) | {"Index"}
    tables_body = board_section(body)
    if tables_body is None:
        # Not "no defects" — the check could not run. Silence here is exactly
        # how the near-duplicate-heading bug survived four runs.
        defects.append("[18] cannot locate exactly one '## Conviction-ranked "
                       "action board' section — the sector-heading check could "
                       "not run (heading missing, renamed, or duplicated)")
    else:
        for h in re.finditer(r"^### ([A-Za-z][A-Za-z ]*?)(?:\s*[（(—].*)?$",
                             tables_body, re.M):
            label = h.group(1).strip()
            if label not in smap_labels:
                defects.append(f"[18] board heading not a sector_map label: "
                               f"### {label}")
        if not re.search(r"^### ", tables_body, re.M):
            defects.append("[18] the conviction-ranked board carries no '### "
                           "<Sector>' tables — nothing to check")

    # -- 19 template compliance ----------------------------------------------
    # Reads templates/evaluation.template.md fresh and diffs `## <header>`
    # lines against the report. The Trader spec (`agents/trader.md` step 9)
    # says read the template fresh every run; this check enforces it.
    template = read(os.path.join(ROOT, "templates", "evaluation.template.md"))
    if template is None:
        defects.append("[19] template file missing at "
                       "templates/evaluation.template.md — cannot verify compliance")
    else:
        tmpl_h = [m.group(1).strip() for m in
                  re.finditer(r"^##\s+(.+?)$", template, re.M)]
        rep_h = [m.group(1).strip() for m in
                 re.finditer(r"^##\s+(.+?)$", body, re.M)]
        missing = [h for h in tmpl_h if h not in rep_h]
        extra = [h for h in rep_h if h not in set(tmpl_h)]
        # Order check — only meaningful when both lists have content.
        order_match = (rep_h[:len(tmpl_h)] == tmpl_h
                       if len(rep_h) >= len(tmpl_h) else False)
        # A held-positions table is mandatory and must have a row per holding
        # (or a SELL row in the Action board).
        held_hp_missing = []
        hp = re.search(r"^## Held positions.*?$(.*?)(?=^## |\Z)", body, re.M | re.S)
        hp_body = hp.group(1) if hp else ""
        sell_tickers = {t for t, sigs in board_signals(body).items()
                        for sig, _ in sigs if "🔴" in sig}
        for t in sorted(held):
            if t not in hp_body and t not in sell_tickers:
                held_hp_missing.append(t)
        if missing:
            defects.append("[19] template sections missing from the report: "
                           + ", ".join(missing))
        if extra:
            defects.append("[19] report has sections not in the template "
                           "(reorder or remove): " + ", ".join(extra))
        if not order_match and not missing and not extra:
            defects.append("[19] report sections are present but in a different "
                           "order than the template — reorder")
        if not hp:
            defects.append("[19] no `## Held positions (summary)` section")
        elif held_hp_missing:
            defects.append("[19] holdings with no row in `## Held positions (summary)` "
                           "and no SELL row in Action board: "
                           + ", ".join(held_hp_missing))

    # -- + radar-age claim vs machine verdict --------------------------------
    verdict, detail = chk.radar_verdict()

    # THE STRUCTURAL FIX (BACKLOG 2.3). When the Trader records the verdict it
    # actually used, this check compares two strings instead of asking whether a
    # paragraph of English asserts staleness. The prose test below still runs —
    # a correct manifest does not stop the report contradicting it — but it is
    # no longer the only thing standing between a run and a false HALT.
    if emf:
        claimed = (emf.get("radar_verdict") or "").strip()
        if claimed != verdict:
            defects.append(f"[+] eval_manifest says the Trader used radar verdict "
                           f"{claimed!r}, but the manifest on disk reads "
                           f"{verdict!r} ({detail})")

    stale_sentence = asserts_radar_stale(body)
    claims_stale = bool(stale_sentence)
    if verdict == "FRESH" and claims_stale:
        quoted = (stale_sentence[:117] + "…") if len(stale_sentence) > 118 else stale_sentence
        defects.append(f"[+] report claims the radar is stale but the machine "
                       f"verdict is FRESH ({detail}) — quote the manifest, "
                       f"never re-derive the age. Offending sentence: {quoted!r}")
    if verdict.startswith("STALE") and not claims_stale:
        defects.append(f"[+] radar is {verdict} ({detail}) but the report "
                       f"carries no staleness caveat")

    # -- output --------------------------------------------------------------
    print(f"eval_reviewer — evaluation_{a.date}.md — "
          f"{len(defects)} defect(s)")
    # Name the data actually compared against, so a missing dated file is visible
    # as a missing comparison rather than silently weakening the review.
    print(f"  compared against: {' · '.join(sources)}")
    print(f"  eval_manifest: {emf_note}\n")
    for i, d in enumerate(defects, 1):
        print(f"{i}. {d}")
    if not defects:
        print("PASS — no mechanical defects. (Judgement checks 4-6, 9, 13-15, "
              "17 remain with the Reviewer agent.)")
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
