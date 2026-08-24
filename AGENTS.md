# AGENTS.md — instructions for AI agents working in this repo

You are in a daily trading evaluation pipeline. The job is to take today's data,
apply the rules, and write `output/evaluation_<date>.md` with explicit signals.

## Start here (read these three files on first load)

1. **`docs/TECHNICAL_ARCHITECTURE.md`** — what this system is: the pipeline diagram, file
   roles, ticker lifecycle, two-sleeve model, rotation v2 design, **invariants**
   (the rules that must not break). This is the entry point. ~400 lines.
2. **`docs/DATA_SOURCES.md`** — the source/provider contract. What the
   fundamentals / chart / conviction legs must supply, what substitutes work, why
   `INFERRED` is not a fabricated pass. ~230 lines.
3. **`docs/RADAR.md`** — the engine's user-guide. Flags, design decisions, inputs
   and outputs. ~120 lines.

That set is enough to act. Go to `rules/*.md` (governance, method, gates) only
when a call needs a judgement you can't make from the docs.

**Before changing anything in the rotation path**, read
`docs/FLOW_FIRST_PROPOSAL.md` — but read its banner first. **Its core change was
declined on 22 Aug (D5):** the radar keeps the rotation read and the flow leg is a
**permanent optional overlay** — never a gate, never a required input. Phases 3, 4
and 5 are retired, so the "Phase 3 evidence gate" no longer exists as a condition
for anything. Rotation v2 plus `SUSTAINED` governs today's runs. The decision and
its reasoning are in `docs/BACKLOG.md` § D5; the policy decisions D1–D4 in §2 of the
proposal still stand, and **D1 is still unshipped** (`docs/BACKLOG.md` item 11).

The Trader subagent owns the daily evaluation; the Analyst owns data ingestion;
the Reviewer audits. See `docs/TECHNICAL_ARCHITECTURE.md` for the three-subagent contract.

**`docs/BACKLOG.md` is the single register of open work.** Every gap, open question
and deferred decision lives there with a status symbol; other documents carry a
pointer, never their own list. If you find outstanding work recorded anywhere else,
move it there rather than tracking it in place.

## Run the daily pipeline

**One instruction runs the whole thing, on both platforms:**

```
/atd-daily
```

Phase A, then Analyst → Trader → Reviewer, the defect loop, and the ledger
draft — no human sequencing between steps. The contract is
`agents/orchestrator.md`; `/atd-daily` is its generated wrapper
(`.claude/commands/atd-daily.md`, `.opencode/command/atd-daily.md`). It **halts** rather
than working around a failure, and it records the day's
decisions in `output/ledger/Gate_Ledger.csv` automatically, once the evaluation
has passed review — the ledger listens to approved output, it does not review it
a second time.

The individual steps, for a partial or manual run:

```bash
python3 tools/run_daily.py          # Phase A: radar · facts · fundamentals · flow · xray · checks
python3 tools/eval_reviewer.py      # mechanical pre-save review (0 defects is the gate)
python3 tools/rerun.py             # re-run today in an isolated sandbox (default); --list · --in-place
python3 tools/append_gate_ledger.py # record today's non-trivial decisions in the ledger
python3 tools/sync_agents.py --check  # CI check on canonical drift, agents + commands (invariant 8)
```

Phase B (the Trader's call) is owned by the `trader` subagent in
`.claude/agents/trader.md` and `.opencode/agent/trader.md` (both generated from
`agents/trader.md`). For file-mode runs, see Timer usage below.

## Timer usage (file-mode Phase B)

The canonical Trader phase names (mirror `agents/trader.md` Steps 2-10):
`start → read → macro → signals → sizing → write → validate → review → save → end`.

In-process:
```python
from tools.time_run import TradeTimer
t = TradeTimer(date="2026-08-20")
t.mark("start"); ...; t.mark("read"); ...; t.mark("macro")
...; t.mark("signals"); ...; t.mark("sizing"); ...; t.mark("write")
...; t.mark("validate"); ...; t.mark("review"); ...; t.mark("save")
t.finish()       # closes `end`, fingerprints artefacts, writes JSON
```

From the shell (one invocation per phase; each loads, updates, saves):
```bash
python3 tools/time_run.py mark start
python3 tools/time_run.py mark read
python3 tools/time_run.py mark macro
python3 tools/time_run.py mark signals
python3 tools/time_run.py mark sizing
python3 tools/time_run.py mark write
python3 tools/time_run.py mark validate
python3 tools/time_run.py mark review
python3 tools/time_run.py mark save
python3 tools/time_run.py mark end
python3 tools/time_run.py summary            # both phases side by side
python3 tools/time_run.py summary --phase trader
python3 tools/time_run.py summary --phase data
```

## State files

| Path | Purpose |
|---|---|
| `output/.state/run_manifest.json` | Phase A timings + artefact sha1s |
| `output/.state/trader_timings_<date>.json` | Phase B phase durations + artefact sha1s |
| `output/.state/radar_state.json` | radar's intermediate state (gauge streaks etc.) |
| `output/.state/rotation_history.json` | sector rotation tag history per run — atomic write with backup fallback |
| `output/.state/nav_history.json` | NAV over time (broker-CSV-mtime-keyed) |

State files are **caches**, not records. Decisions go to `output/ledger/Gate_Ledger.csv`;
positions go to the broker CSV in `input/`; theses go to `input/watchlist*.md` /
`input/tracking/*.md`. Lost state files mean lost chart history only — not lost audit trail.

## Governance

- **The ledger**: `output/ledger/Gate_Ledger.csv` is the permanent audit trail and
  the system's only durable memory — every other file under `output/` is rebuilt
  by the next run. `tools/append_gate_ledger.py` writes to it automatically, but
  only after the evaluation has passed review, so it records approved output
  rather than reviewing it a second time. Rows dated today from `daily-eval` are
  replaced on a re-run; every other row is immutable.
- **Manager review**: `agents/manager.md` performs the adversarial pre-save check.
  Even in file-mode, do not skip it. The mechanical 19-of-19 lives in
  `tools/eval_reviewer.py`; the agent runs after it.
- **Rule files**: `rules/01_METHOD.md` (method), `rules/02_SLEEVE_RULES.md`
  (gates, sizing, stops, risk), `rules/03_DAILY_RUN.md` (execution shape).
- **Subagent + command sync**: `python3 tools/sync_agents.py` regenerates
  `.claude/agents/*.md` and `.opencode/agent/*.md` from canonicals in `agents/`,
  and the command wrappers from their canonicals: `/atd-daily` from
  `agents/orchestrator.md`, `/atd-publish` from `agents/publisher.md` (each to
  `.claude/commands/<name>.md` and `.opencode/command/<name>.md`).
  `python3 tools/sync_agents.py --check` is **invariant 8** of `docs/TECHNICAL_ARCHITECTURE.md`:
  drift must be caught by CI. **Edit a canonical, never a wrapper** — that's how
  silent drift sneaks in.

## Don'ts

- **Do not invent scores or carry yesterday's forward** — every gate card reads
  the same fields from `output/data/fundamentals_latest.md`. A gate applied to
  a name without a fresh score is a defect.
- **Do not run a fund/ETF vehicle through the stock card** (gates 1-2 demand
  company fundamentals; failure mode is fake-pass or auto-fail). Use the `E`
  prefix on the gate result for funds, `S` for stocks — `tools/pnl.py` groups
  blocked decisions by that exact string.
- **Do not write evaluation state back into the watchlist** — it stays a
  stateless registry.
- **Do not skip names.** A run that skips names is a failed run (the 18-name
  gap on 2026-08-12 shipped unnoticed).
- **Do not commit secrets** to the repo. `input/config/providers.json` keys are
  publish-safe defaults; rotate before pushing.

---

*This file is the operational index. The "what" and "why" live in `docs/TECHNICAL_ARCHITECTURE.md`.*
