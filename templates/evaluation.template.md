# <Sleeve> Evaluation — YYYY-MM-DD

*Overwritten every run. **All evaluation state lives here** — never in the watchlist or the rules files.*

`Coverage: N/N`

**Tool status:** fundamentals scorer ✅ · chart platform ✅ · strategic conviction ✅ (read live HH:MM) · web ✅
*Any leg unreachable → state it here and label the affected calls INFERRED.*

**Radar:** `Heartbeat_Radar_YYYY-MM-DD.md` (age: N trading days). *Older than 3 → technical leg is stale, say so.*

---

## Market snapshot

Broad index · commodity references · the FX cross that moves your P&L · notable moves vs yesterday.

## Geopolitical update

Top 1–2 active risks. Each rated **STABLE / ELEVATED / CRITICAL**, with the direct impact on held positions named.

## Rotation read

**ROTATION-IN:** <sectors> · **ROTATION-OUT:** <sectors> · **Persistence:** <streak / trend>

**Sleeve implication:** X% of the sleeve sits in ROTATION-OUT sectors, Y% in ROTATION-IN. <Is the cap what blocks leaning in?>

**Investable line per ROTATION-IN sector:** <ticker> → gate card below (**ETF card** where the line is a fund). *If the bellwether table says `none`, that becomes this run's EXPANSION task.*

---

## Action summary

*Short fixed-width fields only. **Never put reasoning in a table cell.***

> **Heading is load-bearing — do not rename.** This 3-column summary and the 8-column
> `## Conviction-ranked action board` below are two different sections. `tools/eval_reviewer.py`
> and `tools/append_gate_ledger.py` bind to the board by heading; when the two headings were
> near-duplicates (`Action board — conviction ranked` / `Conviction-ranked action board`) all
> three consumers silently matched this one and read zero rows for four days.

| Ticker | Px / Value | Signal |
|---|---|---|
| EXMPL | $118 / $12.4K | 🟢 BUY (capped) |
| EXMP2 | $42 / $3.1K | 🟠 WAIT |

### Notes

**EXMPL** — GATE: S 7/7. Trigger $115, filled within 2%. Size = risk ÷ stop distance = N shares, truncated to cap. Score 71 (ACCEL). Rising 50d and 150d, accumulation 1.8. Headroom to cap: $180 — would have bought $1,400 more. Macro: sector ROTATION-IN, 3rd consecutive run.

**EXMP2** — GATE: S fail #5. Earnings in 6 days → binary risk, no full-size entry. Score 64 (RECORD), chart clean. Action: defer to post-print; re-run the card then.

**EXMP5** — GATE: E 8/8. ETF card. Sector ROTATION-IN (2nd run), AUM £340m, spread 0.11%, TER 0.35%, physical, premium +0.2%, top-10 overlap 4% of NAV. Trigger 42.30. Signal-ruled: 150d @ 38.90, no milestone stop. Eligible for the 10% rotation-conditional cap.

**EXMP6** — GATE: E fail #8. ETF card. Passes 1–7, but top-10 overlap is 14% of NAV against an existing line and both track the same index. **Not starter-eligible** — blocked outright, not halved. Action: choose one line or neither.

> **Prefix every gate result `S` (stock card) or `E` (ETF card).** The two cards number their gates differently, and `tools/pnl.py` groups blocked decisions by this string verbatim — unprefixed, two unrelated gates merge into one meaningless hit rate.

---

## Held positions (summary)

*Every holding, four short columns. Reasoning lives in the Notes section above; here it is the trigger level only. **The Action summary above carries the active calls** — sells, BUY-TRIGGERs, stops to set; this section lists every other position with its stop trigger so nothing drops out of coverage between Active and Risk-level.*

| Ticker | Px | Sector | Stop / Trigger |
|---|---|---|---|
| EXMPL3 | £8.40 / £2.1K | Defence | close < £8.00 = 🔴 SELL (150d) |
| EXMPL4 | $250 / $5.0K | MegaTech | close < $220 = 🔴 SELL (cap-ratchet) |
| EXMPL5 (ETF) | 50.30p | Financials | signal-ruled (150d @ 47.50) |

*If a row's column runs wide, it is wrong — the cell must be the level, never the rationale. If a holding has no written trigger, that is the **most important cell in this section.** The format is deliberately terse; **a missing row is the same defect as a missing call.***

---

## Sector X-ray (verbatim from `output/data/xray_latest.md`)

**NAV £<N>** over <H> holdings *(broker export dated YYYY-MM-DD — values are that day's, not today's).* Value is the broker's own sterling conversion per line (`Market Value £`). Sector mapping: `input/tracking/sector_map.md`. **Each █ = 1% of NAV** (bar width 30).

| Sector | Value £ | % NAV | Weights |
|---|---|---|---|
| <SectorA> | <value> | <pct>% | <block> |
| <SectorB> | <value> | <pct>% | <block> |

*Copied verbatim from the X-ray tool output; no added, removed or reordered rows. The X-ray draws weights from holdings only — watchlist names have no NAV weight.*

## Portfolio growth

| Date | NAV £ | Δ | Run |
|---|---|---|---|
| YYYY-MM-DD | <NAV> | — | █ |
| YYYY-MM-DD | <NAV> | <pct>% | ▁ |

<pre>
<sparkline rows>
YYYY-MM-DD … YYYY-MM-DD
</pre>

*Read the chart: which sectors the book leans on and which ROTATION tags the board above should be read against.*

---

## Conviction-ranked action board

*One table per sector, ranked by conviction. **Held names are bolded. Every roster name appears exactly once across the sector tables.** Columns: `Ticker | Px | 150d | OffHigh | RS | YTD | Signal | Note`. **Every gate result is prefixed `S` (stock) or `E` (ETF)** — the two cards number their gates differently, so an unprefixed row is a defect.*

### <SectorA> *(rotation tag — streak / trend — qualifier if any)*

| Ticker | Px | 150d | OffHigh | RS | YTD | Signal | Note |
|---|---|---|---|---|---|---|---|
| **HELD1** | <px> | <150d> | -X.X% | <RS> | <YTD>% | 🟠 HOLD | GATE: <S/E> <x/x>. <one-line reason, no wrapped multi-line reasoning> |
| WATCH1 | <px> | <150d> | -X.X% | <RS> | <YTD>% | 🟤 AVOID | GATE: S fail #N. <one-line reason> |
| BUY1 | <px> | <150d> | -X.X% | <RS> | <YTD>% | 🔵 BUY-TRIGGER | GATE: S 7/7. Trigger > $X vol-confirmed |

### <SectorB> ...

---

## Risk level

🟢 **DEPLOY** — conditions favourable · 🟡 **HOLD** — wait for clarity · 🔴 **DEFENSIVE** — contingency

<One or two sentences on why.>

## Today's recommended action

One paragraph. Specific tickers, specific amounts. **If no action is warranted, say so clearly and explain why** — "nothing to do today because X" is a complete and valid answer.

## Stop loss review

- Positions within **5%** of a known stop
- Large positions (>20% of sleeve NAV) with **no stop set** — *excluding signal-ruled lines*
- **Signal-ruled lines**, listed explicitly as `signal-ruled (150d @ <level>)`, flagged when price approaches that line. *Exempt from the flag above, never from this list — an invisible exemption reads exactly like a forgotten stop.*
- Stops that should be **raised** after a gain, with the suggested new level
- **Round-trip reviews:** every held position flagged `ROUND-TRIP-RISK` — keep/exit call **with a written trigger level**. *A missing row here is a missed mandatory review.*

## Proactive screening

- `EXTENDED` — up >15% from average cost with **no corresponding weight increase** in the live model portfolio
- Individual stocks above median analyst PT by >10%
- Any analyst downgrade in the past 14 days
- Any earnings in the next 14 days
- **ETF overlap:** combined weight of top-10 constituents held elsewhere >10% of sleeve NAV, or two lines tracking one index. *Gate 8 applies at entry; this catches the same duplication assembling itself gradually across separate, individually-legitimate decisions.*

## Pre-entry validation

*Run on anything entered in the past 48 hours or actively recommended now. State every triggered flag with a specific action.*

**Stocks:**

| Flag | Trigger | Status | Action |
|---|---|---|---|
| BINARY RISK | Earnings ≤7D | | full entry / starter / defer |
| AT PEAK | Within 10% of 52w high | | |
| CONSENSUS EXCEEDED | Above consensus PT | | |
| EXTENDED RUN | YTD gain >50% | | |

**ETFs** — two of the stock flags do not exist for a basket. `CONSENSUS EXCEEDED` has no analyst PT to exceed, and `BINARY RISK` has no single earnings date. Replacing them with a blank row would read as a pass; these are the equivalent questions:

| Flag | Trigger | Status | Action |
|---|---|---|---|
| CLUSTER RISK | ≥25% of fund weight reporting ≤7D | | full entry / starter / defer |
| RECONSTITUTION | Index rebalance ≤5 trading days | | |
| AT PEAK | Within 10% of 52w high | | |
| PREMIUM | Outside ±0.5% of NAV (±1.5% ETC) | | |
| OVERLAP | Top-10 held elsewhere >10% of NAV | | **blocked — never starter** |
| EXTENDED RUN | YTD gain >50% | | |

## Phased strategy

- **TICKER** — allocation, trigger price/condition, target date. *(one line)*

## Early watch

2–3 names not held and not watchlisted, with early earnings acceleration or upgrades. Priority to radar-only names flagged `HEARTBEAT` / `AT-BREAKOUT`.

**Do not filter by theme.** Any ROTATION-IN sector is an active theme by definition.

Pre-checks before surfacing: no earnings ≤7D · not within 10% of 52w high · not above consensus · MA not declining. **On breach, defer rather than present as actionable.**

## Expansion

One new name per active macro theme, with entry thesis — **only if risk level is DEPLOY or HOLD**. Same three pre-checks; on breach, present as a watchlist candidate with an entry condition.

---

## Sweep discipline

Discovery in `input/tracking/universe.md` is **not capped** — the per-sector cap of 8 was scaffolding for the pre-26-Jul-2026 rotation read and was retired with it (bellwether ETFs supply sector direction now). **The live constraint is a floor, not a cap, and it is soft:** an OUT read normally needs three leaving members, but a thin sector (n ≤ 2 screened) has the floor dropped to 1 on both the IN and OUT sides provided its bellwether gauge CONFIRMS the direction. Note the count is *screened* members, not `sector_map.md` rows — several sectors are far thinner in practice. State any sector reading on the thin-sector path this run; **"sector full" is never a reason to drop an idea.**

---

## What changed and why

<Short. The delta from the last run, and what caused it.>

---

*Not financial advice. Data verified at time of writing; verify before acting.*
