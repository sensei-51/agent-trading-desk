#!/usr/bin/env python3
"""
run_daily.py — the one command that produces a coherent run.

WHY THIS EXISTS. On 2026-08-18 the pipeline ran by hand, out of order: the
analyst sheet was written at 12:46 reporting 14 FAILs, the evaluation at 13:08
quoted them, and fundamentals.py re-ran at 13:46 producing the corrected
0-FAIL sheet — so the shipped evaluation described a fundamentals state that
was superseded 38 minutes later. The same run's evaluation also claimed the
radar was "3 trading days stale" when the radar's own header said newest bar
= that day. Both failures are ordering/derivation problems, and both are
impossible when one script runs the steps in order, halts on the first
non-zero exit, and stamps a machine-readable manifest the agents must quote
instead of re-deriving.

WHAT IT RUNS, IN ORDER (each halts the pipeline on failure):

  0. checks  --pre     input sanity (sector map, config)
  1. radar             engine/heartbeat_radar.py
  2. facts             tools/facts.py
  3. fundamentals      tools/fundamentals.py
  3b. darkpool             tools/darkpool.py            (darkpool + conviction legs)
  4. xray              tools/xray.py   (fails on unclassified HELD names)
  5. checks  --post    bloc ceiling, NAV consistency, radar age, honesty
                       ("ledger touched" fails until append_gate_ledger has
                        drafted/committed — expected before the Trader runs)

then writes output/.state/run_manifest.json:

  { "date", "run", "started", "finished", "steps": [{name, cmd, exit, seconds}],
    "radar": {"verdict": "FRESH"|"STALE(ntd)", "detail": ...},
    "artefacts": {path: {"mtime": iso, "sha1": ...}} }

THE CONTRACT WITH THE AGENTS. The Analyst and Trader read the manifest first.
The radar verdict is quoted VERBATIM — an evaluation may not assert a radar
age the manifest does not state (that is how the false staleness claim of
2026-08-18 becomes structurally impossible). An artefact whose sha1 no longer
matches the manifest was regenerated after the run — the Trader must refuse
to proceed and this script must be re-run.

A SECOND RUN IN ONE DAY IS SUPPORTED (decision 2026-08-23). Before overwriting
anything, the run archives the outgoing run's report, Phase A artefacts and
manifest to `output/.state/runs/<date>/run<N-1>/` — so "did the data move, or
did the Trader decide differently?" stays answerable. `--compare-runs` answers
it.

Usage    python3 tools/run_daily.py                # the daily run
         python3 tools/run_daily.py --skip radar   # reuse this morning's radar
         python3 tools/run_daily.py --dry-run      # print the plan only
         python3 tools/run_daily.py --compare-runs 1     # run 1 vs live tree
         python3 tools/run_daily.py --compare-runs 1:2   # run 1 vs run 2

Standard library only.
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))
STATE_DIR = os.path.join(OUTPUT_DIR, ".state")
MANIFEST = os.path.join(STATE_DIR, "run_manifest.json")

PY = sys.executable or "python3"

STEPS = [
    ("checks-pre", [PY, "tools/checks.py", "--pre"]),
    ("radar", [PY, "engine/heartbeat_radar.py"]),
    ("facts", [PY, "tools/facts.py"]),
    ("fundamentals", [PY, "tools/fundamentals.py"]),
    # Whole-book legs. Behaviour-neutral by design: renders darkpool and conviction
    # for the agents to read; no gate consults it yet — ETF gate 1 is still the
    # radar's rotation read. See docs/DARKPOOL_FIRST_PROPOSAL.md Phase 1 vs Phase 4.
    ("darkpool", [PY, "tools/darkpool.py"]),
    ("xray", [PY, "tools/xray.py"]),
    ("checks-post", [PY, "tools/checks.py", "--post"]),
]

# Artefacts the agents consume — fingerprinted so post-run regeneration is
# detectable (the 2026-08-18 failure mode). Dated paths since the `latest*.md`
# pointers were retired on 2026-08-25; `artefacts()` takes the run date because
# there is no longer a fixed filename that means "this run".
def artefacts(date):
    return [
        f"output/radar/Heartbeat_Radar_{date}.md",
        f"output/data/facts_{date}.md",
        f"output/data/fundamentals_{date}.md",
        f"output/data/darkpool_{date}.md",
        f"output/data/xray_{date}.md",
    ]


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def radar_verdict():
    sys.path.insert(0, HERE)
    import checks
    return checks.radar_verdict()


def run_number(date):
    """Which run of `date` is this? 1 for the day's first.

    A SECOND RUN IS SUPPORTED, NOT AN ERROR (decision 2026-08-23). It is,
    however, worth being able to see: without this, run 2 looks identical to a
    first run in the manifest, and `checks --post` cannot tell you it is judging
    a re-run. Counting is all this does — nothing keys off it.
    """
    if not os.path.exists(MANIFEST):
        return 1
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        return 1                       # unreadable manifest: assume a fresh day
    if prev.get("date") != date:
        return 1
    return int(prev.get("run") or 1) + 1


def archive_paths(date):
    """Everything a re-run overwrites that you would want to diff afterwards.

    Real-tree relative, so the archive mirrors `output/` and a path in the
    archive tells you exactly where it came from. Three groups:

      * the report itself — the deliverable
      * the DATED artefacts for this date — what the manifest fingerprints, what
        `tools/eval_reviewer.py` compares the report to, and what a re-run
        silently replaces because they carry the same date

    Missing entries are skipped, not an error: a `--skip`ped step leaves its
    artefact untouched and there is nothing to preserve.
    """
    rel = [f"evaluation_{date}.md"]
    for pat in (f"data/facts_{date}.*", f"data/fundamentals_{date}.*",
                f"data/darkpool_{date}.*", f"data/xray_{date}.*",
                f"data/analyst_{date}.*", f"radar/Heartbeat_Radar_{date}.md"):
        rel += [os.path.relpath(p, OUTPUT_DIR)
                for p in sorted(glob.glob(os.path.join(OUTPUT_DIR, pat)))]
    seen, out = set(), []
    for r in rel:                       # the globs can overlap each other
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def archive_prior_run(date, run):
    """Copy the outgoing run's artefacts aside before this run overwrites them.

    WHY THE REPORT ALONE WAS NOT ENOUGH. The first version of this archived only
    `evaluation_<date>.md`. Run 2 of 2026-08-23 showed why that is half a
    mechanism: seven names flipped between AVOID and WAIT across two runs of the
    same closed-market day, and **the question "did the inputs move, or did the
    Trader just decide differently?" could not be answered** — Phase A had
    already overwritten facts, fundamentals, darkpool, xray and the radar in place.
    A report you cannot diff against its own inputs is a report you cannot
    audit. So the whole input set goes with it.

    The tree has no VCS and no Time Machine; 2026-08-23 also spent two
    evaluations to a silent overwrite (see the tombstones). Copying is cheap —
    the five fingerprinted artefacts total ~84 KB — and the cost of not having
    them is a question that can never be answered later.

    Returns the archive directory, or None if there was nothing to keep.
    """
    if run == 1:
        return None
    dest = os.path.join(STATE_DIR, "runs", date, f"run{run - 1}")
    kept, failed = [], []
    for rel in archive_paths(date):
        src = os.path.join(OUTPUT_DIR, rel)
        if not os.path.exists(src):
            continue
        dst = os.path.join(dest, rel)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            kept.append(rel)
        except OSError as e:
            failed.append(f"{rel} ({e})")
    # The manifest is not under output/ in the same sense — it is the record of
    # HOW the outgoing run was produced (step exits, timings, artefact sha1s),
    # which is exactly what you want beside its artefacts.
    # Stored at its REAL relative path (`.state/run_manifest.json`), not at the
    # archive root: `compare_runs` walks the archive and looks each file up at
    # the same path under the live tree, so an archive that does not mirror the
    # tree exactly reports a phantom difference. Caught by test 2026-08-23 —
    # the root-level copy showed as "absent" on an otherwise identical tree.
    man_rel = os.path.relpath(MANIFEST, OUTPUT_DIR)
    if os.path.exists(MANIFEST):
        try:
            dst = os.path.join(dest, man_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(MANIFEST, dst)
            kept.append(man_rel)
        except OSError as e:
            failed.append(f"{man_rel} ({e})")

    if failed:
        # Loud, and it does NOT stop the run: refusing to run because a backup
        # failed is the blocking behaviour this whole change exists to remove.
        # The human decides whether to proceed.
        print(f"[run] ⚠️  could not archive {len(failed)} file(s) — run {run} "
              f"will overwrite them with no copy retained: "
              + "; ".join(failed), file=sys.stderr)
    return dest if kept else None


def compare_runs(date, a_run, b_run):
    """Print a per-file same/differs table between two archived runs.

    The point of the archive: separating "the data moved" from "the Trader
    decided differently". `b_run` may be omitted, in which case the live tree is
    the comparison — the usual case, since the current run's artefacts are still
    on disk.
    """
    base = os.path.join(STATE_DIR, "runs", date)
    a_dir = os.path.join(base, f"run{a_run}")
    if not os.path.isdir(a_dir):
        print(f"[run] no archive at {os.path.relpath(a_dir, ROOT)}", file=sys.stderr)
        avail = sorted(os.listdir(base)) if os.path.isdir(base) else []
        print(f"[run] archived runs for {date}: {avail or 'none'}", file=sys.stderr)
        return 1
    b_dir = os.path.join(base, f"run{b_run}") if b_run else OUTPUT_DIR
    b_name = f"run{b_run}" if b_run else "live tree"
    if b_run and not os.path.isdir(b_dir):
        print(f"[run] no archive at {os.path.relpath(b_dir, ROOT)}", file=sys.stderr)
        return 1

    rows, differ = [], 0
    for root, _, files in os.walk(a_dir):
        for fn in sorted(files):
            if fn.startswith("_"):
                continue            # `_NOTE.md` and friends are prose about the
                                    # archive, not artefacts to diff
            ap = os.path.join(root, fn)
            rel = os.path.relpath(ap, a_dir)
            bp = os.path.join(b_dir, rel)
            if not os.path.exists(bp):
                rows.append(("absent", rel)); differ += 1
            elif sha1(ap) == sha1(bp):
                rows.append(("same", rel))
            else:
                rows.append(("DIFFERS", rel)); differ += 1
    print(f"[run] run{a_run} vs {b_name} — {date}")
    for status, rel in sorted(rows, key=lambda r: (r[0] == "same", r[1])):
        print(f"  {status:8s} {rel}")
    print(f"[run] {differ} of {len(rows)} file(s) differ")
    if not differ:
        print("[run] inputs identical — any change in the calls is judgement, "
              "not data")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    ap.add_argument("--skip", action="append", default=[],
                    help="step name to skip (repeatable), e.g. --skip radar")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--compare-runs", metavar="A[:B]",
                    help="diff an archived run's Phase A artefacts against "
                         "another archived run, or against the live tree if B "
                         "is omitted. e.g. --compare-runs 1  or  1:2")
    a = ap.parse_args()

    if a.compare_runs:
        parts = a.compare_runs.split(":")
        try:
            a_run = int(parts[0])
            b_run = int(parts[1]) if len(parts) > 1 and parts[1] else None
        except ValueError:
            print("[run] --compare-runs wants run numbers, e.g. 1 or 1:2",
                  file=sys.stderr)
            return 2
        return compare_runs(datetime.date.today().isoformat(), a_run, b_run)

    plan = [(n, c) for n, c in STEPS if n not in a.skip]
    if a.dry_run:
        for n, c in plan:
            print(f"[run] would run {n}: {' '.join(c)}")
        return 0

    date = datetime.date.today().isoformat()
    run = run_number(date)
    if run > 1:
        print(f"[run] ℹ️  run {run} of {date} — this is a re-run, which is "
              f"supported. The radar keeps the previous DAY's flag baseline; "
              f"the ledger de-dupes on Date+Ticker+Action; rotation and NAV "
              f"history replace today's point rather than duplicating it.")
        kept = archive_prior_run(date, run)
        if kept:
            n = sum(len(f) for _, _, f in os.walk(kept))
            print(f"[run] ℹ️  run {run - 1} archived — {n} file(s) "
                  f"(evaluation, Phase A artefacts, manifest) → "
                  f"{os.path.relpath(kept, ROOT)}")
            print(f"[run] ℹ️  after this run: python3 tools/run_daily.py "
                  f"--compare-runs {run - 1}   # did the inputs move, or just "
                  f"the calls?")

    manifest = {"date": date,
                "run": run,
                "started": datetime.datetime.now().isoformat(timespec="seconds"),
                "steps": [], "radar": {}, "artefacts": {}}
    failed = None
    for name, cmd in plan:
        t0 = time.time()
        print(f"\n[run] ▶ {name}: {' '.join(cmd)}")
        r = subprocess.run(cmd, cwd=ROOT)
        secs = round(time.time() - t0, 1)
        manifest["steps"].append({"name": name, "cmd": " ".join(cmd),
                                  "exit": r.returncode, "seconds": secs})
        if r.returncode != 0:
            # checks-post legitimately fails on "ledger touched" before the
            # Trader has run — record it, keep the manifest, but say so loudly.
            failed = name
            print(f"[run] ⛔ {name} exited {r.returncode} after {secs}s — halting")
            break
        print(f"[run] ✅ {name} ({secs}s)")

    verdict, detail = radar_verdict()
    manifest["radar"] = {"verdict": verdict, "detail": detail}
    for rel in artefacts(date):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            real = os.path.realpath(p)
            manifest["artefacts"][rel] = {
                "mtime": datetime.datetime.fromtimestamp(
                    os.path.getmtime(real)).isoformat(timespec="seconds"),
                "sha1": sha1(real)}
    manifest["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    manifest["ok"] = failed is None
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)

    print(f"\n[run] manifest → {os.path.relpath(MANIFEST, ROOT)} (run {run} of {date})")
    print(f"[run] radar: {verdict} — {detail}")
    print(f"[run] {'OK — agents may run (Analyst → Trader → Reviewer)' if not failed else f'FAILED at {failed} — fix and re-run before any agent consumes these artefacts'}")
    return 0 if failed is None else 1


if __name__ == "__main__":
    sys.exit(main())
