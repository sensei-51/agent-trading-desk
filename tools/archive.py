#!/usr/bin/env python3
"""
archive.py — fold old dated artefacts into month folders. A move, never a delete.

WHY THIS IS A SEPARATE TOOL FROM housekeeping.py
  They answer complaints that sound identical and are not. "This directory is
  massive" is almost never about disk — `output/data/` reached 82 entries in
  fourteen days while weighing 1.1 MB. The felt problem is a listing too long
  to skim; the instinct it produces is to delete; and the files nearest to hand
  are the ones nothing can rebuild. `facts.py` fetches live prices and cannot
  be asked for the afternoon of 13 Aug.

  So the two operations are kept apart, because their safety properties are
  opposites. Deleting is irreversible and works off a deny-list: everything is
  fair game unless something protects it. Archiving is reversible with `mv` and
  works off an ALLOW-list: nothing moves unless a rule names it. Putting both
  behind one flag invites the reflex that picks the wrong one — and did, during
  development, when this defaulted to a 30-day window that would have left ~180
  files flat, solving nothing.

  `housekeeping.py` imports `scan_archive` from here to *report* the
  opportunity. It cannot perform it. One implementation, one doer.

WHAT MOVES
  `output/data/facts_2026-08-13.md` → `output/data/2026-08/facts_2026-08-13.md`

  Nothing else changes: same filename, same bytes, one directory deeper. At
  roughly six artefacts a run, a 3-day window holds the flat listing near
  eighteen entries and puts everything else one click away.

THE ALLOW-LIST IS THE WHOLE SAFETY ARGUMENT
  A file moves only if its directory is a key in ARCHIVE_SPECS *and* its name
  matches one of that key's patterns. Evaluations, the gate ledger, `*_latest.*`
  pointers, hand-written notes and every file shape nobody has thought of yet
  are unrecognised, and unrecognised means untouched.

  A deny-list would have to anticipate every future artefact and would fail
  silently the first time it missed one. This has to anticipate none: the
  failure mode of an allow-list is that something useful is left flat, which is
  visible and harmless.

THE PIPELINE DOES NOT KNOW THIS HAPPENED
  Exactly one reader reaches into the past: `tools/eval_reviewer.py`, whose
  `resolve_dated()` tries the flat path and then the month folder. Flat wins
  when both exist, so a stale copy left in an archive can never shadow a live
  file. Every other tool either writes today's file or globs for the newest,
  and `calibrate_derived.py` — which wants the most recent fundamentals CSV —
  is unaffected because the newest is never old enough to have moved.

Inputs   output/{data,radar,reports}/<stem>_<date>.<ext>
Output   the same files, under <dir>/<YYYY-MM>/

Usage    python3 tools/archive.py                  # dry run — shows the moves
         python3 tools/archive.py --apply          # perform them
         python3 tools/archive.py --days 7         # keep a trading week flat
         python3 tools/archive.py --restore 2026-07  # flatten a month back out
"""

import argparse
import datetime
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))

# The allow-list. A directory key, and the filenames under it that are known
# dated artefacts. Anything not matched here is never moved.
ARCHIVE_SPECS = {
    "data": (r"^(?:facts|fundamentals|xray|analyst|darkpool|darkpool_backfill)"
             r"_(?P<date>\d{4}-\d{2}-\d{2})\.(?:md|csv|json)$",),
    "radar": (r"^Heartbeat_Radar_(?P<date>\d{4}-\d{2}-\d{2})\.md$",),
    "reports": (r"^PnL_(?P<date>\d{4}-\d{2}-\d{2})\.md$",),
}

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def rel(path):
    return os.path.relpath(path, ROOT)


def human(n):
    for lim, suf in ((1 << 30, "GB"), (1 << 20, "MB"), (1 << 10, "KB")):
        if n >= lim:
            return f"{n / lim:.1f} {suf}"
    return f"{n} B"


def scan_archive(days):
    """Yield (src, dst, reason) for each dated artefact older than `days`.

    A destination that already exists is skipped rather than overwritten — the
    flat copy is then the odd one out and is better looked at by a human than
    silently merged.
    """
    today = datetime.date.today()
    for sub, pats in sorted(ARCHIVE_SPECS.items()):
        d = os.path.join(OUTPUT_DIR, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            src = os.path.join(d, fn)
            if not os.path.isfile(src):
                continue
            m = None
            for pat in pats:
                m = re.match(pat, fn)
                if m:
                    break
            if not m:
                continue
            try:
                age = (today - datetime.date.fromisoformat(m.group("date"))).days
            except ValueError:
                continue
            if age < days:
                continue
            month = m.group("date")[:7]
            dst = os.path.join(d, month, fn)
            if os.path.exists(dst):
                continue
            yield src, dst, f"{age}d old → {sub}/{month}/"


def scan_restore(month):
    """Yield (src, dst, reason) to flatten one month folder back out.

    The inverse exists so the tool is honestly reversible rather than reversible
    in principle. `mv` would do it; having it here means nobody has to work out
    the glob under pressure.
    """
    for sub in sorted(ARCHIVE_SPECS):
        d = os.path.join(OUTPUT_DIR, sub, month)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            src = os.path.join(d, fn)
            dst = os.path.join(OUTPUT_DIR, sub, fn)
            if not os.path.isfile(src) or os.path.exists(dst):
                continue
            yield src, dst, f"back to {sub}/"


def perform(moves):
    """Move each pair, creating the destination directory. Never overwrites:
    `scan_*` already skipped colliding destinations, so a collision here means
    the tree changed underneath us and stopping is the correct response."""
    done = 0
    for src, dst, _ in moves:
        if os.path.exists(dst):
            raise RuntimeError(f"refusing to overwrite {rel(dst)}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        done += 1
    return done


def prune_empty():
    """Remove month folders left empty by a restore. Only ever an empty
    directory, and only one whose name is a month — never a file."""
    for sub in sorted(ARCHIVE_SPECS):
        d = os.path.join(OUTPUT_DIR, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if os.path.isdir(p) and MONTH_RE.match(fn) and not os.listdir(p):
                os.rmdir(p)


def report(moves, apply_it, verb):
    if not moves:
        print(f"[archive] nothing to {verb}")
        return 0
    total = sum(os.path.getsize(s) for s, _, _ in moves)
    print(f"[archive] {len(moves)} file(s), {human(total)}")
    for src, _, reason in moves[:12]:
        print(f"          {rel(src)}")
        print(f"            ↳ {reason}")
    if len(moves) > 12:
        print(f"          … and {len(moves) - 12} more")
    if not apply_it:
        print(f"[archive] dry run — nothing moved. Re-run with --apply.")
        return 0
    n = perform(moves)
    prune_empty()
    print(f"[archive] moved {n} file(s). Nothing deleted; reverses with "
          f"--restore <YYYY-MM>.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="perform the moves (default is a dry run)")
    ap.add_argument("--days", type=int, default=3, metavar="N",
                    help="archive artefacts older than N days (default 3 — "
                         "keeps the flat listing short enough to read at a "
                         "glance; 30 would leave ~180 files flat)")
    ap.add_argument("--restore", metavar="YYYY-MM",
                    help="flatten one month folder back out")
    a = ap.parse_args()

    if a.restore:
        if not MONTH_RE.match(a.restore):
            print(f"[archive] --restore wants YYYY-MM, got {a.restore!r}")
            return 1
        return report(list(scan_restore(a.restore)), a.apply, "restore")

    if a.days < 0:
        print("[archive] --days must be >= 0")
        return 1
    return report(list(scan_archive(a.days)), a.apply, "archive")


if __name__ == "__main__":
    sys.exit(main())
