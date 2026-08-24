#!/usr/bin/env python3
"""
sync_agents.py — regenerate the platform agent and command wrappers from one
canonical file each.

WHY THIS EXISTS
  `agents/manager.md` and `agents/analyst.md` are the canonical bodies of the
  two-day pipeline's two subagents. Each ships in two discovery paths with
  deliberately different frontmatter:
  - `.claude/agents/<name>.md` (Claude Code: `tools` + `model: sonnet`)
  - `.opencode/agent/<name>.md` (opencode: `mode: subagent` + `permission: { edit: deny }`).

  `agents/orchestrator.md` applies the same idea to the *sequence* rather than a
  role: it is the body of the `/atd-daily` command, which runs the whole pipeline
  from one instruction. It ships to `.claude/commands/atd-daily.md` and
  `.opencode/command/atd-daily.md` — same canonical, same drift check, a different
  frontmatter dialect. That contract previously lived only in the operator's head
  between turns, which is exactly the kind of unwritten sequencing this repo puts
  in a file.

  Before this script (and its predecessor for the reviewer alone,
  `tools/sync_review_manager.py`) there were two hand-maintained copies of each
  checklist, which is invariant 8 of `docs/SYSTEM_MAP.md` in physical form:
  editing a checklist item could leave one platform reviewing last month's format
  with no error appearing anywhere.

  The canonical file under `agents/` is now the single source of truth: its
  frontmatter carries only the shared `description`, its body is the whole
  checklist. This script regenerates both wrappers for *every* canonical, so a
  checklist edit can never silently ship to one platform and not the other.

  The generated wrappers are committed — a fresh clone gets working agents on
  both platforms. The script exists to keep them in sync, and `--check` exists
  so CI or a pre-commit can fail the build if they drift.

WHAT'S COVERED
  Two literal allow-lists (`AGENTS`, `COMMANDS`) prevent accidental enumeration
  into README files or non-agent markdown later added under `agents/`. A new
  agent or command ships by editing its canonical + adding its name here.

USAGE
  python3 tools/sync_agents.py            # write all wrappers
  python3 tools/sync_agents.py --check    # verify wrappers match; exit 1 if drift
"""

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Each entry: name -> wrapper paths + per-platform frontmatter (the `description`
# token is filled at render time from the canonical body's frontmatter).
AGENTS = {
    "manager": {
        "canonical": os.path.join(ROOT, "agents", "manager.md"),
        "claude": {
            "path": os.path.join(ROOT, ".claude", "agents", "manager.md"),
            "frontmatter": [
                "name: manager",
                "description: {description}",
                "tools: Read, Grep, Glob, Bash",
                "model: sonnet",
            ],
        },
        "opencode": {
            "path": os.path.join(ROOT, ".opencode", "agent", "manager.md"),
            "frontmatter": [
                "name: manager",
                "description: {description}",
                "mode: subagent",
                "permission:",
                "  edit: deny",
            ],
        },
    },
    "analyst": {
        "canonical": os.path.join(ROOT, "agents", "analyst.md"),
        "claude": {
            "path": os.path.join(ROOT, ".claude", "agents", "analyst.md"),
            "frontmatter": [
                "name: analyst",
                "description: {description}",
                "tools: Read, Grep, Glob, Bash",
                "model: sonnet",
            ],
        },
        "opencode": {
            "path": os.path.join(ROOT, ".opencode", "agent", "analyst.md"),
            "frontmatter": [
                "name: analyst",
                "description: {description}",
                "mode: subagent",
                "permission:",
                "  edit: deny",
            ],
        },
    },
    "trader": {
        "canonical": os.path.join(ROOT, "agents", "trader.md"),
        "claude": {
            "path": os.path.join(ROOT, ".claude", "agents", "trader.md"),
            "frontmatter": [
                "name: trader",
                "description: {description}",
                "tools: Read, Write, Edit, Grep, Glob, Bash",
                "model: sonnet",
            ],
        },
        "opencode": {
            "path": os.path.join(ROOT, ".opencode", "agent", "trader.md"),
            "frontmatter": [
                "name: trader",
                "description: {description}",
                "mode: subagent",
                "permission:",
                "  edit: allow",  # writes output/evaluation_<date>.md + output/latest.md pointer
            ],
        },
    },
}

# Commands are canonicals too — same render path, same drift check, different
# frontmatter dialect. A command file's *name* comes from its filename on both
# platforms (`atd-daily.md` → `/atd-daily`), so no `name:` key here.
COMMANDS = {
    "atd-daily": {
        "canonical": os.path.join(ROOT, "agents", "orchestrator.md"),
        "claude": {
            "path": os.path.join(ROOT, ".claude", "commands", "atd-daily.md"),
            "frontmatter": [
                "description: {description}",
                # Task = subagent invocation; the orchestrator delegates and
                # shells out, and must never edit the evaluation itself.
                "allowed-tools: Bash, Read, Grep, Glob, Task",
            ],
        },
        "opencode": {
            "path": os.path.join(ROOT, ".opencode", "command", "atd-daily.md"),
            "frontmatter": [
                "description: {description}",
                "agent: build",  # the primary agent; it delegates to the subagents
            ],
        },
    },
    "atd-publish": {
        "canonical": os.path.join(ROOT, "agents", "publisher.md"),
        "claude": {
            "path": os.path.join(ROOT, ".claude", "commands", "atd-publish.md"),
            "frontmatter": [
                "description: {description}",
                # No Task: the publisher shells out and delegates to nobody. No
                # Edit/Write either — it reads the private tree and writes only
                # through publish.py into the destination.
                "allowed-tools: Bash, Read, Grep, Glob",
            ],
        },
        "opencode": {
            "path": os.path.join(ROOT, ".opencode", "command", "atd-publish.md"),
            "frontmatter": [
                "description: {description}",
                "agent: build",
            ],
        },
    },
}


def read_canonical(name, spec):
    """Return (description, body) for one canonical. Raises ValueError on
    malformed files — those are config errors, never silently 'passes'.
    """
    path = spec["canonical"]
    if not os.path.exists(path):
        raise ValueError(f"canonical agent missing: {path}")
    text = open(path).read()
    m = re.fullmatch(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        raise ValueError(f"{name}: no frontmatter — must start with --- … ---")
    fm, body = m.group(1), m.group(2)
    dm = re.search(r"^description:\s*(.*)$", fm, re.M)
    if not dm:
        raise ValueError(f"{name}: no description in frontmatter")
    if not body.strip():
        raise ValueError(f"{name}: empty body")
    return dm.group(1).strip(), body


def render(spec, wrapper_key, description, body):
    """Render one wrapper file text. The frontmatter order matters per platform
    and is not interchangeable. Body is appended verbatim after the closing fence.
    """
    wrapper = spec[wrapper_key]
    lines = ["---"]
    for line in wrapper["frontmatter"]:
        lines.append(line.format(description=description))
    lines.append("---")
    lines.append("")
    lines.append(body.rstrip("\n") + "\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="verify wrappers match; exit 1 if any drift")
    args = ap.parse_args()

    status = 0
    for kind, registry in (("agent", AGENTS), ("command", COMMANDS)):
        for name in sorted(registry):
            spec = registry[name]
            try:
                description, body = read_canonical(name, spec)
            except ValueError as e:
                print(f"ERROR {kind} {name}: {e}", file=sys.stderr)
                return 1

            for key in ("claude", "opencode"):
                path = spec[key]["path"]
                expected = render(spec, key, description, body)
                if os.path.exists(path) and open(path).read() == expected:
                    print(f"OK   {kind} {name}/{key}: "
                          f"{os.path.relpath(path, ROOT)}")
                    continue
                if args.check:
                    print(f"OUT  {kind} {name}/{key}: "
                          f"{os.path.relpath(path, ROOT)} differs from canonical",
                          file=sys.stderr)
                    status = 1
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").write(expected)
                print(f"WROTE {kind} {name}/{key}: {os.path.relpath(path, ROOT)}")

    if status:
        print("run: python3 tools/sync_agents.py", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
