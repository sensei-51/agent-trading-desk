# 02 — Sleeve Rules: Entry Gates, Tiers, Sizing & Stops

*Purpose: stop volatility churn. **No new position without a completed gate card.***

**Paired file: `templates/watchlist.template.md`** — the candidate list. This file governs *how much and whether*; that file governs *what*.

**Hierarchy:** `01_METHOD.md` (method) → this file (gates & sizing) → the watchlist (candidates). **Stricter rule wins**, except the Speculative Tier, which is a deliberate size-limited exception.

---

## A note on the numbers

Every size in this file is expressed as a **percentage of sleeve NAV** — the market value of the trading sleeve this rulebook governs, not your total net worth or total pension.

The worked examples use a **nominal £100,000 sleeve** purely for readability. Substitute your own figure. Set it once in `CONFIG.md` and the whole file scales.

| Parameter | Rule | At a £100K sleeve |
|---|---|---|
| Max risk per trade | **0.8–1.0% of sleeve NAV** | £800–1,000 |
| Tier 1 position cap (at cost) | **5% of sleeve NAV** | £5,000 |
| Tier 2 speculative stake (fixed) | **0.75% of sleeve NAV** | £750 |
| ETF cap while sector is ROTATION-IN *(not SUSTAINED)* | **10% of sleeve NAV** | £10,000 |
| Per-sector bloc ceiling (all vehicles, **excluding cash**) | **25% of sleeve NAV** | £25,000 |
| Speculative sleeve, aggregate | **10% of sleeve NAV** | £10,000 |
| "Large position with no stop" flag | **20% of sleeve NAV** | £20,000 |

---

## Two-tier structure

| Tier | Size | Stop | Gates |
|---|---|---|---|
| **1 — Quality** | Up to **5% of sleeve NAV at cost** per position | Two-stop system, daily-close basis | All gates on the card for its vehicle — 7 for a stock, 8 for an ETF |
| **2 — Speculative** | **0.75% of sleeve NAV**, fixed | **None initially** — the stake *is* the stop | Composite score **≥ 15** (lowered, not waived) + chart sanity + event window |

**Why the Speculative Tier exists.** The 7-gate stock card structurally blocks low-score small caps with 10× potential — including names that screen badly on fundamentals yet run hard. The prior failure mode was *full size + whipsaw stops in 100%+ volatility names*: the worst of both. A 0.75% unstopped stake caps the worst case inside the per-trade risk budget while leaving room to run.

---

## The stock gate — all 7 must pass for Tier 1 full size

| # | Check | Pass condition | Source |
|---|---|---|---|
| 1 | **Composite score** | Score **≥ 60** AND tagged **ACCEL or RECORD** | Fundamentals scorer |
| 2 | **Pillar floors** | Cash Flow **≥ 7/10** AND Stability **≥ 5/10** AND Profit **≥ 13/30** | Fundamentals scorer |
| 3 | **MA gatekeeper** | Price above a **rising** trend MA | Chart platform |
| 4 | **Volume character** | Accumulation (green-day volume); **no red distribution spikes in the last 10 sessions** | Chart platform |
| 5 | **Event window** | **No earnings within 14 days** (starter allowed 7–14D, nothing inside 7D). No scheduled binary event — regulatory ruling, summit, lock-up expiry — within **10 trading days** | Web check |
| 6 | **Valuation headroom** | Below analyst consensus by **≥ 15%**. Not within 10% of the 52-week high — *exception:* a fresh volume breakout above a completed base may enter at a new high | Web check |
| 7 | **Entry discipline** | Fill within **2–3% of the written trigger price**. If it has run past that: no trade, log it, wait for the retest | Order ticket |

**Any single fail = no full entry.**
One fail on checks **5–6 only**, with 1–4 all passing → **starter (half risk)** permitted.
**Two or more fails → watchlist only.**

*Each gate exists because something specific got through without it. Keep the "kills which losers" column in your own copy — a gate whose failure history you can't name is a gate you will eventually relax.*

**This card is for individual stocks.** ETFs and other baskets run the card below.

---

## The ETF gate — all 8 must pass for full size

### Why this card exists at all

The stock card cannot be applied to a fund, and for a long time this file pretended otherwise. Gates 1 and 2 demand a composite score, an ACCEL/RECORD tag and pillar sub-scores — **there is no company to score.** No fundamentals product emits a Cash Flow `/10` for a basket, and none ever will.

That left a contradiction sitting in the middle of the ruleset:

- `agents/trader.md` §1 **requires** every ROTATION-IN sector to land on a buyable ticker by running its *Investable line* through the gate card — and nearly every investable line in the bellwether table is an ETF.
- The rotation-conditional cap below grants ETFs **double the single-stock size** — the largest sizing privilege in this file.
- Yet under the stock card every one of those vehicles fails gates 1 and 2 automatically.

So in practice ETFs were either being waved through the two gates nobody could evaluate — meaning the biggest positions in the sleeve rested on the least-documented exemption — or they were being blocked, making step (e) impossible and the entire rotation read unactionable. **Both readings were live at once, which is how a rule dies.** An undefined exemption is not a lenient rule; it is no rule, and it will be resolved in whichever direction is convenient on the day.

### The card

Gates 3, 4 and 7 are price-and-volume tests. They carry over **unchanged** — a fund's tape is as readable as a stock's. The other four are replaced by the nearest question that is actually answerable about a basket.

| # | Check | Pass condition | Source |
|---|---|---|---|
| 1 | **Sector thesis** *(replaces composite score)* | **Either** the sector's tag in *this run's* radar is `ROTATION-IN` / `STRONG-IN` / `CHASING` / `SUSTAINED`, **or** its tag is `—` and its bellwether gauge is above a **rising** 150-day **or** reads `^STRONG` (20-day momentum > +5%). `MIXED` / `ROTATION-OUT` / `FADING-OUT` / `EXHAUSTED` **fail outright — the gauge fallback cannot rescue an explicit exit tag.** A remembered tag is not a tag | Radar rotation read |
| 2 | **Fund structure** *(replaces pillar floors)* | **AUM ≥ £100m** · **spread ≤ 0.3%** · **TER ≤ 0.65%** · **physical replication** (synthetic requires a written reason) · **UCITS / reporting-fund status** for the base currency · **tracking difference ≤ 1.0%/yr** | Factsheet / KIID |
| 3 | **MA gatekeeper** | Price above a **rising** trend MA | Chart / radar |
| 4 | **Volume character** | Accumulation; **no red distribution spikes in the last 10 sessions** | Chart / radar |
| 5 | **Event window** *(replaces earnings)* | No **constituent earnings cluster** — under 25% of fund weight reporting within 7 days. No index reconstitution or scheduled rebalance inside 5 trading days | Web check |
| 6 | **Premium / extension** *(replaces consensus PT)* | Trading within **±0.5% of NAV** (±1.5% for ETCs and physically-backed commodity lines). Not within 10% of the 52-week high — *same breakout exception as the stock card* | Factsheet / web |
| 7 | **Entry discipline** | Fill within **2–3% of the written trigger price**. If it has run past that: no trade, log it, wait for the retest | Order ticket |

**Gate 1, and the three changes made to it on 22 Aug 2026** *(`docs/BACKLOG.md` item 5;
diagnosis in `docs/ROTATION_DIAGNOSIS_2026-08-21.md` §5 and §8)*:

1. **The phase tags are now written down.** The card said `ROTATION-IN` while
   `agents/manager.md` rule 8 had always passed `STRONG-IN` and `CHASING` as well. The
   reviewer was the de-facto rule and the card was stale. `CHASING` still carries its
   "wait for a pullback to the 150-day, then re-check" qualifier on the recommendation
   line — passing gate 1 is not the same as entering today.

2. **`SUSTAINED` passes.** It is the radar's continuation state: the sector is already
   moving, with 2+ of its members above a rising line near their highs *and*
   accumulating above the universe median. Gate 1 asks whether there is a sector
   thesis, and for such a sector there manifestly is one. This is the change that
   would have unblocked KNT.TO on 20 Aug, where a **7/7, all-pillars, score-87 gate
   card was held at WAIT** with "Gold not tagged" given as the reason — while gold's
   own gauge momentum read +22%. **It does not lift the doubled ETF cap** (see the
   rotation-conditional cap below): passing a thesis gate and being authorised for
   double size are different questions, and a continuation is by construction already
   extended.

3. **`^STRONG` joins the fallback, and the fallback is now subordinate to the tag.**
   The old fallback was "above a rising 150-day" — the same lagging instrument whose
   slope produced the original miss, so it failed in exactly the conditions it was
   meant to cover (GDX sat **+10% above** its 150-day on the day it mattered, but the
   line read *Flat*). A 20-day momentum limb covers the reversal case the level-and-
   slope test cannot. Adding a faster limb to an unconditioned `or` would have
   widened the gate a long way, so the fallback is simultaneously **restricted to
   sectors reading `—`**: it exists to speak where the cluster is silent, never to
   overrule a cluster that has spoken. That restriction was not in the old wording and
   is a genuine tightening — an `EXHAUSTED` sector with a bouncing bellwether used to
   pass gate 1 on the fallback alone.

**And one gate a stock does not need:**

| # | Check | Pass condition | Source |
|---|---|---|---|
| 8 | **Overlap** | Combined weight of the fund's top-10 constituents that you **already hold** — directly or through another fund — **≤ 10% of sleeve NAV**. And no more than **one** line tracking a given index | Holdings + factsheet |

Same pass arithmetic as the stock card: any single fail blocks full entry; one fail on **5–6 only** with the rest clean permits a **starter at half risk**; two or more fails means watchlist only. **Gate 8 is never starter-eligible** — an overlap fail is not made safe by being smaller, it is the same duplication at a lower price.

### Why gate 8 is not optional

The 25% bloc ceiling below catches *size* but not *duplication*, and duplication is the specific way an ETF book goes wrong. The worked example is already in this file: a single "Index" ROTATION-IN tag lifted four developed-market beta ETFs at once — three US large-cap with heavy constituent overlap, **two tracking the same index**, and the largest constituent held directly on top. Every line passed its own test. The bloc would have been ~40% of the sleeve wearing four tickers: concentration disguised as diversification, assembled entirely out of individually-legitimate decisions.

Nothing in gates 1–7 sees that, because nothing in gates 1–7 looks at what you already own.

### Signal-ruled exits — what the ratchet exemption means

The trailing ratchet below exempts "index vehicles (signal-ruled)". **Signal-ruled** means:

> **A decisive daily close below a flattening or declining 150-day line is the exit. While the 150-day rises and price holds it, the position stands — no milestone stops, no trailing band, no trimming on extension.**

The milestone ratchet is built for idiosyncratic risk: a single company can gap 40% on one announcement, so the stop must climb to protect gains. A diversified basket cannot do that, and a +10%-to-breakeven stop on an index line converts ordinary market noise into a forced sale near the bottom of it. The 150-day is the same line the sleeve already uses for mature-position exits and for the index tripwire in `01_METHOD.md` — this is not a new mechanism, only a name for one already in use. The radar computes it every run.

**Consequences, stated so they aren't quietly reversed:**

- A signal-ruled position has **no stop level to raise**, so it never appears in the stops review as "needs ratcheting". It appears there only when price approaches its 150-day.
- The `£20K position with no stop set` flag in proactive screening **does not fire** on a signal-ruled line. The 150-day *is* its stop. It must still be stated in the run as `signal-ruled (150d @ <level>)` — an exemption you can't see is indistinguishable from an oversight.
- Signal-ruled applies to **broad index and diversified sector vehicles only.** A single-country, single-commodity or thematic fund of under 30 holdings is concentrated enough to behave like a stock: it runs the normal ratchet.

### Existing ETF positions

**Grandfathered.** Positions held before this card existed keep their size and are **never force-sold by it** — manufacturing a sell decision out of a documentation change is precisely the churn this file exists to prevent, and the rule that exits come from the stop and the 150-day, never from a rules revision, applies here exactly as it does to cap changes.

**Every add is gated.** The card applies in full to any further buying, including adds to a position that predates it.

---

## Sizing — risk first, size second

- **Max risk per trade: 0.8–1.0% of sleeve NAV.**
- **Max position size: 5% of sleeve NAV at cost.** The cap applies **at cost, not market value** — winners run uncapped. More names, more spread: ~12–15 positions at full deployment.
- **Size = risk ÷ stop distance**, then truncate to the cap. A 15% stop → ~6% of NAV before the cap bites; a 25% stop → ~3.5%.
- Stops are **daily-close basis** — set price *alerts*, not resting intraday stop orders. Exit next morning if the close confirms. (Resting hard stops only for names already in breakdown.)
- **Speculative sleeve** — Tier 2 positions plus anything failing gates 1–2 that is held on a thesis: capped at **10% of sleeve NAV** in aggregate.

### The cap is a sizing constraint, not a signal

**Never downgrade a signal because the position is at the cap.** The signal answers *is this a good idea*; the cap answers *how much can go in*. Collapsing the second into the first destroys information — a name reading BUY-but-full and a name reading HOLD-on-merit look identical in the report, and the reader cannot tell which positions would be added to if capital were available.

- Rate every name on its **merits** — gates, tape, conviction — exactly as if no position were held.
- State the cap consequence **separately on the same row**: `🟢 BUY (capped)`, with the headroom and the size that would have been bought in the note.
- A capped BUY is a **standing instruction** for the next time capital frees up — an exit, a cap change, a contribution. It is the queue, and the queue is only visible if the signal is honest.

*Origin: a position printing 2.1× volume over four sessions, accumulation ratio 2.03, rising 150-day and 50-day, ~20% below its 52-week high and carrying the highest strategic conviction weight in the book — written up as "HOLD" solely because book cost sat £9 under the cap. That is a buy the sleeve could not fund, reported as a buy the sleeve did not want.*

### Currency basis — native currency

The cap is **5% of sleeve NAV expressed in the currency the line trades in**, and it **does not convert**. On a £100K sleeve: £5,000 on GBP/LSE lines, **$5,000 on USD lines**. A USD position is therefore worth ~£3,750 at 1.33, and that ceiling moves with the exchange rate — accepted deliberately for order-ticket simplicity.

Consequence to apply every run: **do not compute USD headroom by converting the sterling cap.** A position at $4,984 of a $5,000 cap is full, even though it looks ~£1,250 short if the cap is misread in sterling. That mis-read produces unfundable starter recommendations.

**ETFs are not exempt from the currency basis** (they run their own gate card, but the cap arithmetic is identical). Some ETFs trade in USD while the broker CSV records book cost in GBP — headroom must still be computed in **USD cost** (derive from shares × average USD entry price if the CSV doesn't give it). One basis, no per-name exceptions.

### Rotation-conditional ETF cap — 10% of sleeve NAV, native currency

**An ETF may run to 10% of sleeve NAV at cost — double the single-stock cap — while its sector is tagged ROTATION-IN in the current run's radar rotation read.** Native currency, never converted, same basis as above.

Rationale: the cap exists to contain **idiosyncratic** risk, and every failure it was written against is a *single company*. A diversified fund does not carry that risk, and the radar's output is sector-level — the sleeve should be able to fund its own conclusions with a basket rather than being forced to express a sector view through single stocks.

**Conditions, all binding:**

1. **ETFs only.** Single stocks stay at 5% regardless of sector tag. A sector being ROTATION-IN does nothing for an individual stock in it.
2. **Live tag required.** The sector must read ROTATION-IN in *this run's* radar, not a remembered one. Sector is read from `input/tracking/sector_map.md`.

   **`SUSTAINED` does NOT lift the cap** *(22 Aug 2026)*. It passes gate 1 — the sector
   thesis is real — but the doubled cap is written against a *fresh* rotation, and
   `SUSTAINED` means the opposite: the move is already underway and every member of
   the cohort is near its high by definition. Doubling size into an extended move is
   the one thing this cap exists to prevent. `STRONG-IN` and `CHASING` are IN-base
   tags and do lift it; `SUSTAINED` is its own base and does not.
3. **Revert on flip is a no-add, never a forced sell.** If the tag lapses, the cap returns to 5% and any cost above that is **grandfathered**. Selling because a 20-day flag count changed is exactly the churn this file exists to stop. **Exits come from the stop and the 150-day rule, never from a cap revision.**
4. **Risk-first still governs.** 10% of NAV on a 12% stop is 1.2% of NAV at risk — over the per-trade budget. The cap is a **ceiling, not a target**: size from risk ÷ stop distance first, then truncate.
5. **⚠️ BLOC CEILING — 25% of sleeve NAV at cost per sector, across all vehicles, excluding cash.** *The one deliberate exception to the native-currency basis: it aggregates across currencies, so it is measured in your base currency at recorded book cost. Per-line caps stay native; the cross-line ceiling is base.*

   **Cash is not a bloc, and neither cap applies to it** *(23 Aug 2026)*. Short-dated government bills — the `Cash` sector in `sector_map.md` — are counted in NAV and excluded from both the bloc ceiling and the 5% line cap. Both caps bound **concentration**: how much of the book is impaired if one sector or one name goes wrong. A three-week T-Bill does not go wrong in that sense. Counting it as a bloc reports danger where there is none and, worse, consumes apparent headroom that belongs to the positions actually at risk — on the day this was written, three bills held as dry powder pushed a bloc to 24.1% of the ceiling and tripped the line cap three times over, describing no risk at all. **Credit instruments are a different question and stay in `Bonds`:** a corporate note carries issuer risk and belongs under the rail. `tools/checks.py` enforces this split via `CASH_SECTORS`.

   Added as a safety rail, not a preference — **without it this rule is dangerous.** A single sector tag can lift four overlapping lines at once. Worked example: "Index" tagging ROTATION-IN lifted four developed-market beta ETFs simultaneously, three of them US large-cap with heavy constituent overlap (two tracking the *same* index, with the largest constituent also held directly on top). Filling all four to 10% would have put **~40% of the sleeve into one correlated bloc wearing four tickers** — concentration disguised as diversification. **Adjust the number deliberately if you want more; do not remove the rail.**

**Grandfathering:** positions that predate a cap change keep their size. Hold rules apply; **no adds** while above the current cap.

### Trailing-stop ratchet

Milestone-based, daily-close basis, **ratchet up only** — a stop never moves down. Checked in every run's stops review.

| Milestone | Action |
|---|---|
| **+10% on cost** | Raise stop to **breakeven** (the free-trade point) |
| **+20% on cost** | Raise stop to lock in **~+10%** |
| **Beyond +20%** | Trail at the **higher** of: just below the rising trend MA, or **~15% below the highest daily close** |

Milestones are deliberately loose to avoid the tight-stop whipsaw failure mode. Not applied to Tier 2 (no stop by design) or to **signal-ruled index vehicles** — defined under the ETF gate card above: a decisive close below a flattening or declining 150-day is the exit, and there is no milestone stop to raise.

---

## Speculative Tier — full rules

### Entry

- **0.75% of sleeve NAV, fixed. No stop loss** — room to run through the volatility that kills tight-stopped high-beta positions. **No averaging down, ever.**
- **Score floor: ≥ 15.** Gate 1 is *lowered* (from 60), not waived — no ACCEL/RECORD tag required. Gate 2 pillar floors are waived. This admits genuine high-upside speculatives but still blocks bottom-decile names. **If the scorer has no data on a name, that is a fail, not a pass.**
- **Still required:**
  - **Chart sanity:** MA flattening or turning up, accumulation visible, not in active breakdown. No entry into a falling knife.
  - **Event window:** no earnings within **7 days**.
  - **Logged in the watchlist**, tagged `SPECULATIVE`, with the source noted. The gate *card* — scores, levels, pass/fail — belongs in the evaluation file, not the stateless list.
- **Sleeve cap: max 5 concurrent speculative positions**, and speculative + thesis-holds combined ≤ 10% of sleeve NAV. Damage is only limited per position; the cap limits it in aggregate.

### Scale-up (Tier 2 → Tier 1)

- **Trigger (written, not discretionary):** the name passes the chart gates it failed at entry — **rising trend MA + volume breakout above the written trigger price.**
- **Action:** add up to the full 5% cap at cost. The add gets a stop below the breakout, sized so **remaining risk on the combined position ≤ 1% of sleeve NAV**. From that point it is a Tier 1 position and all hold rules apply.
- **No scale-up on price alone** — the trigger must fire on volume with the MA confirmed.

### Exit (no stop ≠ no exit)

- **−50% from entry:** mandatory review. Thesis intact with accumulation building, or recycle.
- **90 days with no momentum** (no MA turn, no volume event): recycle the capital. *The sleeve must not fill with dead corpses.*

### Weekly capture

Log any speculative idea surfaced that week as a `SPECULATIVE CANDIDATE` in the watchlist regardless of score. Run the chart-sanity check; enter only if it passes.

---

## Weekly screening workflow

Run once a week, with the watchlist update.

1. **Fundamentals screen** — each active theme tab → investment style: *Record Quarter* → sort by composite score. Shortlist anything **≥ 60 with ACCEL/RECORD** not already held.
2. **Pillar check** — apply the floors (CF ≥ 7, Stability ≥ 5, Profit ≥ 13). Discard fails.
3. **Chart check** — rising MA + accumulation + base identified. Set a **200% volume alert** (1D, once per day) **and a price alert at the breakout trigger** for each survivor.
4. **Validation check** — earnings date, 52-week-high distance, consensus headroom ≥ 15%. Log the gate card in the evaluation file; add new names to the watchlist.
5. **Act only on alert fire.** A triggered price/volume alert on a name with a **completed gate card** is the *only* buy signal. **No alert, no trade.**

---

## Per-name gate state

Lives in the evaluation file, produced fresh every run — **never here.**

*A dated snapshot that once sat in this section went stale within days: names exited, scores were re-rated. Rules files hold rules; state belongs to the evaluations.*

---

## Gate ledger

`output/ledger/Gate_Ledger.csv` is the permanent audit trail of every gate decision — the record the evaluations can't provide, because they are regenerated each run. Rows are written automatically by `tools/append_gate_ledger.py` once the evaluation has passed review, and only today's own `daily-eval` rows are ever rewritten. Template: `templates/gate_ledger.template.csv`.

**Append one row per decision event, in the same run that makes it:**

- Any **entry, add, or exit** (`ENTERED` / `ADDED` / `EXITED`). Exits must record exit date and price — undocumented exits are unrecoverable.
- Any **BLOCKED / STARTER-CAP / WAIT / WATCHLIST** verdict from a gate card or pre-entry validation. **These rows are the point of the ledger.** `Price_At_Decision` is **mandatory** on them: a blocked idea without a price can never be scored.

**Rules:** append only. Never overwrite or delete rows. Prefix back-filled approximate dates with `~`.

**Monthly scoring (first Friday):** for every non-`ENTERED` row ≥30 days old, compare `Price_At_Decision` to the current price. Report **blocked-winner rate vs blocked-loser rate** — the empirical answer to *"are the gates filtering out the next great position, or saving us from the next disaster?"*

---

*Process rules, not financial advice. See `DISCLAIMER.md`.*
