# 01 — Method

*The analysis method the whole system sits on. Stock-agnostic. This file describes **how to read a name**; `02_SLEEVE_RULES.md` describes **how much to buy and whether**.*

> **Provenance note.** This is an original restatement of a widely-taught momentum/breakout framework — trend filter, volume confirmation, consolidation base, earnings acceleration. It is not a reproduction of any commercial course's materials, and it deliberately names no proprietary methodology. Bring your own data sources; see `docs/DATA_SOURCES.md`.

---

## Data sources — three legs, all mandatory

No single tool runs this method. Each leg is non-overlapping, and skipping one leaves a signal unverified.

| Leg | Supplies | Feeds |
|---|---|---|
| **Fundamentals scorer** | Composite quality score, pillar sub-scores (profitability, growth, cash flow, stability, valuation), earnings-acceleration tags; sector screener for discovery | Signal 3 — earnings acceleration |
| **Chart / flow platform** | Trend-MA direction and price-vs-MA, volume accumulation vs distribution, consolidation-box structure, RSI, earnings markers, institutional/dark-pool flow | Signals 1 and 2, plus the tactical flow read |
| **Web search** | Live price, 52-week high, analyst consensus PT, earnings date, rating changes | Pre-entry validation |

**Rules:**

- The fundamentals leg tells you **if** a name qualifies. The chart leg tells you **when / whether** to act. You need both before any call.
- Chart reads are visual — state derived levels as approximate (`~`). Scorer data is structured and exact.
- If a source can't be reached, **say so explicitly** and label which legs are therefore *inferred* rather than confirmed. Never silently skip a leg.

---

## The three signals

All three must align before entry. Missing one = watchlist only.

### Signal 1 — Institutional volume

**Principle:** volume is the signal. When institutions move, volume spikes. You follow smart money; you do not predict it.

Reading it:

- Up-arrows / green markers on volume bars = accumulation.
- Down-arrows / red markers = distribution.
- A large volume spike into a price breakout = institutional entry confirmed.
- Quiet, low-volume drift after a run = normal. Holders are holding.
- Red volume spikes during a decline = institutions exiting. Do not catch this.

**Alert setting:** volume moves above average by **200%** (2× average), daily interval, once per day. 2× is the qualifying threshold; 3×+ is stronger conviction but is not the bar.

### Signal 2 — The consolidation base ("heartbeat")

**Principle:** after a big move, strong names don't crash — they go sideways in a tight range while institutions accumulate. It looks boring. That is the setup.

Identification:

1. Prior significant run up
2. Sharp pullback or correction
3. Long sideways consolidation — price oscillating in a defined box
4. Volume drying up inside the box (no selling pressure)
5. Accumulation markers building on the volume panel

**Entry rule:** enter on a close **above the top of the box**, confirmed by a volume spike. The top of the box is the breakout point.

**What it is not:** a downtrend pausing below a declining MA; a distribution pattern (volume spiking on down days); anything below a falling moving average.

### Signal 3 — Earnings acceleration

**Principle:** only buy names whose earnings are growing *faster each quarter*, and preferably those that just posted their **fastest growth quarter on record**. Technical patterns without this are incomplete.

Two tags to look for in the scorer:

- **ACCEL** — each quarter's earnings growth faster than the last
- **RECORD** — the most recent quarter was the fastest in company history

Screen: sector tab → filter on earnings momentum / record quarter → sort by composite score descending → take names tagged ACCEL or RECORD.

---

## The entry filter stack

All five must be confirmed before any position:

| # | Check | Condition | If failed |
|---|---|---|---|
| 1 | Moving average | Price above a **rising** MA | Watchlist only |
| 2 | Volume | 2×+ average volume spike present or building | Watchlist only |
| 3 | Consolidation base | Price in, or breaking out of, a box | Wait for the box |
| 4 | Earnings acceleration | ACCEL or RECORD confirmed | Watchlist only |
| 5 | Pre-entry validation | No earnings within 7D; not within 10% of the 52-week high; not above analyst consensus | Starter only, or defer |

**Speculative-tier exception:** the full stack blocks small caps with high upside and poor scores by construction. The Speculative Tier in `02_SLEEVE_RULES.md` *lowers* check 4 rather than waiving it, and caps size so the worst case is contained. Checks 1–3 apply in relaxed form. The full stack re-applies at scale-up.

---

## The moving average — master trend filter

The trend MA is the **primary filter**, applied before anything else.

- **MA declining + price below it** → DO NOT BUY. Regardless of thesis.
- **MA flattening + price crossing above** → start watching for the breakout.
- **MA rising + price above, pulling back to it** → potential add / re-entry.
- **Price riding above a rising MA** → trend intact, hold.

The **50-day** is the tactical line: support during an uptrend, add point on a held pullback, reference for the Trading Stop.

---

## The two-stop system

Every position requires **both** stops. A position with one stop is incomplete.

| Stop | Level | Role |
|---|---|---|
| **Trading Stop** | ~10–15% below the breakout point | Active risk management. Close below = exit the trade |
| **Investing Stop** | ~20–25% below the breakout, or at/near cost | Thesis invalidation. Only on a sustained move through |

Every watchlist row needs: **Breakout Point** (the prior high / resistance), **Trading Stop**, **Investing Stop** — all written *before* entry.

---

## The 150-day line

1. **Mature-position exit line.** Once price is well extended above the breakout and the 150-day has risen to meet the position, the Investing Stop **migrates** from the static −20–25% level to: *a decisive close below the 150-day = exit.* Stay in while it holds the rising 150-day.
2. **Role split.** 50-day = tactical (adds, pullback support, Trading Stop reference). 150-day = strategic (thesis invalidation). Both stops still set at entry; the 150-day takes over as the trend matures.
3. **Index tripwire.** The broad index closing below a flattening or declining 150-day = automatic 🔴 DEFENSIVE regime review in the daily run. Historical precedent: the S&P broke its rising 150-day in late 2007, roughly 8 months before the crisis peak.
4. **Volume trigger = 2× average** (see Signal 1).
5. **Rotation, reactive:** when a held leader stalls (base fails, sector goes tired), check where the flow went *before* redeploying. Quality gates are unchanged at the destination.
6. **Rotation, proactive.** Rule 5 only fires *after* a holding stalls, which finds the destination late. The radar's `## Rotation read` detects rotation independently by clustering flags across the whole universe by sector: **2+ names arriving with little leaving = ROTATION-IN; 3+ leaving with little arriving = ROTATION-OUT.** Check it every run, before assessing any individual name.
   - **A cluster of breakouts in an "off-theme" sector is the highest-value output of the radar**, because the active-theme list always describes the *previous* regime. Never filter candidates by theme before reading the clusters.
   - **Three states, not two** *(22 Aug 2026)*. Arriving and leaving are both *transitions*; a sector that is simply **already moving** is neither, and for eighteen consecutive runs such a sector produced no row in the table at all — the strongest 20-day momentum on the board reading as silence. `SUSTAINED` is that third state: 2+ members, and at least half the sector, above a rising line and near their highs while accumulating above the universe median. It is a **weaker claim than ROTATION-IN and must not be read as one** — money has not left and is still being committed, which is not the same as money arriving.
   - The `## Sector pressure` table below the rotation read asks the same question of the **continuous** measures rather than the thresholded flags, and produces no tag at all. Where the two disagree, the disagreement is the finding.
   - State each run: what fraction of the sleeve sits in ROTATION-OUT sectors vs ROTATION-IN/SUSTAINED, and whether the position cap is what blocks leaning into the destination.

*One-line summary: spot the base → follow the rotation → hold while it holds the 150-day → stop set before you buy.*

---

## Distribution vs accumulation

The most important pattern skill. They look alike and mean the opposite.

| | **Distribution** (institutions exiting) | **Accumulation** (institutions entering) |
|---|---|---|
| Price | At/near highs, failing to make new ones | At/near lows after a decline |
| Volume | Spikes on **red/down** days | Spikes on **green/up** days, or quiet building |
| MA | Rolling over — flattening then declining | Flattening then curving up |
| Structure | Repeated failure at resistance | Tight oscillation above support |
| Action | **Exit or reduce. Do not add.** | **Watch for breakout. Prepare entry.** |

The sequence: distribution box at highs → decline → accumulation base at lows → volume breakout above the box ceiling → entry confirmed.

---

## The prior high / breakout point

**The prior significant high IS the breakout point.** Draw a horizontal line at it. Price will approach it repeatedly — that is the base consolidating below resistance. A **close above on a volume spike** is the entry signal, and the prior high becomes support.

This is not a guess. It is the exact price of the prior high. It goes in the watchlist as *Breakout Point*.

---

## IPO recovery playbook

Fresh listings often follow a predictable arc:

1. IPO → excitement → run
2. Lock-up expiry / reality check → 40–70% give-back
3. Base formation → floor, quiet accumulation
4. Recovery trade → target is often a return to the IPO price

**Conditions:** MA must flatten and turn up from the post-crash lows; accumulation building; a base above clear support. **Do not enter while the MA is still declining**, however compelling the story.

---

## Dip-or-trap check

Run before any "it's down, is it a buy?" decision, and before averaging down on anything. Three questions, in order:

| # | Question | Green | Red |
|---|---|---|---|
| 1 | Did the business actually break? | Sales growing, guidance steady/raised, no ugly surprise (non-cash charges don't count) | Sales shrinking, guidance cut, margin collapse, negative FCF, lost anchor customer |
| 2 | Whole neighbourhood or just this house? | Sector down together (power outage) | This name alone while peers are fine (house fire) |
| 3 | What is smart money doing? | PTs held/raised, insiders buying the drop | PTs cut, insiders selling into the fall |

**Two or more RED = ⚠️ TRAP CHECK FAILED.** Treat as a broken thesis, not a dip — no entry, no averaging down, regardless of the name's reputation or how far it has fallen. One red = proceed only with the full stack and reduced size.

This screens the **fundamental** leg only. A pass does not waive the technical stack: a name can be triple-green and still be a no-entry because it sits below a declining MA.

---

## Watchlist management

Updated **weekly**. Columns: Sector / Name / Symbol / Price / Breakout Point / Trading Stop / Investing Stop / Market-cap category.

| Category | Range | Note |
|---|---|---|
| Mega | >$200B | |
| Large | $10B–$200B | |
| Mid | $2B–$10B | |
| Small | $300M–$2B | |
| Micro | <$300M | Highest risk, widest stops — **starter positions only, never full size** |

---

## Crisis / shock overlay

**Tactical overlay, not a strategic change.** Shock effects are transitory (oil's median post-shock move is roughly +18% over three months, then fades). These rules govern behaviour *during* the event window (~30–90 days); the entry filter stack still applies to anything bought. **A crisis waives no check.**

| Phase | What happens | Rule |
|---|---|---|
| **1 — Shock** | Algos and retail sell together, VIX >20, even gold dips as pros raise cash | **No action.** No panic-sells, no spike-chasing. Phase 1 is a head-fake |
| **2 — Repricing** | Market asks "does this change anything?" | **The entry window.** Position in the clarity, not the chaos. Full stack on every candidate |
| **3 — Rotation** | Money moves from old winners to new-reality winners | Follow with sized tilts, not wholesale switches |

**Conduct rules:**

1. **Tilt, don't gamble** — no single position sized so a wrong call wrecks the book.
2. **Keep a calm core** — quality holdings and index core are untouchable in the shock window.
3. **Know your exit before you enter** — both stops set on any crisis-window entry.
4. **Accumulate the calm, not the spike** — hedge/metal adds only on pullbacks, never on the shock-day spike.
5. **Shovels, not the barrel** — commodity-shock exposure via services and infrastructure, not spot proxies; the spot gain fades in ~3 months.
6. **Structural, not the pop** — multi-year spending repricings are spread across names; don't chase shock-day pops in the obvious primes.
7. **Know the losers** — while "higher for longer" holds, no new entries in rate-sensitive utilities or real estate.
8. **Watch the hand-off** — if insider buying dries up while retail buying runs 2×+ hot, treat rallies in crowded/expensive names as distribution: hold valid theses, do not add.

**Phase-2 entry checklist:** (a) beneficiary of the *repriced* reality, not the headline spike; (b) full stack passes; (c) sized as a tilt; (d) exit defined before entry. *If it only works while the crisis lasts, it's a trade, not a position — starter size max.*

---

## Discipline rules

- No entry without all three signals confirmed.
- No full-size entry with earnings inside 7 days.
- No chasing a name within 10% of its 52-week high without an explicit momentum case.
- Both stops set before entering. Always.
- A volume spike is the only valid entry trigger. Thesis alone is never enough.
- **The MA is the gatekeeper.** Price below a declining MA = no entry, regardless of story.

---

*Educational reference. Not financial advice. See `DISCLAIMER.md`.*
