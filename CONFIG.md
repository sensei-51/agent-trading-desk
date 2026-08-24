# Configuration

Every number the ruleset depends on. Set these once, then the rest of the repo scales to your sleeve.

> **You do not need this file to run the radar.** `python3 engine/heartbeat_radar.py`
> works on an unedited clone — the screen is technical and knows nothing about your
> position sizes. Come here when you start acting on it.
>
> **Only §1, `SLEEVE_NAV`, is genuinely required.** Everything else below has a working
> default, and the defaults are the rules as written. Change one only when you have a
> reason to, and read the note attached to it first — several of the numbers are safety
> rails with a specific failure behind them.

---

## 1. Sleeve NAV

```
SLEEVE_NAV = £__________
```

The market value of **the trading sleeve this rulebook governs** — not your total net worth, not your whole pension. Every size below is a percentage of this.

The rules files use a **nominal £100,000 sleeve** in worked examples purely for readability.

## 2. Sizing parameters

| Parameter | Default | Yours | At £100K |
|---|---|---|---|
| Max risk per trade | 0.8–1.0% of NAV | | £800–1,000 |
| Tier 1 position cap (at cost) | 5% of NAV | | £5,000 |
| Tier 2 speculative stake (fixed) | 0.75% of NAV | | £750 |
| ETF cap while sector is ROTATION-IN | 10% of NAV | | £10,000 |
| Per-sector bloc ceiling (all vehicles, **excluding cash**) | 25% of NAV | | £25,000 |
| Speculative sleeve, aggregate | 10% of NAV | | £10,000 |
| "Large position, no stop" flag | 20% of NAV | | £20,000 |
| Target position count at full deployment | 12–15 | | |

> **Cash is exempt from both caps** *(23 Aug 2026)*. Short-dated government bills sit in the `Cash`
> sector of `sector_map.md`: counted in NAV, excluded from the bloc ceiling and the 5% line cap,
> because both rails bound concentration risk and a three-week T-Bill carries none. Corporate
> notes keep issuer risk and stay in `Bonds`, under the rail. Enforced by `CASH_SECTORS` in
> `tools/checks.py`; see `rules/02_SLEEVE_RULES.md` §5.
>
> **The bloc ceiling is a safety rail, not a preference.** A single sector tag can lift several overlapping ETF lines at once — four correlated developed-market beta funds at 10% each is 40% of the sleeve in one bloc wearing four tickers. Adjust the number deliberately if you want more exposure; **do not remove the rail.**

## 3. Currency basis

```
BASE_CURRENCY  = GBP
CAP_BASIS      = native      # native | converted
```

**`native` (default):** the cap is *N units of the currency the line trades in* and **does not convert**. £5,000 on GBP lines, $5,000 on USD lines. A USD position is therefore worth less in sterling terms, and that ceiling drifts with FX — accepted deliberately for order-ticket simplicity.

⚠️ **The recurring error this causes:** computing USD headroom by converting the sterling cap. A position at $4,984 of a $5,000 cap is *full*, even though it looks ~£1,250 short if you misread the cap in sterling. That mis-read produces recommendations you cannot fund.

**ETFs are not exempt.** Some ETFs trade in USD while the broker CSV records book cost in GBP. Compute headroom in **USD cost** — derive it from shares × average USD entry price if the CSV doesn't give it.

The **bloc ceiling is the one deliberate exception**: it aggregates across currencies, so it is measured in your base currency — **on the broker's own sterling market value per line (`Market Value £`)**, not book cost. *(Decision 2026-08-18: the previous "recorded book cost" wording was uncomputable from the export — book cost ships in native currency — and produced two irreconcilable manual readings of the same rail on the same day, 33.3% vs 24.7%. Market value is always present, reproducible, and tracks current exposure, which is what a concentration rail guards. `tools/checks.py --post` computes it; a hand-derived bloc figure that disagrees with the check is wrong by definition.)*

## 4. Gate card thresholds

| Gate | Parameter | Default |
|---|---|---|
| 1 | Composite score floor | 60, **and** ACCEL or RECORD |
| 2 | Cash Flow floor | 7/10 |
| 2 | Stability floor | 5/10 |
| 2 | Profit floor | 13/30 |
| 4 | Distribution lookback | 10 sessions |
| 5 | Earnings blackout — full size | 14 days |
| 5 | Earnings blackout — hard stop | 7 days |
| 5 | Binary-event window | 10 trading days |
| 6 | Consensus headroom | ≥15% below PT |
| 6 | 52-week-high proximity | not within 10% |
| 7 | Fill tolerance vs written trigger | 2–3% |
| Tier 2 | Speculative score floor | 15 |
| Tier 2 | Max concurrent speculatives | 5 |

**This card is for individual stocks.** ETFs run the separate card below — gates 1 and 2 are unanswerable for a basket, and treating "no company data" as a pass is what left the largest positions in the sleeve ungated.

## 4b. ETF gate card thresholds

| Gate | Parameter | Default | Note |
|---|---|---|---|
| 1 | Sector thesis | ROTATION-IN this run, **or** bellwether above a rising 150-day | Not a remembered tag |
| 2 | Minimum fund AUM | £100m | Below this, closure and spread risk dominate |
| 2 | Maximum bid-ask spread | 0.30% | The cost you actually pay, unlike TER |
| 2 | Maximum TER | 0.65% | Raise for genuinely niche exposure, deliberately |
| 2 | Replication | Physical | Synthetic permitted **with a written reason** |
| 2 | Maximum tracking difference | 1.0%/yr | vs stated index, trailing 12m |
| 5 | Constituent earnings cluster | <25% of fund weight reporting within 7 days | The basket equivalent of binary risk |
| 5 | Reconstitution / rebalance window | 5 trading days | |
| 6 | Premium/discount to NAV | ±0.5% | ±1.5% for ETCs and physically-backed commodity lines |
| 6 | 52-week-high proximity | not within 10% | Same breakout exception as the stock card |
| 7 | Fill tolerance vs written trigger | 2–3% | |
| 8 | Overlap with existing holdings | ≤10% of sleeve NAV | Top-10 constituents you already hold, directly or via another fund |
| 8 | Lines tracking one index | 1 | |

⚠️ **Gate 8 has no starter option.** Every other gate can be half-sized into; an overlap fail cannot, because a duplicated bet at half size is the same duplicated bet. This is the check that would have caught the four-overlapping-beta-ETF episode in `rules/02_SLEEVE_RULES.md`, where every line passed its own test and the bloc was ~40% of the sleeve in one position wearing four tickers.

## 5. Stops

| Stop | Default |
|---|---|
| Trading Stop | 10–15% below the breakout point |
| Investing Stop | 20–25% below the breakout, or at/near cost |
| Basis | **Daily close.** Price alerts, not resting intraday orders |
| Mature-position exit | A decisive close below the rising 150-day |
| **Signal-ruled** (broad index / diversified sector ETFs) | **No stop level.** Exit on a decisive close below a flattening or declining 150-day. Exempt from the ratchet and from the "large position, no stop" flag — but must be stated in every run as `signal-ruled (150d @ <level>)` |

**Trailing ratchet** — up only, a stop never moves down:

| Milestone | New stop |
|---|---|
| +10% on cost | Breakeven |
| +20% on cost | Locks in ~+10% |
| Beyond +20% | Higher of: just below the rising trend MA, or ~15% below the highest daily close |

Not applied to Tier 2 (no stop by design) or index vehicles (signal-ruled).

## 6. Radar parameters

Set in `engine/heartbeat_radar.py`:

| Constant | Default | Meaning |
|---|---|---|
| `MIN_FULL` | 160 | Sessions needed for a 150-day line |
| `MIN_SHORT` | 60 | Sessions for a reduced 50-day read |
| `LOWLIQ_USD` | 3,000,000 | 60-day avg dollar volume below this → `LOW-LIQ` |
| `COIL_PCTL` | 25.0 | 20-day range must sit in the bottom quartile of its own year |
| `RS_LEADER` | 80.0 | RS percentile at/above which a name is tagged `RS-LEADER` |
| `VOL_WINDOW` | 5 | Sessions scanned for a volume spike |
| `FX_FALLBACK` | 1.34 | GBP→USD if the FX fetch fails |

**Rotation thresholds** (in the rotation read, v2 — 16 Aug 2026):

- **ROTATION-IN** (= base `IN`) — score_passes (size-normalised floor + > 2× ratio rules; the score a tiebreaker), tag `STRONG-IN` if EARLY > LATE arrivals, `CHASING` if LATE > EARLY
- **ROTATION-OUT** (= base `OUT`) — same with signs flipped, `FADING-OUT` / `EXHAUSTED` when leaving-magnitude shrinks over 3 runs
- **MIXED** — its own half-state, fired when both sides ≥ 2 OR > 30% round-trips AND the score can't pick a clean side. **Not actionable**; gate 1 of the ETF card rejects MIXED outright
- **Single-stock sectors** (≤ 2 names) — `in_min = 1`, gauge **CONFIRMED** required
- **Gauge enforcement** — 3 consecutive CONFLICT/ERROR gauge runs auto-demote IN/OUT (with phases) to MIXED. Persisted in `rotation_history.json`

## 7. Paths

**You edit `input/`. The system writes `output/`.** Nothing crosses.

| What | Where | Edited by |
|---|---|---|
| Broker exports | `input/*.csv` | you |
| Watchlist (Tier 1 — evaluated) | `input/watchlist.md` (or `watchlist_*.md`) | you |
| Tracking (Tier 0 — radar-only, NOT evaluated) | `input/tracking/*.md` | you |
| Ticker → sector + bellwethers | `input/tracking/sector_map.md` | you |
| Radar reports | `output/radar/` | generated |
| Daily evaluations | `output/evaluation_<date>.md` (+ `output/latest.md` pointer) | generated |
| P&L and post-mortems | `output/reports/` | generated |
| Gate ledger | `output/ledger/Gate_Ledger.csv` | **appended; only today's own `daily-eval` rows are ever rewritten** |
| Radar / rotation state | `output/.state/` | generated, disposable |

Override either side per run, or per sleeve:

```bash
python3 engine/heartbeat_radar.py --input-dir ~/sleeveA/in --output-dir ~/sleeveA/out
TP_INPUT=~/sleeveB/in TP_OUTPUT=~/sleeveB/out python3 engine/heartbeat_radar.py
```

⚠️ **`output/ledger/Gate_Ledger.csv` is the one file that is never regenerated.** It is the only record of decisions the evaluations cannot provide, because they are regenerated each run. **Back it up.** Everything else under `output/` can be rebuilt by re-running; the ledger cannot.

One bounded exception, and it is the only write in the system that is not an append: `tools/append_gate_ledger.py` replaces rows dated *today* whose `Source` is `daily-eval`, so a same-day re-run corrects its own record instead of filing a second opinion next to the first. It is scoped by date **and** source — a position you entered by hand today is not its to touch — it copies the file to `.bak` before every write, and it refuses the whole batch rather than write a row whose fields have shifted.

## 8. File wiring

**Nothing to configure.** As of 12 Aug 2026 there is no file wiring: every `*.csv` in
`input/` and every `watchlist*.md` at the top of `input/` is picked up
automatically,
broker column names are matched at runtime, and price-feed tickers are resolved from the
exchange tag in the instrument name, then `input/tracking/sector_map.md`, then the trading currency.

This replaced three hand-edited tables inside `engine/heartbeat_radar.py`
(`HOLDINGS_SOURCES`, `WATCHLIST_SOURCES`, `ROSTER`) that had to be filled in before a
first run produced anything — a programming task standing in front of a screening tool.

**The one thing worth knowing:** ticker resolution guesses, and every guess prints its
basis on the run. To make one authoritative, add a row to `input/tracking/sector_map.md` with the
exact ticker. A guess the price feed rejects is retried in its other form (bare ↔ `.L`)
before being written off, so a bad guess self-corrects rather than becoming a holding
with no exit line. Rows with no price series are counted and named, never dropped
silently. Full matching tables: [`input/README.md`](input/README.md).

## 9. Scheduling

| Task | Cadence | Command |
|---|---|---|
| Radar screen | Weekdays, after the close | `python3 engine/heartbeat_radar.py` |
| Daily evaluation | Weekdays, after the radar | `/atd-daily` — the agent pipeline of `rules/03_DAILY_RUN.md` |
| RRG snapshot | Weekly (Sundays) | `python3 engine/heartbeat_radar.py --rrg` |
| Tracking refill | As needed | Append to `input/tracking/universe.md`, drop stale rows. **No per-sector cap** (the 8-cap was retired with the count-based rotation read — bellwether ETFs supply direction). `input/tracking/sector-coverage.md` exists to hold thin sectors at ≥3 members, the floor below which a sector's own cluster needs its bellwether to confirm before an exit reads |
| P&L + gate scoring | Monthly, first Friday | `python3 tools/pnl.py` |

Both scripts write a dated file **and** update `latest.md` in the same folder.

**Ordering matters:** the radar must run before the evaluation, or the evaluation reads yesterday's flags. If the radar file is more than 3 trading days old, the run must say so and treat the technical leg as stale.
