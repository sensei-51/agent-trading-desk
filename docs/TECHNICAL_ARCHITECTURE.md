# Technical Architecture

*How the machine hangs together. **Read this before changing any file it names.***

**Purpose of the setup:** detect sector rotation early and screen every relevant ticker daily, so portfolios are managed from **darkpool and flags** rather than narrative — with human attention spent only where a flag fires.

---

## The picture

![Technical Architecture](Technical_Architecture.png)

*Editable source: `Technical_Architecture.svg` (same folder). Regenerate the PNG at 2× with `sips -s format png -Z 2480 Technical_Architecture.svg --out Technical_Architecture.png` (macOS). The companion `3_agent_pipeline.svg/.png` is the same picture narrowed to the three subagents, and is the README's hero image. Every box and arrow is a file or step named in this document; **if the picture and the text disagree, the picture is stale.** This diagram is the map a future change reads first, and its whole value is that it is true.*

---

## The process in five steps

1. **INTAKE — the weekly sweep fills the funnel.** The weekly fundamentals sweep (score ≥ 60, cap ≥ $2B, sector tabs) pulls *new* names into `input/tracking/universe.md`. Speculative ideas are a parallel intake — they bypass discovery and go straight to the watchlist tagged `SPECULATIVE`.
2. **SCREEN — the radar watches everything.** `engine/heartbeat_radar.py` screens the whole membership (holdings + watchlists + discovery) daily on technicals and produces the rotation read. No opinion, just flags.
3. **PROMOTE — flags earn attention.** A radar flag (`HEARTBEAT` / `AT-BREAKOUT` / `VOL-2X`) promotes a discovery name into the evaluation, via EARLY WATCH triage. Unflagged discovery names cost zero attention. Roster names — held plus watchlisted — are evaluated every run regardless.
4. **DECIDE — gates before money.** The evaluation applies the rulebooks: gate cards, pre-entry validation, rotation call, round-trip reviews → actions with **written levels**.
5. **FEED BACK — decisions re-enter the files.** Promotions add watchlist rows (deleting the universe row); fills land in the holdings CSV. Tomorrow's screen automatically covers today's decisions.

The funnel narrows at each stage: **the sweep finds hundreds → discovery holds ~30 → flags surface a handful → gates pass one or two.**

---

## Three kinds of component, and how to tell which you need

Every piece of this system is one of three things. The distinction is not stylistic — choosing wrong is how a setup like this becomes slow, expensive and quietly unreliable at the same time.

| If the work is… | It is a… | Because |
|---|---|---|
| **Deterministic** — same inputs, same answer, every time | **Python script** in `engine/` or `tools/` | A model asked to do arithmetic will *usually* get it right. "Usually" is not auditable, costs tokens on every run, and fails silently. A script either produces the number or exits non-zero |
| **Judgement that must not be self-assessed** — it needs a different context, or an author who is not the reviewer | **Subagent** in `.claude/agents/` or `.opencode/agent/` — both generated from a canonical `agents/*.md` | Independence is the entire product. The model that just wrote the report is the worst available judge of whether it is complete, because it believes it is. Three subagents occupy this slot: the **Analyst** (data ingestion), the **Trader** (the call), and the **Reviewer** (pre-save check). Each has a different context; each refuses to read another's rulebooks |
| **A criterion** — a bar, a threshold, a definition that a human argues about and an agent applies | **Markdown rulebook** in `rules/`, or a contract in `docs/` | A rule needs exactly one home so it can be changed in one place. Bury a criterion in a script and it stops being arguable; restate it in a subagent's checklist and it drifts silently (invariant 8). Rulebooks are read **on demand**, not on load — that is what keeps a daily run cheap |

Worked examples of the first row, because it is the one that pays:

- **The technical screen.** 150-day line, breakout, 2× volume, consolidation box, RS percentile, and the rotation clustering — all arithmetic over price series. `engine/heartbeat_radar.py`.
- **The lookup legs.** Price, 52-week high, consensus PT, next earnings, YTD, rating changes. Retrieval, not judgement — and the four PRE-ENTRY VALIDATION flags plus two of the PROACTIVE SCREENING tests are pure arithmetic over those numbers, so they are **computed rather than judged**. `tools/facts.py`. *A flag that fires from a formula cannot be forgotten at the end of a long report on a long roster.*
- **P&L and gate scoring.** `tools/pnl.py`.

What that leaves for the agent is exactly what should be left: reading the flags, picking the right gate card, weighing a thesis against the macro backdrop, and writing calls with levels on them.

### The bar for adding another one

**Five scripts run daily (radar · facts · fundamentals · xray · checks, the last wrapping the pipeline as `--pre` and `--post`; pnl scores the ledger separately), and three subagents wrap the run: Analyst owns ingestion, Trader owns the call, Reviewer owns the pre-save check.** The **Analyst** clears the bar on the same independence argument as the Reviewer, applied to ingestion instead of to the report: the agent that decides a data row is good enough should not also be the agent that needs it to be good enough. The **Trader** is a subagent because it must read the rulebooks fresh in a context that holds neither the Analyst's source contract nor the Reviewer's checklist; it used to run as the main session driving `rules/03_DAILY_RUN.md` directly, and that file-driven mode was retired on 2026-08-23 once `agents/trader.md` carried the same recipe. Each of the three reads a **different** rule set and refuses to read the others'.

The bar for *adding more subagents* remains high, because every subagent restating rules is another copy that can drift out of date with no error appearing anywhere (invariant 8). Two open candidates would clear it:

- **The weekly INTAKE sweep** — currently by hand. Bounded contract already written down (rank by score desc → ACCEL/RECORD count desc → alphabetical), different cadence to the daily run, writes exactly one file. This is also what closes known gap 1. *The contract originally carried an 8-per-sector cap and compete-and-displace; both were retired 23 Aug 2026 with the count-based rotation read they served — see the sector-coverage note below.*
- **A periodic ledger post-mortem** — `tools/pnl.py` does the arithmetic, but nothing turns it into the "did the gates filter out winners or save money" verdict the ledger exists to support. It needs independence for the same reason the reviewer does: a system marking its own homework.

Note that the X-ray (`tools/xray.py`, 16 Aug 2026) cleared the deterministic bar *within* the daily run rather than as a new cadence: the "Index is 23% of NAV, Defence 8%" arithmetic the evaluation used to re-derive by hand each run is exactly the row of the three-component table that says "a script either produces the number or exits non-zero". It took over the weight computation and added a running NAV history that the report now charts.

The fundamentals leg joined the family in the same shape (18 Aug 2026): `tools/fundamentals.py` is deterministic — composite /100 + 6 pillars + ACCEL/RECORD, computed for every roster name on every run, source-agnostic via pluggable providers named in `input/config/providers.json`. The `none` default ships publish-safe: every row returns `NONE` and the gate flags become `GATE1-INFERRED` / `GATE2-INFERRED` rather than a fabricated pass. The Analyst owns its handoff and refuses to read the rulebooks — same shape as the Reviewer, opposite end of the pipeline.

Conversely, **do not turn a step into a subagent just because it is long.** Length is not the test; needing a different context, or needing to not be the author, is.

---

## File roles

| File | Role | Maintained by |
|---|---|---|
| `*.csv` in `input/` | Holdings membership — every row auto-screened, every row gets an evaluation call | Broker export |
| `<sleeve>_watchlist.md` | Candidate membership — **stateless** thesis rows (ticker + source + thesis only; no stops, gates or chart state) | By hand, via promotions |
| `input/tracking/sector_map.md` | Classification dictionary (ticker → sector) for **every** screened name, plus the per-sector **bellwether ETF table**. Authoritative over the universe file's Sector column, which is the fallback for a ticker this file has no row for (`hr.load_universe_sectors`, applied by the radar, the x-ray and the checks alike since 2026-09-01) — and which may only reuse a sector named here, never invent one. A superset — inert rows are fine; adds nobody to the screen. **A HELD name missing from it is a defect, not a gap** — the x-ray banners it in the report and `checks --pre` `held classified` warns, naming the ticker and the row to add; it halts the run only when the unplaced value could push a bloc past the 25% ceiling (2026-08-18: eight missing held rows silently misfiled 21.6% of NAV as Unclassified; 2026-09-01: one £3,624 row halted a whole pipeline, backlog #30) | By hand, on any new ticker |
| `engine/heartbeat_radar.py` → `output/radar/Heartbeat_Radar_<date>.md` | Daily screen of the membership union: 150-day exit line, breakout, 2× volume, consolidation box, RS percentile, then the **Rotation read** with per-sector streak/trend persistence and its three states (arriving / **SUSTAINED** = already moving / leaving), and the **Sector pressure** table — the same question asked of the *continuous* measures (median `acc`/`r5`/`r20`/`r60`/`rng_pctl` per sector, percentile-ranked against the universe) because flags are thresholded and thresholding decorrelates a cluster. Fetches each ticker's history **once** into the `output/.state/bars/` OHLCV cache and thereafter asks only for the missing sessions | Scheduled task |
| `tools/facts.py` → `output/data/facts_<date>.md` | Daily **lookup** sheet for the roster: price, 52-week high, median analyst PT, next earnings, YTD, vehicle class, genuine rating changes — plus the flags that are pure arithmetic over them (`BINARY-RISK`, `AT-PEAK`, `CONSENSUS-EXCEEDED`, `EXTENDED-RUN`, `DOWNGRADE-14D`). Removes ~6 search legs per name from the evaluation. Price and 52-week high use the radar's own fetcher and 252-session close convention, so the two files can never quote different numbers | Before each run |
| `tools/xray.py` → `output/data/xray_<date>.md` | Daily **sector X-ray** for the book: NAV total (the broker's own sterling conversion per line), value and % NAV per sector with weight bars, and the running **portfolio-growth chart** from `output/.state/nav_history.json`. Pure arithmetic over the holdings CSVs + `sector_map.md` — takes the "how much of the book is in each sector" step out of the evaluation, which used to recompute it by hand every run. Its **Movers** section is the *held-line* half of delta reporting — value change split from P&L, because a line whose share count moved is marked `TRADE` and shown on price per unit | Before each run |
| `agents/manager.md` → `.claude/agents/` + `.opencode/agent/` via `tools/sync_agents.py` | Adversarial pre-save reviewer. Checks the drafted report against the roster, the facts sheet and the format rules; returns numbered defects, never edits, has no view on any call. **Runs on a self-contained checklist and never loads the rulebooks** — which is what keeps it cheap, and why its checklist must be edited whenever a rule it encodes changes. The canonical checklist is the single source; the two platform wrappers are generated | On process decisions |
| `agents/analyst.md` → `.claude/agents/` + `.opencode/agent/` via `tools/sync_agents.py` + `tools/fundamentals.py` + `providers/` + `input/config/providers.json` | Per-run **data ingestion**. Reads source config; runs `facts.py` and `fundamentals.py`; resolves FAIL/PARTIAL/NONE rows live; sources theme news; publishes dated `output/data/analyst_<date>.md`. Operates only on the source contract (`docs/DATA_SOURCES.md`) — never on the rulebooks, not on the gate cards | Scheduled per Analyst invocation |
| `agents/trader.md` → `.claude/agents/` + `.opencode/agent/` via `tools/sync_agents.py` | Per-run **the call**. Reads the Analyst handoff, the rotation read, the rulebooks fresh, applies the gate cards, writes `output/evaluation_<date>.md` with one explicit signal per roster name. Operates on the rulebooks; refuses to re-fetch the Analyst's data, refuses to self-audit (the Reviewer does that). The only execution mode — the file-driven fallback was retired 2026-08-23 | Scheduled per Trader invocation |
| `tools/fundamentals.py` → `output/data/fundamentals_<date>.md` | Daily **fundamentals lookup** sheet: composite /100 + grade + six pillars (Quality, Growth, Cash Flow, Stability, Valuation, Ownership) plus ACCEL/RECORD, computed for every roster name from whichever provider `input/config/providers.json` names. Stock-card gates 1 and 2 (composite ≥ 60 + ACCEL/RECORD; CF ≥ 7, Stability ≥ 5, Quality ≥ 13) are arithmetic over these figures and are stamped on each row with `S` prefix. Provider selection defaults to `none` (publish-safe: every row returns `GATE*-INFERRED`, not a fabricated pass). Each row carries the `provider` that answered it and an `approx` flag | Before each run |
| `tools/sync_agents.py` | Generates `.claude/agents/<name>.md` + `.opencode/agent/<name>.md` from every canonical under `agents/` by name; `--check` is the CI mode (drift = exit 1). Iterates over the allow-list `[manager, analyst, trader]`; add new subagents by adding one canonical body **and** one entry here | On any canonical edit |
| `tools/run_daily.py` → `output/.state/run_manifest.json` | **The one command that produces a coherent run.** Executes checks-pre → radar → facts → fundamentals → darkpool → xray → checks-post in order, halts on the first non-zero exit, stamps a manifest (step exits, artefact sha1s, and the **radar verdict the Trader must quote verbatim** — never re-derive the radar's age). Exists because 2026-08-18's hand-run pipeline let the evaluation consume pre-fix data and assert a false staleness claim. **Running it twice in one day is supported** — it stamps `"run": N`, archives the prior evaluation to `.state/evaluation_<date>.run<N-1>.md`, and `checks --pre` reports the re-run as a WARN, never a FAIL (`docs/BACKLOG.md` item 22) | Daily, before any agent |
| `tools/checks.py` | **The consolidated assertion pass** — one file of named checks instead of ten single-check scripts. `--pre`: sector-map hygiene, config sanity. `--post`: bloc ceiling ≤ 25% NAV per sector (basis: **market value £**, CONFIG §3), line-cap warnings, NAV cross-check, radar-age verdict, status-table honesty (⚫ ABSENT never ✅), ledger-touched. `--publish`: real-NAV leak sweep + gitignore sanity before any public push. Add a check here, not a new file | On process decisions |
| `tools/eval_reviewer.py` | The **mechanical 10-of-18** of the Reviewer checklist (roster reconciliation, gate prefixes, card-vs-vehicle, round-trip reviews, CHASING qualifier, x-ray verbatim, sector headings, radar-age claim …) in seconds, emitting numbered defects in `agents/manager.md`'s numbering. The Reviewer agent runs after it and starts from its output — it verifies instead of transcribing | On checklist changes (invariant 8) |
| `tools/append_gate_ledger.py` → `output/ledger/Gate_Ledger.csv` | Records today's non-trivial decisions (BUY/SELL/EXIT/TRIM/BLOCKED/STARTER/WAIT rows, from the Trader's manifest or parsed from the evaluation) in the ledger. Runs only after the evaluation passes review, so it records approved output rather than reviewing it again. Replaces today's own `daily-eval` rows on a re-run; refuses the batch on a malformed row. `checks.py --post` fails a run where today's evaluation exists but the ledger was not touched | Each run, after the review passes |
| `tools/calibrate_derived.py` → `docs/DERIVED_CALIBRATION_<date>.md` | Scores the `derived` (Yahoo-proxy) fundamentals provider against a curated run on the actual roster — per-name composite deltas and gate-1/2 confusion counts. The number to drive to zero is FALSE PASSES (curated FAIL → derived PASS); tighten band edges in `providers/fundamentals/derived.py` until it is | After any band-edge change |
| `rules/01_METHOD.md` | Method: the three signals, entry filter stack, 150-day rule, rotation rules, dip-or-trap, crisis overlay | On new material |
| `rules/02_SLEEVE_RULES.md` | Gates and sizing: **7-gate stock card + 8-gate ETF card**, two-tier structure, trailing ratchet, signal-ruled exits, sleeve caps | On process decisions |
| `rules/03_DAILY_RUN.md` | The Trader's **execution context**: input order, the `/atd-daily` invocation pointer, and the report's **bindings** — which headings a script matches by regex, which strings reach the ledger verbatim, which blocks are quoted from a generated file. **The Trader canonical (`agents/trader.md`) holds the recipe; `templates/evaluation.template.md` holds the report's shape; this file holds neither.** Changes to the recipe go to the canonical, changes to what the report *looks like* go to the template, changes to what it *binds to* go here. The three are disjoint on purpose — a fourth description of the report format is how 21 Aug 2026 happened (`docs/BACKLOG.md` item 25) | On process decisions |
| `output/evaluation_<date>.md` | Daily output — dated, accumulates each run. All evaluation state lives here, never in the watchlists | Each scheduled run |
| `output/ledger/Gate_Ledger.csv` | Append-only audit trail of every gate decision, across all sleeves | Every decision |

---

## Ticker lifecycle

```
idea (sweep / research / early watch / external source)
  → row in input/tracking/universe.md  +  label in sector_map.md
  → radar screens it daily (Tier 0)
  → FLAG FIRES (HEARTBEAT / AT-BREAKOUT / VOL-2X)
    → PROMOTION: thesis row added to watchlist, tracking row DELETED
    → auto-screened as a watchlist name (Tier 1)
    → gate card runs every day
    → bought → appears in holdings CSV (Tier 2)
```

The `sector_map.md` row never moves through any of this — it is a permanent label.

### Three-tier member model (17 Aug 2026)

| Tier | File(s) | Radar | Eval |
|---|---|---|---|
| Hold | broker CSVs in `input/*.csv` | yes | yes — full gate card |
| Watchlist | `input/watchlist.md` (or `watchlist_*.md` for splits) | yes | yes — full gate card |
| **Tracking** | `input/tracking/*.md` | yes | **no** |

A tracking name darkpools into the rotation read, picks up RS percentile, and is
flagged for HEARTBEAT / AT-BREAKOUT / VOL-2X — but **the daily evaluation does
not run a gate card on it.** That's the budget split: the radar filters for
signals; the evaluation commits to the work of running a full card on the
pre-qualified names. Tracking reduces the latter's labour to the names the
sleeve has decided to think about.

**Tickers that have nowhere else to go** (no breakeven fundamentals data,
no agent run, just an external reference point) belong here. Promote to a
watchlist when the radar flag matches a thesis you actually support; drop
the row on the next sweep if the flag is unfollow-through. The full workflow
notes are in `input/tracking/README.md`.

### Two tracking swimlanes

`input/tracking/` reads as a directory of `*.md`, not a single file. As of
17 Aug 2026:

| File | Role |
|---|---|
| `universe.md` | User-facing channel for discovery names — sweep output, YouTube / screeners / news / podcasts / manual research. **Promote on improvement.** |
| `sector-coverage.md` | Sector-rotation quorum backing. Intent-stated names kept deliberately. **Not** an ideas pool. |

A tracking ticker that appears in both files double-counts — same constraint
as the old universe.md rule for holdings/watchlists. The Sector column in
either file is a fallback; `sector_map.md` wins on the ticker→sector mapping.

**Speculative bypass** (unchanged from prior versions): speculative names
skip tracking entirely and go straight into the watchlist tagged
`SPECULATIVE`, regardless of score. The radar screens them but assigns **no
RS percentile and never tags them RS-LEADER**.

---

## Two sleeves, opposite philosophies, one spine

If you run more than one account, they may deserve genuinely different rulebooks. A worked contrast — a momentum trading sleeve versus a core DCA sleeve:

| | **Trading sleeve** (buys strength) | **Core sleeve** (buys weakness) |
|---|---|---|
| Method | Full momentum stack — breakout entries confirmed by volume, earnings acceleration | Method applies only to individual stocks; ETFs run mechanical 200DMA rules |
| Gate card | **Stock card** for single names, **ETF card** for baskets — see `02_SLEEVE_RULES.md`. Never mix the two | Size gate only; no fundamentals card either way |
| Entry style | Momentum: buy the breakout above the prior high, act only on alert fire | Anti-chase DCA: buy on the calendar, 1.5× bigger below the 200DMA |
| Gates | 7-gate stock card; 8-gate ETF card | Size gate for core; 4 mechanical gates for thematic |
| Sizing | Risk-first: risk ÷ stop distance | Loss-budget: budget ÷ normal drawdown, tranched over months |
| Selling | Two-stop system + trailing ratchet; winners run uncapped | Scale out at +25% / +50%, trail 20% from high, quarterly harvest, rebalancing bands |
| Risk flag | 🟡/🔴 gates new entries | Never vetoes — only scales tranche size |
| Rotation use | **Fast lane (weeks):** ROTATION-IN steers new risk money; OUT feeds 150-day sell-reviews | **Slow lane (months), thematic only:** OUT pauses tranches; IN prioritises the build queue. Core is exempt by design |
| Frequency | Event-driven | 1 buy/week, 4-week tranche gaps, volatility brake |

⚠️ **Read this table by column.** The right-hand column describes the **core sleeve**, and nothing in it is a rule for the trading sleeve. The `200DMA` entries in particular are core-sleeve mechanics.

This warning is here because the misreading already happened: *"ETFs run mechanical 200DMA rules"* — a core-sleeve statement — was for a long time the only sentence in the repo that looked like it addressed how a fund clears the gate card. It reads as a general exemption, so the trading sleeve's actual ETF gap went unnoticed until it was looked for directly. **The trading sleeve's ETF rules are the ETF gate card and signal-ruled exits in `02_SLEEVE_RULES.md`, and nowhere else.**

**Do not "unify" sleeves under one method.** The genuinely shared layer is: the radar + sector map + rotation read, the trend-line principle (150-day fast, 200DMA slow — same idea, different tempo), the anti-chase gate, sizing from risk not conviction, strategic-conviction weights, event windows, and stricter-rule-wins. **The architecture layer is the spine; sleeve rulebooks sit on top.**

---

## Sector rotation — detection and consumption (v2, 16 Aug 2026)

*Twelve changes shipped together with the v2 rotation read. Each closes a
specific failure mode the v1 read was producing on this sleeve's actual
flag-history. Listed in priority order in `engine/heartbeat_radar.py:86` (CHANGES
17) and again in the priority classification at the foot of the file.*

### Tag vocabulary

Every sector reads as one of these tags each run. Phases ride on a base tag; the
streak is counted at the base, not the phase.

| Tag | What it means | Carries over to |
|---|---|---|
| **ROTATION-IN** | Cluster pulse decisively upward; phase is balanced | Stops being "IN" the moment LATE > EARLY |
| **STRONG-IN** | IN + EARLY > LATE — rotation has further to run | Treated as a generous **IN** for the gate card |
| **CHASING** | IN + LATE > EARLY — most participants already own | Gate 1 carries, but the action line says "wait for a pullback" |
| **MIXED** | Both ≥ 2 arriving AND ≥ 2 leaving, OR > 30% round-trips, AND score can't pick a clean side | **Not actionable.** Two-way motion is signal but not signal-mapped-to-buy/sell. |
| **ROTATION-OUT** | Cluster pulse decisively downward | Reverts to HOLD on the held names, kept on watchlist |
| **FADING-OUT** | OUT + leaving magnitude shrinking — rotation winding down | Watch for an early-IN candidate 1-3 runs out |
| **EXHAUSTED** | OUT + leaving magnitude has shrunk past the re-IN threshold | Sector reading is "rotation already absorbed"; the held names are candidates for re-evaluation but no new selling |
| **—** | Cluster is small or balanced below both floors | Read the sector gauges and the single-name flags directly |

**Important:** the tag is a cluster signal, not a buy/sell signal. Every
candidate that flags still needs the full stack (gates 1-7 stock card, gates
1-8 ETF card) before any money moves. The rotation tag is the **direction of
bias**, not an action.

### Detection (in `engine/heartbeat_radar.py`)

- **Arriving / leaving.** A member counts as *arriving* on `HEARTBEAT` or
  `AT-BREAKOUT` without `ROUND-TRIP-RISK`, and as *leaving* on
  `ROUND-TRIP-RISK` or `BELOW-RISING-LINE`. **Clusters are read before any
  individual name is judged.**
- **Cluster build.** Every screenable member's flags are aggregated by sector
  into `in`, `out`, `early` (HEARTBEAT), `late` (AT-BREAKOUT),
  `round_trip`, `conflict`. A name in both `in` and `out` counts twice
  (once each) and is recorded in `conflict`.
- **Tag scoring rubric** (replaces v1's strict "> 2×" ratio rule):

  `score_in  = arrivals − 2×leavings + 0.5×(EARLY−LATE) + 0.3×gauge_20d_momentum`
  `score_out = leavings − 2×arrivals + 0.5×(LATE−EARLY) − 0.3×gauge_20d_momentum`

  Where the gauge_20d is positive, score_in rises and score_out falls —
  the bellwether's 20-day change enters the cluster's read in the direction
  of its own vote. A 6-leaving/2-arriving cluster with a rising bellwether
  reads score_out = −0.4; **this is a FADING-OUT or MIXED signal, not a
  silent "—"** — the divergence between cluster and bellwether is itself a
  signal.
- **Hard gates:** ratio (`arrivals > 2×leavings` for IN; `leavings > 2×arrivals`
  for OUT) AND size-normalised floor (`arrivals ≥ max(2, 20%-of-roster)` for
  IN, `leavings ≥ max(3, 20%-of-roster)` for OUT). Score > 0 of the *winning*
  side. **Score is a tiebreaker, not a gate.**
- **Single-stock sectors** (≤ 2 named members) get a `in_min` floor of 1 and
  require the bellwether to be CONFIRMED. The "no UCITS healthcare/rail ETF
  exists" case is no longer structurally unreachable — see `input/tracking/sector_map.md`
  for the gauge requirement.
- **Bellwether flag rendering (Change A, 16 Aug 2026).** The same flag
  vocabulary that runs on member names also runs on the bellwether itself
  (`gauge_analyse()` in `engine/heartbeat_radar.py`). The `Flags` column
  in the sector gauges subtable shows HEARTBEAT / AT-BREAKOUT /
  VOL-2X-{UP,DOWN} / ROUND-TRIP-RISK / BELOW-RISING-LINE / NEAR-52W-HIGH
  on the gauge ETF directly. This is the cluster's chief quorum signal on
  days where member flags are sparse.
- **Sparse-cluster gauge fallback (Change B, 16 Aug 2026).** When the cluster
  has dropped to a `-` tag AND its flag density is below 30% of the sector
  roster (`arrivals + leavings ≤ max(2, ceil(n/10))`), the bellwether can
  speak. Two cases:
  - gauge verdict CONFIRMED in the IN direction AND gauge flags include
    HEARTBEAT (early shape) → `STRONG-IN`; AT-BREAKOUT (already past the box)
    → `CHASING`.
  - gauge verdict CONFIRMED in the OUT direction AND gauge flags include
    ROUND-TRIP-RISK or BELOW-RISING-LINE → `FADING-OUT`.
  This *does not* override a cluster producing real activity: a 4-arrival,
  6-leaving Defence cluster stays `-` because density is 100% of the
  roster — the cluster's disagreement is the read. The rescue is exactly
  for the case where the cluster has nothing to say.
- **Gauge verdict (CONFIRMED / CONFLICT / ERROR)** — bellwether ETF vs its
  150-day, tagged with the cluster's proposed direction. A flags-only
  ROTATION-IN against a failing gauge reads CONFLICT. **Three consecutive
  CONFLICT/ERROR runs auto-demote the IN/OUT-and-its-phases tag to MIXED.**
  The conflict streak is persisted in `rotation_history.json` so re-runs do
  not reset it.
- **Persistence** — `rotation_persistence()` walks the last 30 valid runs.
  *Note (18 Aug 2026): `rotation_history.json` was reset on 2026-08-18 — the
  prior 30-run history lives only in `rotation_history.backup-2026-08-16.json`
  (pre-v2 schema). Until ~10 runs re-accumulate, every streak reads "1, NEW"
  and the Streak / Trend / Speed columns are noise; the Trader should weight
  the tag and the gauges, not the persistence columns, during the rebuild.*
  Streak counts runs of the same *base* tag (phase suffixes ride on it;
  STRONG-IN→CHASING is still streak 2 IN). Trend is signed-intensity vs 5-run
  mean (and reads opposite-way for OUT — leaving-falling = EXHAUSTED,
  leaving-growing = STRENGTHENING). Speed is ACCELERATING /
  DECELERATING / STABLE / NEW based on score vs 3-run mean; a sector turning
  over without changing tag will still surface here.

### Reading the new columns

| Column | What it tells you |
|---|---|
| **EARLY** | count of HEARTBEAT (pre-breakout coiling). > LATE → STRONG-IN; < LATE → CHASING |
| **LATE** | count of AT-BREAKOUT (already past the box). Tag suffix reads from this |
| **!** | conflicted name count (arriving AND leaving). > 0 = cluster has contradictory signals — usually MIXED |
| **Gap-IN** | names needed to satisfy the size floor. 0 = at threshold; 1+ = one flag away |
| **Gap-OUT** | same, leaving-side |
| **Gauge / G-streak** | bellwether vote *relative to the tag* + the count of consecutive contradicting runs **ending today**. `CONFLICT(3)` demotes the tag to MIXED in that same run; a gauge that agrees today resets the count to 0 |
| **Speed** | ACCEL/DECEL on score, 3-run mean. The "rotation just started" signal before the tag flips |

### Consumption (in `agents/trader.md` and the gate card)

1. **The report must carry an explicit rotation call** — which sectors are
   IN/OUT/MIXED, *and* the phases where relevant. STRONG-IN means the
   ETF card gate 1 passes with a clean mover; CHASING means it passes only
   after a pullback — the action line is automatic.
2. **MIXED is not actionable.** A MIXED sector's investable line stays on
   the table; gate 1 fails by definition. **EXPANSION** for a MIXED
   sector is to find the side the cluster is actually resolving to
   (one name decoupling from the rest), not to push money in on the
   sector average.
3. **Live cross-check the destination when a held leader stalls.** Same
   as v1 — but with the Gap-IN/Gap-OUT columns, you can see how close a
   stalled sector is to a tag flip and time the cross-check.
4. **Every ROTATION-IN / STRONG-IN sector must land on a buyable ticker.**
   Look up the bellwether table's Investable line and run it through the
   appropriate gate card. CHASING adds the qualifier "wait for a
   pullback" to the recommendation line. If the table shows `none`,
   finding a vehicle becomes that run's EXPANSION task.

> **bellwether → investable line → gate card → report** is the full path
> from "sector improving" to "buy recommendation". The gate card reads
> STRONG-IN as a clean pass, CHASING as a pass with a pullback qualifier, and
> MIXED / FADING-OUT / EXHAUSTED as outright rejections of gate 1.

Gate 1 of the ETF card *is* the rotation read, so this path is not circular by accident — it is circular by design. **This is also why the rotation read's blind spots are trading defects, not reporting defects**: for eighteen runs it had no vocabulary for a sector that was already moving, so such a sector rendered no row, so gate 1 had nothing to pass, so a 7/7 gate card was held at WAIT. The `SUSTAINED` state (22 Aug 2026) exists to close that path end to end — it passes gate 1 and it explicitly does **not** lift the doubled ETF cap. A sector ETF's thesis **is** the sector call; there is no separate company story to verify. What stops it being a rubber stamp is that gates 2–8 are all independent of the rotation read, and gate 8 in particular is the one that fires when four ROTATION-IN lines turn out to be the same bet.

### Why these specific changes and not others

- **The size-normalised threshold floor of 20%-of-roster is unchanged.** It
  correctly prevents 34-name Gold and 1-name Healthcare from being
  compared to each other on count alone. The single-stock exception is
  *separate*, not a relaxation.
- **The 2× ratio is preserved as a HARD gate.** It is the floor below the
  score, not a guideline. It still catches sectors in genuine
  two-way motion (3 in / 2 out → ratio 1.5, fails).
- **Round-trip still overrides the arrive side.** A name at a 52-week
  high with both flags is a trap, not an arrival.
- **Bellwethers are still measurement-only.** Gauges never enter the
  In/Out counts. A bellwether breaking out is *gauge* evidence for the
  sector, never a sector member that registered a flag.
- **Gauge conflict is now load-bearing at 3 runs.** It was decorative in
  v1 (the verdict appeared in the table, the tag ignored it). MegaTech's
  17 consecutive OUT runs with a CONFIRMING gauge are an existence-proof
  of why this had to change.

### A caution on measurement

> Sector readings averaged over "whichever members a sector happens to have"
> are not comparable — 34 miners and 1 healthcare stock are not the same
> measurement. The fix is still the **bellwether ETF table** in
> `input/tracking/sector_map.md` — one gauge ETF per sector, **measurement-only**.
> Member counts remain a *breadth* measure only. **Treat thin sectors' In/Out
> counts as anecdotes and lean on the gauge for direction.**

### Expansion: thin sectors

Sectors with very few members (1-2 names) cannot satisfy the 20% floor
without an explicit expansion. The radar surfaces this via the Gap-IN /
Gap-OUT columns but the underlying fix is in the **sector_map.md**:

- **Healthcare** (1 → 5 names) — added UNH, JNJ, PFE, MRK as
  sector-rotation-read backing. XLV (gauge) is sufficient as a sector
  ETF measurement; no `Investable line` change required at the table.
- **Rail** (1 → 4 names) — added UNP, CSX, CP. Same — IYT (gauge) is
  sufficient, Sector is structurally stock-only (no pure-rail ETF).

These tickers are entered in `input/tracking/sector_map.md` AND in
`input/tracking/universe.md` so they are screened by the radar as discovery
backing but never auto-promoted to a buy. **Nothing bounds further additions** —
the discovery cap of 8-per-sector was scaffolding for the count-based rotation
read and retired with it on 26 Jul 2026, when bellwether ETFs took over sector
direction. What remains is a *floor*: `heartbeat_radar.classify()` needs three leaving
members for an OUT read, relaxed to one for a thin sector (`n <= 2`) provided
the bellwether gauge reads CONFIRMED. That relief existed only on the IN side
until 2026-08-23, when the OUT side was mirrored onto it (`docs/BACKLOG.md`
item 23.1) — before then a one- or two-member sector could signal arrival from
its own members and never departure.


---

## Screening & evaluation contract

- **Roster coverage is total.** Every watchlist row and every holding gets an explicit signal in the evaluation, coverage-counted at the top of the report. **A roster name missing from the radar is a bug to flag, not a name to skip.**
- **Discovery names are triaged, not evaluated.** Most screen themselves out silently; any that flag go through EARLY WATCH — regardless of currency. Currency decides only which sleeve's watchlist an adopted name lands in.
- **`ROUND-TRIP-RISK` on a held position = mandatory sell-review** under the 150-day rule. The report must state keep/exit with a written trigger level. The distinction that matters: a round-tripped *winner* (the rule's target) exits; a position near cost in tactical drawdown holds with a level. On watchlist names, the flag is just an AVOID reason.
- **Every candidate that flags still needs the full stack** before money moves. **The radar is a screen, never a buy signal.**

---

## Invariants — do not break these

1. Watchlists are **stateless** registries; all evaluation state is produced fresh each run in the evaluation file.
2. `input/tracking/universe.md` is **discovery-only**. Holdings and watchlist names are auto-derived. *Hand-listing them there is the failure mode that once dropped two live holdings off the screen entirely — no exit line, no round-trip coverage, for weeks.*
3. **Promotion deletes the universe row.** A name may exist in only one membership source; leaving it in two double-counts it in the rotation read and corrupts the momentum calculation.
4. `sector_map.md` wins over the universe file's Sector column, and must stay a **superset** of everything screenable.
5. Bellwethers and speculative names take **no RS percentile** and can never be RS-LEADER.
6. Theme membership is **a lens for interpreting a flag, never a gate for suppressing one.**
7. **Stricter rule wins** across method → sleeve rules → watchlist — except the Speculative Tier, a deliberate size-limited exception.
8. **Every subagent's checklist has to be maintained as one.** `.claude/agents/manager.md`, `.claude/agents/analyst.md`, and `.claude/agents/trader.md` each restate their own contract rather than reading the rulebooks, deliberately — that is what makes them cheap enough to run daily. The cost: each can drift out of date without any error appearing anywhere. **Change a rule a checklist encodes, change the checklist in the same edit.** Each canonical lives at `agents/<name>.md`; both platform wrappers are generated from it by `tools/sync_agents.py`, so an edit ships to every platform or none. A reviewer quietly checking last month's format is worse than no reviewer at all, because its PASS still reads as assurance. **Edit a wrapper directly and drift is silently re-introduced; the next `python3 tools/sync_agents.py --check` (or the next run) will catch it.**
9. **A generated file is an input, never a source of truth.** `output/data/facts_<date>.md`, `output/data/xray_<date>.md`, and `output/radar/Heartbeat_Radar_<date>.md` are today's lookups, regenerated each run and safe to delete. Nothing may be recorded only there — decisions go to the ledger, positions to the broker CSV, theses to the watchlist. `output/.state/nav_history.json` is the same rule in persisted form: a charting cache of NAV points, rebuilt from the broker CSV each run — it is never the record of a decision, and a lost file only loses history, not the audit trail. `output/.state/bars/` is the same again — a raw-OHLCV cache that re-verifies itself against the feed every run and rebuilds from scratch on any disagreement, so deleting it costs one full refetch and nothing else. *This is the same rule as "retire stale local caches", applied to the caches this repo writes itself. The dated `evaluation_<date>.md` files are an archive, not the record — the ledger stays the durable artefact.*

---

## Known gaps worth carrying into your own copy

**The open list lives in `docs/BACKLOG.md`, not here** — one register, so a gap cannot be
half-tracked in two places. The five that used to be listed in this section are **item 18**
there, with their original wording:

| | Gap |
|---|---|
| 18.1 | **Speculative-tier screen** — no inverted weekly sweep, so that tier's funnel is whatever you happened to read this week |
| 18.2 | **Rotation step on the slow sleeve** — a core sleeve heavy in the biggest ROTATION-OUT sector, with no rotation step in its own rules |
| 18.3 | **Round-trip review table** — without a fixed subsection, a skipped mandatory review is invisible |
| 18.4 | **Sector measurement by breadth** — see *"A caution on measurement"* above; mitigated by bellwethers, not solved |
| 18.5 | **The publish decision** — real ledger + anonymised holdings, to be executed before the first public commit. The one that moves real data |

**Cross-platform subagents** (the sixth entry, done 15–18 Aug 2026) is no longer a gap: each
subagent has one canonical body under `agents/`, and `tools/sync_agents.py` regenerates both
platform wrappers with `--check` for CI. That is **invariant 8** below. Edit the canonical in
`agents/<name>.md` only — a wrapper edited directly is drift that `--check` will catch, and a
new subagent ships by adding one canonical *and* one entry to the script's allow-list.

---

*Not financial advice. See `DISCLAIMER.md`.*
