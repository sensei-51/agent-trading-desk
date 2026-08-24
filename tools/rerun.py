#!/usr/bin/env python3
"""
rerun.py — run the pipeline a second (third, tenth) time on the same day.

WHY THIS EXISTS — AND WHAT IT IS NO LONGER FOR.

The pipeline was built to run once per calendar day and its state files said so,
which made a same-day re-run collide with the first run rather than repeat it.
As of 2026-08-23 that is fixed at source: **a plain second `run_daily.py` is
supported**, and you do not need this script for one. The collisions and where
they now live:

  * `output/.state/radar_state.json` is "flags as of the previous run", and the
    day's first run overwrote yesterday's copy — so run 2 diffed today against
    today and reported zero new flags. FIXED: the first run of a day now rotates
    the outgoing file to `radar_state.prev.json`, and any run that finds
    `radar_state.json` already dated today reads the baseline instead
    (`engine/heartbeat_radar.py`, "THE SAME-DAY RE-RUN PROBLEM").
  * `output/.state/trader_timings_<date>.json` is keyed on the date and the CLI
    `time_run.py mark` path APPENDED to whatever was there, landing run 2's
    `start` after run 1's `end` so `in_order` went False and the durations
    became nonsense. FIXED: a CLOSED record rotates into `previous_runs[]` and
    the new run starts a fresh phase list (`tools/time_run.py`,
    `closed_run_on_disk`).
  * `output/evaluation_<date>.md` is overwritten in place — the first run's
    report destroyed with no trace, in a repo with no VCS. FIXED: `run_daily.py`
    copies it to `.state/evaluation_<date>.run<N>.md` first.
  * the ledger's today-dated rows are rewritten. NEVER A PROBLEM since
    2026-08-23: `append_gate_ledger.commit()` replaces this date's own
    `daily-eval` rows rather than appending beside them, so run 2 leaves one
    row per decision and it is run 2's. Rows from any other source, including a
    position entered by hand today, are not its to touch.
  * `output/.state/rotation_history.json` and `nav_history.json` de-dupe on
    date, so the second run silently *replaces* the first run's point — fine
    for correctness, but it means the first run's numbers are gone. STILL TRUE,
    and deliberately so; `checks.py --pre` says it out loud on a re-run.

`checks.py --pre` now reports "run N of <date>" as a WARN — visible, never
fatal. So what is left for this script is the two things a plain re-run is not:

Two ways out, both here:

  SANDBOX (default) — copy `output/` to `.rerun/<date>/run_NN/output`, point
  TP_OUTPUT at the copy, and run there. Every tool in the tree already honours
  TP_OUTPUT (run_daily, checks, facts, fundamentals, xray, time_run,
  append_gate_ledger, pnl, heartbeat_radar), so the real tree is never touched
  and you can re-run as many times as you like. This is what you want for
  testing.

  IN-PLACE (`--in-place`) — snapshot today's state, roll it back to
  "before this morning's run", then run for real in `output/`. Use this when
  the morning run was wrong and you want the day's artefacts REPLACED — in
  particular when you need today's committed ledger rows stripped, which a
  plain re-run will not do (it de-dupes instead). `--restore` puts the
  snapshot back. If you just want to run the pipeline again, do not use this:
  run `run_daily.py` (or `/atd-daily`) a second time.

Usage
    python3 tools/rerun.py                      # sandbox run of the full pipeline
    python3 tools/rerun.py -- --skip radar      # args after -- go to run_daily.py
    python3 tools/rerun.py --seed empty         # cold-start sandbox (no prior state)
    python3 tools/rerun.py --no-run             # just build the sandbox, print the env
    python3 tools/rerun.py --list               # sandboxes and snapshots
    python3 tools/rerun.py --in-place           # reset today's real state, then run
    python3 tools/rerun.py --in-place --no-run  # reset only
    python3 tools/rerun.py --restore            # undo the last in-place reset
    python3 tools/rerun.py --dry-run ...        # print what would happen

Standard library only.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REAL_OUTPUT = os.path.join(ROOT, "output")
SANDBOX_ROOT = os.path.join(ROOT, ".rerun")
SNAP_ROOT = os.path.join(REAL_OUTPUT, ".state", "rerun_snapshots")
BASELINE_DIR = os.path.join(REAL_OUTPUT, ".state", "rerun_baseline")

PY = sys.executable or "python3"
IGNORE = shutil.ignore_patterns("__pycache__", ".DS_Store", "rerun_snapshots")

# The radar's bar cache (`output/.state/bars/`, ~6 MB) IS copied into a sandbox,
# deliberately. It costs ~6 MB per retained sandbox and buys two things: the
# sandboxed run fetches 0.2 MB instead of 7 MB, and — the reason that matters —
# it reproduces a normal day, where the cache is warm. A cold-cache sandbox
# would exercise a path the real run almost never takes. The sandbox writes to
# its own copy, so the real cache is never touched by a re-run.


def today():
    return datetime.date.today().isoformat()


def stamp():
    return datetime.datetime.now().strftime("%H%M%S")


def say(msg):
    print(f"[rerun] {msg}")


# ---------------------------------------------------------------- sandbox mode


def next_sandbox(date):
    day = os.path.join(SANDBOX_ROOT, date)
    n = 1
    while os.path.exists(os.path.join(day, f"run_{n:02d}")):
        n += 1
    return os.path.join(day, f"run_{n:02d}")


def build_sandbox(date, seed, dry):
    dest = next_sandbox(date)
    out = os.path.join(dest, "output")
    rel = os.path.relpath(out, ROOT)
    if dry:
        say(f"would create sandbox {rel} (seed={seed})")
        return out
    os.makedirs(dest, exist_ok=True)
    if seed == "copy" and os.path.isdir(REAL_OUTPUT):
        shutil.copytree(REAL_OUTPUT, out, symlinks=True, ignore=IGNORE)
        say(f"sandbox {rel} seeded from output/ "
            f"({sum(len(f) for _, _, f in os.walk(out))} files)")
    else:
        for sub in ("", ".state", "data", "radar", "ledger", "reports"):
            os.makedirs(os.path.join(out, sub), exist_ok=True)
        say(f"sandbox {rel} created empty (cold start)")
    return out


def prune_sandboxes(keep, dry):
    if not os.path.isdir(SANDBOX_ROOT):
        return
    runs = []
    for day in os.listdir(SANDBOX_ROOT):
        d = os.path.join(SANDBOX_ROOT, day)
        if not os.path.isdir(d):
            continue
        for r in os.listdir(d):
            p = os.path.join(d, r)
            if os.path.isdir(p):
                runs.append((os.path.getmtime(p), p))
    runs.sort()
    for _, p in runs[:-keep] if keep > 0 else runs:
        if dry:
            say(f"would prune old sandbox {os.path.relpath(p, ROOT)}")
        else:
            shutil.rmtree(p, ignore_errors=True)
            say(f"pruned old sandbox {os.path.relpath(p, ROOT)}")


# --------------------------------------------------------------- in-place mode

def state(name):
    return os.path.join(REAL_OUTPUT, ".state", name)


def snapshot_paths(date):
    """Everything a same-day re-run would clobber, real-tree relative."""
    return [
        os.path.join(".state", "run_manifest.json"),
        os.path.join(".state", f"trader_timings_{date}.json"),
        os.path.join(".state", f"eval_draft_{date}.md"),
        os.path.join(".state", "radar_state.json"),
        # The previous-DAY flag baseline, rotated here by the day's first run
        # (added 2026-08-23 when a plain second run became supported). An
        # in-place reset rolls the day back, so the baseline has to roll back
        # with it — otherwise `--restore` returns a radar_state.json that no
        # longer has a matching baseline and "new today" goes wrong for a day.
        os.path.join(".state", "radar_state.prev.json"),
        # Dated, so a same-day re-run overwrites *this date's* snapshot and no
        # other. Snapshotted for the same reason as the report itself: the
        # pre-re-run numbers are the only record of what the first run saw.
        os.path.join(".state", f"radar_snapshot_{date}.json"),
        os.path.join(".state", "nav_history.json"),
        os.path.join(".state", "rotation_history.json"),
        os.path.join(".state", "ticker_resolution.json"),
        # `.state/bars/` is deliberately NOT here. A re-run does append to it,
        # but it is a derived, self-healing cache: losing it costs one full
        # refetch and nothing else. Every other entry in this list is a record
        # of what a run SAW, which is the thing a re-run would destroy.
        f"evaluation_{date}.md",
        "latest.md",
        os.path.join("ledger", "Gate_Ledger.csv"),
        os.path.join("data", "latest.md"),
        os.path.join("data", "fundamentals_latest.md"),
        os.path.join("data", "xray_latest.md"),
        os.path.join("radar", "latest.md"),
    ]


def take_snapshot(date, dry):
    snap = os.path.join(SNAP_ROOT, f"{date}_{stamp()}")
    kept = 0
    for rel in snapshot_paths(date):
        src = os.path.join(REAL_OUTPUT, rel)
        if not os.path.lexists(src):
            continue
        kept += 1
        if dry:
            continue
        dst = os.path.join(snap, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.islink(src):
            os.symlink(os.readlink(src), dst)
        else:
            shutil.copy2(src, dst)
    if dry:
        say(f"would snapshot {kept} file(s) → "
            f"{os.path.relpath(os.path.join(SNAP_ROOT, date + '_' + stamp()), ROOT)}")
    else:
        say(f"snapshot: {kept} file(s) → {os.path.relpath(snap, ROOT)}")
    return snap


def capture_baseline(date, dry):
    """Save radar_state.json as it was BEFORE the day's first re-run.

    radar_state.json is 'flags as of the previous run'. The day's first run
    already consumed yesterday's copy; the first time rerun.py sees a given
    date we keep whatever is there so later resets can hand the radar a
    plausible prior state instead of an empty one (empty means *no* flag is
    reported as new).
    """
    src = state("radar_state.json")
    dst = os.path.join(BASELINE_DIR, f"radar_state_{date}.json")
    if os.path.exists(dst):
        return dst                      # captured by an earlier reset today
    if not os.path.exists(src):
        return None
    if dry:
        say(f"would capture radar baseline → {os.path.relpath(dst, ROOT)} "
            "(first reset of the day: nothing to restore from yet)")
        return None
    os.makedirs(BASELINE_DIR, exist_ok=True)
    shutil.copy2(src, dst)
    say(f"captured radar baseline → {os.path.relpath(dst, ROOT)}")
    return None                         # nothing earlier to restore on this pass


def drop_json_entries(path, key, date, container, dry):
    """Remove entries dated `date` from a {container: [ {key: date, ...} ]} file."""
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (ValueError, OSError) as e:
        say(f"⚠️  {os.path.relpath(path, ROOT)} does not parse ({e}) — left alone. "
            "Note heartbeat_radar.py swallows this error and starts a fresh "
            "history, so streaks silently reset to 1/NEW until it is fixed.")
        return
    rows = doc.get(container, [])
    keep = [r for r in rows if r.get(key) != date]
    if len(keep) == len(rows):
        return
    if dry:
        say(f"would drop {len(rows) - len(keep)} {date} entry(ies) from "
            f"{os.path.relpath(path, ROOT)}")
        return
    doc[container] = keep
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    say(f"dropped {len(rows) - len(keep)} {date} entry(ies) from "
        f"{os.path.relpath(path, ROOT)}")


def strip_ledger_rows(date, dry):
    path = os.path.join(REAL_OUTPUT, "ledger", "Gate_Ledger.csv")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    keep = [ln for ln in lines if not ln.startswith(date)]
    n = len(lines) - len(keep)
    if not n:
        return
    if dry:
        say(f"would strip {n} row(s) dated {date} from ledger/Gate_Ledger.csv")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(keep)
    say(f"stripped {n} row(s) dated {date} from ledger/Gate_Ledger.csv "
        "(snapshotted — the ledger is append-only in normal use)")


def repoint_latest(date, dry):
    """Refresh output/latest.md from the newest evaluation that is not today's.

    latest.md is a plain copy, not a symlink — see the note in
    `engine/heartbeat_radar.py` and docs/BACKLOG.md item 19.
    """
    link = os.path.join(REAL_OUTPUT, "latest.md")
    cands = sorted(f for f in os.listdir(REAL_OUTPUT)
                   if re.fullmatch(r"evaluation_\d{4}-\d{2}-\d{2}\.md", f)
                   and f != f"evaluation_{date}.md")
    target = cands[-1] if cands else None
    if dry:
        say(f"would refresh latest.md ← {target or '(removed — no prior evaluation)'}")
        return
    if os.path.lexists(link):
        os.remove(link)
    if target:
        shutil.copyfile(os.path.join(REAL_OUTPUT, target), link)
        say(f"latest.md ← {target}")
    else:
        say("latest.md removed (no prior evaluation to point at)")


def remove(path, dry, why=""):
    if not os.path.lexists(path):
        return
    rel = os.path.relpath(path, ROOT)
    if dry:
        say(f"would remove {rel} {why}".rstrip())
        return
    os.remove(path)
    say(f"removed {rel} {why}".rstrip())


def reset_in_place(date, dry):
    if not os.path.isdir(REAL_OUTPUT):
        say("no output/ tree — nothing to reset")
        return
    baseline = capture_baseline(date, dry)
    take_snapshot(date, dry)

    remove(state("run_manifest.json"), dry, "(Phase A manifest)")
    remove(state(f"trader_timings_{date}.json"), dry,
           "(Phase B timings — the append-after-`end` bug)")
    remove(state(f"eval_draft_{date}.md"), dry)
    remove(os.path.join(REAL_OUTPUT, f"evaluation_{date}.md"), dry,
           "(today's evaluation — snapshotted)")
    repoint_latest(date, dry)
    strip_ledger_rows(date, dry)
    drop_json_entries(state("nav_history.json"), "date", date, "history", dry)
    drop_json_entries(state("rotation_history.json"), "date", date, "runs", dry)

    # PREFER THE RADAR'S OWN PREVIOUS-DAY BASELINE. Since 2026-08-23 the day's
    # first run rotates the outgoing radar_state.json to radar_state.prev.json,
    # which is genuinely yesterday's flags — strictly better than
    # capture_baseline()'s copy, which is only "whatever was there when rerun.py
    # first saw this date" and on the first reset of a day is today's own run.
    # capture_baseline stays as the fallback for a tree that predates the
    # rotation, or one where the baseline write failed.
    prev_day = state("radar_state.prev.json")
    if os.path.exists(prev_day):
        if dry:
            say("would restore radar_state.json from radar_state.prev.json "
                "(the radar's own previous-day baseline)")
        else:
            shutil.copy2(prev_day, state("radar_state.json"))
            say("restored radar_state.json from radar_state.prev.json "
                "(new-flag diff runs against the prior DAY)")
    elif baseline and os.path.exists(baseline):
        if dry:
            say("would restore radar_state.json from today's captured baseline")
        else:
            shutil.copy2(baseline, state("radar_state.json"))
            say("restored radar_state.json from today's captured baseline "
                "(new-flag diff runs against the prior day again)")
    else:
        say("⚠️  no radar_state.prev.json and first reset of " + date + " — "
            "radar_state.json left as-is. The day's prior-run state was already "
            "consumed by the morning run, so this run's new-flag counts are "
            "against the morning run, not yesterday. Later resets today restore "
            "the captured baseline.")


def restore_latest_snapshot(dry):
    if not os.path.isdir(SNAP_ROOT):
        say("no snapshots to restore")
        return 1
    snaps = sorted(os.path.join(SNAP_ROOT, d) for d in os.listdir(SNAP_ROOT)
                   if os.path.isdir(os.path.join(SNAP_ROOT, d)))
    if not snaps:
        say("no snapshots to restore")
        return 1
    snap = snaps[-1]
    n = 0
    for dirpath, _, files in os.walk(snap):
        for fn in files:
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, snap)
            dst = os.path.join(REAL_OUTPUT, rel)
            n += 1
            if dry:
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.lexists(dst):
                os.remove(dst)
            if os.path.islink(src):
                os.symlink(os.readlink(src), dst)
            else:
                shutil.copy2(src, dst)
    verb = "would restore" if dry else "restored"
    say(f"{verb} {n} file(s) from {os.path.relpath(snap, ROOT)}")
    say("note: files CREATED after the snapshot are not deleted by a restore")
    return 0


def do_list():
    print("sandboxes:")
    if os.path.isdir(SANDBOX_ROOT):
        for day in sorted(os.listdir(SANDBOX_ROOT)):
            d = os.path.join(SANDBOX_ROOT, day)
            if not os.path.isdir(d):
                continue
            for r in sorted(os.listdir(d)):
                p = os.path.join(d, r)
                ts = datetime.datetime.fromtimestamp(
                    os.path.getmtime(p)).isoformat(timespec="seconds")
                print(f"  {os.path.relpath(p, ROOT):<32} {ts}")
    else:
        print("  (none)")
    print("in-place snapshots:")
    if os.path.isdir(SNAP_ROOT):
        for s in sorted(os.listdir(SNAP_ROOT)):
            p = os.path.join(SNAP_ROOT, s)
            n = sum(len(f) for _, _, f in os.walk(p))
            print(f"  {os.path.relpath(p, ROOT):<32} {n} file(s)")
    else:
        print("  (none)")


# ----------------------------------------------------------------------- drive

def run_pipeline(output_dir, extra, dry):
    cmd = [PY, "tools/run_daily.py"] + list(extra)
    env = dict(os.environ, TP_OUTPUT=output_dir)
    shown = f"TP_OUTPUT={os.path.relpath(output_dir, ROOT)} {' '.join(cmd)}"
    if dry:
        say(f"would run: {shown}")
        return 0
    say(f"running: {shown}")
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    say(f"run_daily.py exited {r.returncode}")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[1].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-place", action="store_true",
                    help="reset today's state in the real output/ tree and run "
                         "there (default is an isolated sandbox copy)")
    ap.add_argument("--seed", choices=["copy", "empty"], default="copy",
                    help="sandbox seeding: copy output/ (default) or start cold")
    ap.add_argument("--no-run", action="store_true",
                    help="prepare/reset only; do not invoke run_daily.py")
    ap.add_argument("--restore", action="store_true",
                    help="restore the newest in-place snapshot and exit")
    ap.add_argument("--list", action="store_true",
                    help="list sandboxes and snapshots, then exit")
    ap.add_argument("--keep", type=int, default=5,
                    help="how many sandboxes to keep (default 5, 0 = keep all)")
    ap.add_argument("--date", default=None,
                    help="override the run date (default: today)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("rest", nargs="*",
                    help="args after `--` are passed to run_daily.py")
    a = ap.parse_args()

    if a.list:
        do_list()
        return 0
    if a.restore:
        return restore_latest_snapshot(a.dry_run)

    date = a.date or today()
    extra = [x for x in a.rest if x != "--"]

    if a.in_place:
        say(f"IN-PLACE re-run for {date} — the real output/ tree will change")
        reset_in_place(date, a.dry_run)
        if a.no_run:
            say("reset done (--no-run). `--restore` puts the snapshot back.")
            return 0
        return run_pipeline(REAL_OUTPUT, extra, a.dry_run)

    out = build_sandbox(date, a.seed, a.dry_run)
    prune_sandboxes(a.keep, a.dry_run)
    if a.no_run:
        say("sandbox ready (--no-run). Drive it yourself with:")
        print(f"\n  TP_OUTPUT={os.path.relpath(out, ROOT)} {PY} tools/run_daily.py\n")
        return 0
    rc = run_pipeline(out, extra, a.dry_run)
    if not a.dry_run:
        say(f"artefacts under {os.path.relpath(out, ROOT)} — the real output/ "
            "tree was not touched")
        say("Phase B in the same sandbox: "
            f"export TP_OUTPUT={os.path.relpath(out, ROOT)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
