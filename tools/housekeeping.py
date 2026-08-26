#!/usr/bin/env python3
"""
housekeeping.py — reclaim disk from the artefacts that are genuinely rebuilt,
and refuse to touch anything else.

WHY THIS EXISTS, AND WHY IT IS SHAPED LIKE A REFUSAL RATHER THAN A CLEANER.

This tree has **no version control**. `git` is not initialised in the private
repo, there is no Time Machine, and `docs/BACKLOG.md` items 19 and 22.3 are two
separate tombstones for evaluations that were silently overwritten and are gone
for good. In a tree like that, a cleaning script is not a convenience — it is the
single most dangerous program in `tools/`, because every other tool writes and
this one is the only one that unlinks. So the design premise is inverted from a
normal `clean` target: the question is never "what can I delete", it is "what can
I *prove* the next run rebuilds".

That premise produced three structural decisions, each of which is the reason a
particular failure cannot happen here:

  1. **Dry-run is the default and `--apply` is a second, typed decision.** A
     destructive default in a repo with no undo is one mistyped command away
     from a loss with no recovery path. `--apply` alone still stops and asks for
     the literal word DELETE on stdin; `--yes` is the escape hatch for a script,
     and it still prints the full plan first.
  2. **A deny-list checked at the unlink, not at the scan.** Every scanner below
     is already narrow — each walks one hard-coded root and yields one shape of
     file. That is the allow-list. But an allow-list is only as good as the
     scanner that implements it, and a future edit to a scanner is exactly the
     change nobody re-reads this docstring for. So `protected()` runs again on
     every single path immediately before it is removed, and on every member of
     every tree, and it does not care which scanner produced the path. Two
     independent gates; a bug has to appear in both to reach a protected file.
  3. **A tree with one protected member vetoes the whole tree.** `remove_tree`
     walks first, checks everything, and deletes nothing at all if any entry is
     protected. Partial deletion of a directory is the worst outcome available —
     it destroys data *and* leaves the thing looking cleaned.

WHAT IS PROTECTED, AND WHAT IT WOULD COST TO BE WRONG

  `output/ledger/**` — `Gate_Ledger.csv` is the system's **only durable memory**
      (AGENTS.md § Governance). Every other file under `output/` is a claim about
      a day; the ledger is the audit trail those claims are scored against by
      `tools/pnl.py`. It is append-only across all time and there is no second
      copy. `Gate_Ledger.csv.bak` is protected for the same reason and not a
      lesser one: a backup of the only durable memory is the recovery path.

  `input/capture/**` — the vendor captures. Each one costs a live browser session
      against a paid vendor's date picker, and they cannot be re-fetched for a
      past date. Verified 2026-08-26: all 12 darkpool captures are load-bearing,
      serving 48 scored decisions across 16 sessions through the ≤4-day backward
      lookup in `tools/darkpool_backfill.py`. Deleting one does not merely lose
      decisions — it silently **re-maps** them to an older capture, so the scorer
      still reports a clean count while scoring against data the decision never
      saw. A wrong number that looks right is worse than a missing one.

  `input/**` generally — broker CSVs (the position record), `watchlist*.md` and
      `tracking/*.md` (the theses), `tracking/sector_map.md` (the classification
      dictionary), `config/providers.json` (the live provider selection, which is
      gitignored and therefore has no upstream copy). `agents/orchestrator.md`
      states the rule the orchestrator already works under: **never edit
      `input/`.** This tool holds the same line one level lower down.

  `providers/**` — `providers/private/` is gitignored and unpublishable by
      construction (`tools/publish.py` builds the public tree by declining to
      copy it). Gitignored means there is no remote that has ever seen it.

  `output/**` — the whole real output tree, and this is the finding that most
      surprised the investigation. The brief's obvious candidate was "superseded
      dated files under `output/data/`, `output/radar/`, `output/reports/`", and
      the obvious candidate is wrong. AGENTS.md's "every other file under
      `output/` is rebuilt by the next run" is true of **today's** artefacts and
      only those. `output/data/facts_2026-08-13.md` is rebuilt by nothing:
      `tools/facts.py` fetches live prices, 52-week highs and consensus PTs, and
      no flag asks it for the afternoon of the 13th. Every dated facts,
      fundamentals, x-ray, radar and P&L file is a point-in-time record of what a
      run **saw** — which is exactly what the ledger's decisions have to be
      audited against for the ledger to be worth keeping. The whole history is
      ~2 MB. Unreproducible and cheap is the worst possible thing to delete, so
      nothing under `output/` is removable here except the OS/interpreter
      ephemera named in `ALWAYS_EPHEMERAL_*`.

  `output/.state/runs/**` — see the review-only section below. Not deletable at
      any retention, deliberately.

  Every named state file under `output/.state/` — enumerated in `PROTECTED_NAMES`
      with the reason each one is load-bearing. Three of these were nearly
      classified as junk during this tool's own design and are worth naming:

      * `rotation_history.backup-2026-08-16.json` **looks** like a stale hand
        backup and is in fact a **live recovery path**:
        `engine/heartbeat_radar.py:_rotation_backup_path` globs
        `rotation_history.backup-*.json` and reads the newest one when the
        primary will not parse. Deleting it removes the only fallback for the
        rotation history.
      * `run_manifest.backup-2026-08-21-preRestamp.json` is **cited by name** in
        the body of `output/evaluation_2026-08-21.md` as the retained pre-restamp
        manifest. Deleting it turns a shipped report's evidence into a dead
        reference.
      * `review_2026-08-23.json.new` looks like an interrupted atomic write. It
        is not: it carries `PASS WITH DEFECTS` and a real numbered defect, where
        the `.json` beside it carries a bare `PASS`. The `.new` file is the
        *richer* record, and it is the only copy of that defect.

      The generalisation is the point: in this tree, `*.backup-*`, `*.bak` and
      `*.new` under `output/` are **not** a temp-file convention. Three files
      matching those patterns were checked and three were load-bearing. So the
      patterns are on the deny-list, not the sweep list.

WHAT IT ACTUALLY CLEANS, AND WHY EACH IS SAFE

  pycache     `__pycache__/` and `*.pyc` / `*.pyo`, tree-wide. Regenerated by the
              interpreter on the next import, deterministically, from source that
              is right there. Cost of being wrong: one slower import. This is the
              only category with genuinely zero downside.

  ds_store    `.DS_Store`, tree-wide. Finder's per-directory view metadata.
              Gitignored, never read by anything in this repo, and recreated by
              Finder the moment the folder is opened again. Cost of being wrong:
              an icon layout.

  sandboxes   `.rerun/<date>/run_NN/`, for date directories older than
              `--keep-days`. A sandbox is a **copy** of `output/` that
              `tools/rerun.py` makes so a test re-run never touches the real
              tree; its contents are by construction either a copy of something
              still in `output/` or the product of a run that was explicitly not
              the real one. The precedent is unimpeachable: `rerun.py` already
              deletes these itself — `prune_sandboxes()` keeps the newest 5 on
              every sandbox run. This tool prunes on age instead of count because
              age is what makes a *test* run stale, and it declines to touch
              today's. Cost of being wrong: a test you would have re-run anyway.

  toolbackups `.backup/<name>.<stamp>.bak`, older than `--keep-days`, **and only
              where the live original still exists**. These are pre-edit
              snapshots of source files. If the original is present, the backup is
              a superseded copy of a file that is itself under `tools/`; if the
              original is missing, the backup is the only copy and this tool will
              not offer it at any age. `tools/publish.py` excludes `.backup/` from
              the public tree, so nothing downstream depends on it.

WHAT IT FINDS AND REFUSES TO CLEAN (`--review` output, never deleted)

  run_archives  `output/.state/runs/<date>/run<N>/`. `tools/run_daily.py` writes
              these before a same-day re-run overwrites the outgoing run's
              report and Phase A artefacts, so that "did the data move, or did
              the Trader decide differently?" stays answerable
              (`archive_prior_run`, and `docs/BACKLOG.md` item 22.3). It is
              tempting to age these out, because the only reader —
              `--compare-runs` — hard-codes **today's** date, so an archive under
              any other date directory is already unreachable by code. It is
              still wrong to delete them, and the reason is that reachability is
              not the test: these are the **only surviving copies** of superseded
              runs' evaluations, facts, fundamentals, darkpool, xray and radar
              output. None of that is regenerable — `facts.py` fetches live
              prices and cannot be asked for a past afternoon. The live tree
              keeps only the *final* run of each day. So the whole archive costs
              ~1.6 MB to keep and an unanswerable question to lose, and this tool
              reports it rather than offering it.

  orphans     Files under `output/` that match no known producer's naming
              pattern. Reported for a human to look at, never deleted, because
              "no tool writes this name" and "a human wrote this by hand" are
              indistinguishable from the outside — and in this tree the very
              in this tree the very first hit is a hand-written comparison note
              that no tool has ever produced and nothing could reproduce.

  Two more, listed here so the next reader does not have to rediscover them:
  `output/.state/bars/` (~6 MB) is the radar's OHLCV cache — regenerable, but
  only by re-fetching every ticker's full history from the network, and
  `rerun.py` deliberately copies it into sandboxes so a test run exercises the
  warm-cache path a real run takes. `.opencode/node_modules/` (~61 MB, the
  largest single directory in the tree) is an npm install, regenerable but only
  with network access and a working registry, and deleting it breaks the
  opencode platform until someone reinstalls. Neither is this tool's business.

Usage
    python3 tools/housekeeping.py                    # dry run — the default
    python3 tools/housekeeping.py --keep-days 14     # gentler retention
    python3 tools/housekeeping.py --only pycache,ds_store
    python3 tools/housekeeping.py --skip sandboxes
    python3 tools/housekeeping.py --apply            # asks for the word DELETE
    python3 tools/housekeeping.py --apply --yes      # scripted; still prints the plan
    python3 tools/housekeeping.py --review           # only the never-deleted findings
    python3 tools/housekeeping.py --self-test        # prove the deny-list holds

Exit 0 = nothing went wrong (a dry run always exits 0). Exit 1 = a refusal fired,
a removal failed, or `--self-test` found a hole.

Standard library only.
"""

import argparse
import datetime
import fnmatch
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

OUTPUT_DIR = os.path.join(ROOT, "output")
STATE_DIR = os.path.join(OUTPUT_DIR, ".state")
SANDBOX_ROOT = os.path.join(ROOT, ".rerun")
TOOL_BACKUP_DIR = os.path.join(ROOT, ".backup")

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# --------------------------------------------------------------------------
# THE DENY-LIST.
#
# Everything below is expressed relative to ROOT and compared with realpath
# containment, so a symlink cannot be used to walk into a protected tree from a
# candidate that looks innocent. This list is deliberately wider than the set of
# things any scanner could produce: its job is to be the second gate, and a
# second gate that only restates the first one is not a second gate.
# --------------------------------------------------------------------------

PROTECTED_TREES = {
    # The only durable memory. Nothing under here, backups included.
    "output/ledger": "the gate ledger — the system's only durable memory",
    # Vendor captures, broker exports, watchlists, theses, sector map, provider
    # config. Expensive-to-impossible to recreate; the orchestrator's own
    # contract says never edit input/.
    "input": "human/vendor input — captures, broker CSVs, watchlists, config",
    # Gitignored, unpublishable, no remote has ever seen it.
    "providers": "provider adapters, incl. the private gitignored ones",
    # Source and contracts. A cleaner has no business in any of these.
    "tools": "source",
    "engine": "source",
    "agents": "canonical agent + command bodies",
    "rules": "rulebooks",
    "docs": "contracts and architecture",
    "templates": "report templates",
    ".claude": "platform wrappers and settings",
    ".opencode": "platform wrappers and settings",
    # Superseded runs' reports and inputs — the only copies. See the docstring.
    "output/.state/runs": "same-day re-run archives — the only copy of a "
                          "superseded run's report and its inputs",
    # The radar's OHLCV cache: regenerable only from the network.
    "output/.state/bars": "radar OHLCV cache — regenerable only by refetching "
                          "every ticker's full history",
    # THE WHOLE REAL OUTPUT TREE. This is the conclusion of the investigation
    # that produced this tool, and it is deliberately blunt: nothing under
    # `output/` is removable by this tool except the OS/interpreter ephemera in
    # ALWAYS_EPHEMERAL_*. The obvious candidate was "superseded dated files
    # under output/data, output/radar, output/reports" — and the obvious
    # candidate is wrong. AGENTS.md's "every other file under output/ is
    # rebuilt by the next run" is true of TODAY's artefacts and only those. A
    # `facts_2026-08-13.md` is not rebuilt by anything: `tools/facts.py` fetches
    # live prices, 52-week highs and consensus PTs, and there is no way to ask
    # it for the afternoon of the 13th. The same holds for every dated
    # fundamentals sheet, radar report, x-ray and P&L — each is a point-in-time
    # record of what a run SAW, which is precisely what the ledger's decisions
    # are audited against. They are small (~2 MB for the entire history) and
    # unreproducible, which is the worst possible trade to make.
    "output": "the real output tree — dated artefacts are point-in-time "
              "records, not rebuilt by any later run",
    # An npm install. Regenerable only with network + registry.
    ".opencode/node_modules": "installed npm dependencies",
}

# Basename patterns protected anywhere under the REAL output tree. Scoped to
# `output/` on purpose: `.rerun/<date>/run_NN/output/` holds copies with these
# same names, and a copy inside a throwaway sandbox is not the record — the file
# it was copied from is, and that one lives under a PROTECTED_TREE or under
# `output/` where these patterns apply.
PROTECTED_NAMES = {
    "Gate_Ledger*": "the ledger, in any form",
    "evaluation_*.md": "a daily evaluation — the deliverable, not regenerable",
    "*.backup-*": "a dated backup; in this tree these are load-bearing "
                  "(rotation_history's is a live recovery path, "
                  "run_manifest's is cited in a shipped evaluation)",
    "*.bak": "a backup under output/",
    "*.new": "an interrupted-looking write that is not one "
             "(review_*.json.new carries the richer verdict)",
    "run_manifest*.json": "the run manifest the agents quote instead of "
                          "re-deriving",
    "radar_state*.json": "flag baseline — .prev.json is the previous DAY's, "
                         "and the new-flag diff runs against it",
    "rotation_history*.json": "sector rotation tag history",
    "nav_history.json": "NAV over time — the portfolio-growth chart's series",
    "position_history.json": "per-line history behind the x-ray's Movers",
    "ticker_resolution.json": "broker-symbol → Yahoo-ticker map, read by "
                              "checks.py and eval_reviewer.py",
    "radar_snapshot_*.json": "the dated numeric snapshot series; a gap in it is "
                             "only discoverable much later",
    "eval_manifest_*.json": "the Trader's per-run manifest",
    "eval_draft_*.md": "a drafted evaluation",
    "review_*.json": "the Reviewer's verdict record",
    "trader_timings_*.json": "Phase B durations + artefact fingerprints",
    ".gitkeep": "keeps a published directory in the tree",
}

# THE ONE CARVE-OUT, and the reasoning that keeps it from becoming a precedent.
#
# `.DS_Store` and `__pycache__`/`*.pyc` occur inside protected trees too —
# `tools/.DS_Store`, `providers/private/.DS_Store`, `engine/__pycache__`. Left to
# the tree rules alone they would be refused forever, which is a real functional
# loss for the two categories that carry no risk at all.
#
# So they are exempted from the TREE rules only, and only on an exact basename
# match against this closed set. The test that makes this safe is not "is it
# junk" — it is that these names are generated by the OS and the interpreter, are
# never authored, never carry repository content, and are reconstructed
# automatically the next time the directory is opened or the module imported.
# Nothing else clears that bar, which is why the set is closed and literal
# rather than a pattern anyone can extend.
#
# The exemption does NOT apply to symlinks (a link named `.DS_Store` is a
# smuggling attempt, not Finder metadata) and does NOT lift the outside-the-root
# rule or the PROTECTED_NAMES rules.
ALWAYS_EPHEMERAL_FILES = {".DS_Store"}
ALWAYS_EPHEMERAL_DIRS = {"__pycache__"}
ALWAYS_EPHEMERAL_SUFFIXES = (".pyc", ".pyo")

# Exemplars asserted unreachable by --self-test. Each is a real path in this
# tree (or a plausible one); the test fails if `protected()` returns None for
# any of them, or if any scanner ever yields one.
SELF_TEST_PATHS = (
    "output/ledger/Gate_Ledger.csv",
    "output/ledger/Gate_Ledger.csv.bak",
    "output/ledger/Gate_Ledger.example.csv",
    "output/ledger/.gitkeep",
    "input/capture/darkpool_2026-08-25.md",
    "input/capture/conviction_2026-08-19.md",
    "input/AJ Bell.csv",
    "input/ii.csv",
    "input/watchlist.md",
    "input/tracking/sector_map.md",
    "input/config/providers.json",
    # Deliberately fictional vendor names. `protected()` matches on the path
    # shape, not the module, so these test exactly what the real ones would —
    # and this file ships publicly, where a real provider name must not.
    "providers/private/fundamentals/acme.py",
    "providers/private/darkpool/acme.py",
    "output/.state/runs/2026-08-23/run2/evaluation_2026-08-23.md",
    "output/.state/bars/AAPL.csv",
    "output/.state/rotation_history.backup-2026-08-16.json",
    "output/.state/run_manifest.backup-2026-08-21-preRestamp.json",
    "output/.state/review_2026-08-23.json.new",
    "output/.state/evaluation_2026-08-20.backup-17-10.md",
    "output/.state/radar_state.prev.json",
    "output/evaluation_2026-08-25.md",
    "output/data/facts_2026-08-25.csv",
    "output/data/fundamentals_2026-08-18.md",
    "output/data/head_to_head_notes_2026-08-18.md",
    "output/radar/Heartbeat_Radar_2026-08-25.md",
    "output/reports/PnL_2026-08-13.md",
    "output/.state/nav_history.json",
    "output/.state/eval_draft_2026-08-20.md",
    "output/README.md",
    "tools/housekeeping.py",
    "engine/heartbeat_radar.py",
    "docs/TECHNICAL_ARCHITECTURE.md",
)


def rel(path):
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:                      # different drive — treat as outside
        return path


def within(child, parent):
    """True if `child` is `parent` or lives under it, resolving symlinks on both.

    `commonpath` rather than `startswith`: "output/ledger2" must not count as
    inside "output/ledger", and a string prefix test says it does.
    """
    c = os.path.realpath(child)
    p = os.path.realpath(parent)
    if c == p:
        return True
    try:
        return os.path.commonpath([c, p]) == p
    except ValueError:
        return False


def protected(path):
    """Return the reason `path` must not be removed, or None if it may be.

    THIS IS THE CHOKEPOINT. It is called on every candidate before removal and
    again on every member of every tree, regardless of which scanner produced
    it. It never consults the scanner's intent — that is the whole point of
    having it.
    """
    ap = os.path.abspath(path)

    # Anything that resolves outside the repo. Catches an absolute path passed
    # in by hand and a symlink pointing out of the tree alike.
    if not within(ap, ROOT):
        return "outside the repository root"
    if os.path.realpath(ap) == os.path.realpath(ROOT):
        return "the repository root itself"

    name = os.path.basename(ap)
    ephemeral = not os.path.islink(ap) and (
        name in ALWAYS_EPHEMERAL_FILES
        or name in ALWAYS_EPHEMERAL_DIRS
        or name.endswith(ALWAYS_EPHEMERAL_SUFFIXES))

    # Three phases, ordered so the MOST SPECIFIC reason is the one returned.
    # Safety does not depend on the order — every phase is a refusal and the
    # first hit wins either way — but the message does, and a refusal that
    # explains itself badly is a refusal someone will argue with.
    #
    #   1. nested trees   `output/ledger`, `output/.state/runs`, …
    #   2. basenames      the per-file reasons in PROTECTED_NAMES
    #   3. top-level      the catch-alls: `output`, `input`, `providers`, …
    nested = [(t, w) for t, w in PROTECTED_TREES.items() if "/" in t]
    toplevel = [(t, w) for t, w in PROTECTED_TREES.items() if "/" not in t]

    if not ephemeral:
        for tree, why in nested:
            if within(ap, os.path.join(ROOT, tree)):
                return f"{tree}/ — {why}"

    # Basename rules, scoped to the real output tree (see PROTECTED_NAMES).
    # Applied to ephemeral names too: `.gitkeep` lives in PROTECTED_NAMES and
    # must survive, and a future addition there must not be silently exempted.
    if within(ap, OUTPUT_DIR):
        for pat, why in PROTECTED_NAMES.items():
            if fnmatch.fnmatch(name, pat):
                return f"{pat} under output/ — {why}"

    if not ephemeral:
        for tree, why in toplevel:
            if within(ap, os.path.join(ROOT, tree)):
                return f"{tree}/ — {why}"

    # A symlink is judged by where it points as well as where it sits, so a link
    # planted inside a candidate tree cannot smuggle a protected target into a
    # recursive delete.
    if os.path.islink(ap):
        target = os.path.realpath(ap)
        if not within(target, ROOT):
            return "symlink pointing outside the repository root"
        for tree, why in PROTECTED_TREES.items():
            if within(target, os.path.join(ROOT, tree)):
                return f"symlink into {tree}/ — {why}"

    return None


# --------------------------------------------------------------------------
# Sizing and removal
# --------------------------------------------------------------------------

def size_of(path):
    """Bytes on disk for a file or a whole tree. `lstat` and `followlinks=False`
    throughout: a symlink counts as itself, never as what it points at, or a
    link into `output/` would report the target's megabytes as reclaimable.
    """
    if os.path.islink(path) or os.path.isfile(path):
        try:
            return os.lstat(path).st_size
        except OSError:
            return 0
    total = 0
    for dirpath, _dirs, files in os.walk(path, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def remove_one(path):
    """Remove one file or symlink. Re-checks `protected()` first, always."""
    why = protected(path)
    if why:
        raise PermissionError(f"refusing to remove {rel(path)}: {why}")
    os.remove(path)


def remove_tree(path):
    """Remove a directory tree, but only if NOT ONE member is protected.

    Walks and checks everything first. A tree containing a protected file is
    left entirely alone rather than partially emptied: a half-deleted directory
    destroys data and simultaneously looks like it was cleaned, which is the
    worst of both outcomes and the hardest to notice afterwards.
    """
    why = protected(path)
    if why:
        raise PermissionError(f"refusing to remove {rel(path)}: {why}")
    for dirpath, dirs, files in os.walk(path, followlinks=False):
        for name in list(dirs) + files:
            member = os.path.join(dirpath, name)
            mwhy = protected(member)
            if mwhy:
                raise PermissionError(
                    f"refusing to remove {rel(path)}: it contains "
                    f"{rel(member)} — {mwhy}")
    shutil.rmtree(path)


# --------------------------------------------------------------------------
# Scanners. Each yields (path, reason). Each walks ONE hard-coded root, and none
# of them is trusted — `protected()` runs again at the unlink either way.
# --------------------------------------------------------------------------

SKIP_WALK = {".git", "node_modules", ".venv", "venv"}


def walk_repo():
    """Walk the tree once, skipping directories nothing here should enter."""
    for dirpath, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_WALK]
        yield dirpath, dirs, files


def scan_pycache(_args):
    for dirpath, dirs, files in walk_repo():
        for d in list(dirs):
            if d == "__pycache__":
                dirs.remove(d)      # do not descend; the whole dir goes
                yield os.path.join(dirpath, d), \
                    "bytecode cache — the interpreter rebuilds it on next import"
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                yield os.path.join(dirpath, f), \
                    "stray bytecode — rebuilt on next import"


def scan_ds_store(_args):
    for dirpath, _dirs, files in walk_repo():
        for f in files:
            if f == ".DS_Store":
                yield os.path.join(dirpath, f), \
                    "Finder view metadata — gitignored, read by nothing here"


def stale_days(name, keep_days):
    """Days past retention for a `YYYY-MM-DD` directory name, or None if the
    name is not a date or the date is still inside the window.

    Date-directory granularity rather than mtime: a sandbox is stale because the
    DAY it was testing is over, not because nobody touched the folder.
    """
    m = DATE_RE.fullmatch(name)
    if not m:
        return None
    try:
        d = datetime.date.fromisoformat(name)
    except ValueError:
        return None
    age = (datetime.date.today() - d).days
    return age if age > keep_days else None


def scan_sandboxes(args):
    if not os.path.isdir(SANDBOX_ROOT):
        return
    for day in sorted(os.listdir(SANDBOX_ROOT)):
        p = os.path.join(SANDBOX_ROOT, day)
        if not os.path.isdir(p) or os.path.islink(p):
            continue
        age = stale_days(day, args.keep_days)
        if age is None:
            continue
        yield p, (f"rerun sandbox for {day}, {age}d old — a throwaway copy of "
                  f"output/ that rerun.py prunes itself (--keep 5)")


BAK_RE = re.compile(r"^(?P<orig>.+?)(?:\.\d{8}-\d{6})?\.bak(?:\.\w+)?$")


def live_original(bak_name):
    """Where the file this `.bak` was taken from lives now, or '' if nowhere.

    A backup whose original has since been deleted is the ONLY copy of that
    file, so it is never offered — regardless of age. This is the difference
    between pruning a superseded snapshot and quietly finishing a deletion
    somebody started by hand.
    """
    m = BAK_RE.match(bak_name)
    if not m:
        return ""
    orig = m.group("orig")
    for d in ("tools", "engine", "agents", "rules", "docs", "templates", ""):
        cand = os.path.join(ROOT, d, orig)
        if os.path.isfile(cand):
            return cand
    return ""


def scan_toolbackups(args):
    if not os.path.isdir(TOOL_BACKUP_DIR):
        return
    cutoff = args.keep_days * 86400.0
    now = datetime.datetime.now().timestamp()
    for f in sorted(os.listdir(TOOL_BACKUP_DIR)):
        p = os.path.join(TOOL_BACKUP_DIR, f)
        if not os.path.isfile(p) or os.path.islink(p):
            continue
        if ".bak" not in f:
            continue
        age = (now - os.lstat(p).st_mtime) / 86400.0
        if (now - os.lstat(p).st_mtime) <= cutoff:
            continue
        orig = live_original(f)
        if not orig:
            continue                # only copy of a file that no longer exists
        yield p, (f"pre-edit snapshot, {age:.0f}d old — the live original is "
                  f"still at {rel(orig)}")


CLEANABLE = {
    "pycache": scan_pycache,
    "ds_store": scan_ds_store,
    "sandboxes": scan_sandboxes,
    "toolbackups": scan_toolbackups,
}


# --------------------------------------------------------------------------
# Archive — reported here, performed by tools/archive.py.
#
# Clutter complaints usually want a MOVE, not a delete: `output/data/` reached
# 82 entries in fourteen days while weighing 1.1 MB. This tool surfaces the
# opportunity and deliberately cannot act on it — deleting works off a
# deny-list and is irreversible, archiving works off an allow-list and reverses
# with `mv`, and one flag that could do either invites the wrong reflex.
#
# `/atd-archive` and `tools/archive.py` own the operation. One implementation.
# --------------------------------------------------------------------------

from archive import scan_archive          # noqa: E402  (same directory)

ARCHIVE_REPORT_DAYS = 3


# --------------------------------------------------------------------------
# Review-only findings. These never enter the delete plan; there is no flag that
# promotes them, which is the point.
# --------------------------------------------------------------------------

PRODUCERS = {
    "": (r"evaluation_\d{4}-\d{2}-\d{2}\.md", r"README\.md", r"latest\.md",
         r"\.DS_Store", r"\.gitkeep"),
    "data": (r"(facts|fundamentals)_\d{4}-\d{2}-\d{2}\.(md|csv)",
             r"(xray|analyst)_\d{4}-\d{2}-\d{2}\.(md|json)",
             r"darkpool(_backfill)?_\d{4}-\d{2}-\d{2}\.md",
             r"\w+_latest\.(md|csv|json)", r"latest\.md", r"\.gitkeep"),
    "radar": (r"Heartbeat_Radar_\d{4}-\d{2}-\d{2}\.md", r"latest\.md",
              r"\.gitkeep"),
    "reports": (r"PnL_\d{4}-\d{2}-\d{2}\.md", r"latest\.md", r"\.gitkeep"),
}


def review_orphans():
    for sub, pats in PRODUCERS.items():
        d = os.path.join(OUTPUT_DIR, sub) if sub else OUTPUT_DIR
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if not os.path.isfile(p):
                continue
            if any(re.fullmatch(pat, f) for pat in pats):
                continue
            yield p, ("no tool in this repo produces this name — check by hand "
                      "before assuming it is junk")


def review_run_archives(args):
    base = os.path.join(STATE_DIR, "runs")
    if not os.path.isdir(base):
        return
    for day in sorted(os.listdir(base)):
        p = os.path.join(base, day)
        if not os.path.isdir(p):
            continue
        age = stale_days(day, args.keep_days)
        n = len([r for r in os.listdir(p) if os.path.isdir(os.path.join(p, r))])
        note = f"{n} archived run(s)"
        if age is not None:
            note += (f", {age}d old — unreachable by --compare-runs (which only "
                     f"looks at today), but the ONLY copy of those runs' "
                     f"reports and inputs")
        yield p, f"retained deliberately: {note}"


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def say(msg=""):
    print(f"[housekeeping] {msg}" if msg else "")


def build_plan(args):
    """Collect (category, path, reason, bytes), dropping anything protected.

    A scanner that yields a protected path is a bug in the scanner, and it is
    reported as REFUSED rather than skipped quietly — a deny-list that fires
    silently teaches nobody that the allow-list has a hole.
    """
    plan, refusals = [], []
    for name, scan in CLEANABLE.items():
        if name not in args.categories:
            continue
        for path, reason in scan(args):
            why = protected(path)
            if why:
                refusals.append((name, path, why))
                continue
            plan.append((name, path, reason, size_of(path)))
    return plan, refusals


def print_plan(plan, refusals, args):
    if refusals:
        for cat, path, why in refusals:
            say(f"⛔ REFUSED  {cat}: {rel(path)} — {why}")
        say()
    if not plan:
        say("nothing to clean — every candidate category is empty or inside "
            f"the {args.keep_days}-day retention window")
        return 0
    total = 0
    for cat in sorted({c for c, _, _, _ in plan}):
        items = [i for i in plan if i[0] == cat]
        sub = sum(i[3] for i in items)
        total += sub
        say(f"── {cat} — {len(items)} item(s), {human(sub)}")
        for _, path, reason, n in sorted(items, key=lambda i: -i[3]):
            say(f"   {human(n):>10}  {rel(path)}")
            say(f"   {'':>10}  ↳ {reason}")
        say()
    return total


def print_review(args):
    findings = list(review_run_archives(args)) + list(review_orphans())
    if not findings:
        return
    say("── review only — found, never deleted by this tool")
    for path, reason in findings:
        say(f"   {human(size_of(path)):>10}  {rel(path)}")
        say(f"   {'':>10}  ↳ {reason}")
    say()


def confirm():
    """Explicit, typed, and not a y/n.

    A y/n prompt in a tree with no undo is answered reflexively. Typing the word
    is the smallest gesture that cannot be made by muscle memory.
    """
    try:
        answer = input("[housekeeping] type DELETE to remove the items above: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip() == "DELETE"


def apply_plan(plan):
    freed, failed = 0, []
    for _cat, path, _reason, n in plan:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                remove_tree(path)
            else:
                remove_one(path)
            freed += n
            say(f"removed {rel(path)} ({human(n)})")
        except (PermissionError, OSError) as e:
            failed.append((path, e))
            say(f"⛔ {rel(path)}: {e}")
    return freed, failed


def self_test(args):
    """Prove the two gates hold, mechanically rather than by inspection.

    Test 1 — every exemplar in SELF_TEST_PATHS is refused by `protected()`,
    whether or not it exists on disk right now. A protection that only works on
    files that happen to be present is a protection that lapses the day one is
    restored.

    Test 2 — no scanner yields a protected path, at any retention. Run at
    keep_days=0, the most aggressive setting the CLI allows, because a gap that
    only appears at the loosest retention is the one that ships.
    """
    bad = []
    for r in SELF_TEST_PATHS:
        p = os.path.join(ROOT, r)
        why = protected(p)
        if not why:
            bad.append(f"NOT PROTECTED: {r}")
        else:
            say(f"✅ refused  {r}")
            say(f"            ↳ {why}")
    say()

    probe = argparse.Namespace(keep_days=0, categories=set(CLEANABLE))
    yielded, leaked = 0, 0
    for name, scan in CLEANABLE.items():
        for path, _reason in scan(probe):
            yielded += 1
            why = protected(path)
            if why:
                leaked += 1
                bad.append(f"SCANNER {name} yielded protected {rel(path)}: {why}")
    mark = "⛔" if leaked else "✅"
    say(f"{mark} scanners at keep-days=0 yielded {yielded} candidate(s), "
        f"{leaked} of them protected")
    say()
    if bad:
        for b in bad:
            say(f"⛔ {b}")
        say(f"SELF-TEST FAILED — {len(bad)} hole(s)")
        return 1
    say(f"SELF-TEST PASSED — {len(SELF_TEST_PATHS)} protected exemplar(s) "
        f"refused, no scanner reaches one")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[1],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default is a dry run); still asks "
                         "for a typed DELETE unless --yes")
    ap.add_argument("--yes", action="store_true",
                    help="skip the typed confirmation (for scripts). The plan "
                         "is still printed first")
    ap.add_argument("--keep-days", type=int, default=5, metavar="N",
                    help="retention for dated categories, in days "
                         "(default 5 — one trading week)")
    ap.add_argument("--only", metavar="A,B",
                    help=f"clean only these: {','.join(sorted(CLEANABLE))}")
    ap.add_argument("--skip", metavar="A,B", help="clean everything but these")
    ap.add_argument("--review", action="store_true",
                    help="print only the never-deleted findings and exit")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the protected paths are unreachable, then exit")
    args = ap.parse_args()

    if args.keep_days < 0:
        say("--keep-days must be >= 0")
        return 1

    cats = set(CLEANABLE)
    if args.only:
        want = {c.strip() for c in args.only.split(",") if c.strip()}
        unknown = want - cats
        if unknown:
            say(f"unknown category: {', '.join(sorted(unknown))} "
                f"(known: {', '.join(sorted(cats))})")
            return 1
        cats = want
    if args.skip:
        cats -= {c.strip() for c in args.skip.split(",") if c.strip()}
    args.categories = cats

    if args.self_test:
        return self_test(args)

    say(f"root {ROOT}")
    say(f"mode {'APPLY' if args.apply else 'DRY RUN — nothing will be deleted'} "
        f"· retention {args.keep_days}d · categories "
        f"{', '.join(sorted(cats)) or 'none'}")
    say()

    if args.review:
        print_review(args)
        return 0

    moves = list(scan_archive(ARCHIVE_REPORT_DAYS))
    if moves:
        say(f"── archive — {len(moves)} dated file(s) could fold into month "
            f"folders, freeing the listing without deleting anything")
        say(f"   run /atd-archive (or python3 tools/archive.py) — this tool "
            f"will not move them")
        say()

    plan, refusals = build_plan(args)
    total = print_plan(plan, refusals, args)
    print_review(args)

    if not plan:
        return 1 if refusals else 0

    if not args.apply:
        say(f"would reclaim {human(total)} across {len(plan)} item(s)")
        say("dry run — nothing was deleted. Re-run with --apply to remove.")
        return 1 if refusals else 0

    if not args.yes and not confirm():
        say("aborted — nothing was deleted")
        return 0

    say()
    freed, failed = apply_plan(plan)
    say()
    say(f"reclaimed {human(freed)} across {len(plan) - len(failed)} item(s)")
    if failed:
        say(f"⛔ {len(failed)} item(s) could not be removed")
    return 1 if (failed or refusals) else 0


if __name__ == "__main__":
    sys.exit(main())
