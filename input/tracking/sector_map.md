# Sector Map

Authoritative ticker → sector classification for every screened name.

**This file is GENERATED.** `tools/publish.py` derives it from the private tree's
own sector map on every publish; editing it in a clone is fine, but understand it
is a derived artefact upstream, not a hand-maintained one. Two things are removed
in the derivation, and both for the same reason — a classification dictionary that
tracks a live book will otherwise disclose that book:

- **The ticker table is filtered** to names a public clone actually has: the demo
  book in `input/*.example.csv` and the starter list in
  `input/tracking/universe.example.md`. The private map covers whatever its owner
  holds, so shipping it whole would publish the roster, on a lag, forever.
- **The Investable line column reads `none` throughout.** In the private file it
  names the roster vehicle a ROTATION-IN tag should land on. A fresh clone has no
  roster, so `none` is not a redaction here — it is the accurate value, and it
  carries the meaning the column already defines: finding a vehicle becomes that
  run's EXPANSION task.

**Resolution order:** this file → the `Sector` column in `input/tracking/*.md` →
`Unclassified` (reported as a warning on every run).

**A caution on reading the rotation table.** The In/Out columns count member flags,
so a sector holding many names and a sector holding one are not comparable by
count. The radar reads each sector's level and direction from the bellwether table
below; member counts remain only as a breadth measure. **Treat a thin sector's
In/Out count as an anecdote and lean on the gauge column for direction.**

## Bellwether ETFs

One reference ETF per sector. **Measurement-only rules:**

- Bellwethers supply the sector's **level, trend and momentum** in the rotation
  read. Member names still generate their own per-name flags.
- A bellwether is **never** a candidate, never counted in the rotation In/Out
  columns, takes **no RS percentile**, and can never be tagged RS-LEADER — the
  same separation speculatives get. Otherwise XLP breaking out would itself count
  as "Defensive arriving" and pollute the read.
- US-listed lines are chosen deliberately: longest daily history and cleanest
  fetches. These are gauges, not holdings.
- Read by `heartbeat_radar.load_bellwethers()`, which requires this table to keep
  all four columns. Fetch failures on any gauge surface in the radar's
  "Bellwether fetch failures" list.


| Sector | Bellwether | Investable line | Note |
|---|---|---|---|
| AIInfra | DTCR | none | Global X Data Center & Digital Infra — REIT-tilted, approximate for the E&C/power names |
| Agri | MOO | none | VanEck Agribusiness |
| CleanEnergy | ICLN | none | iShares Global Clean Energy; TAN if solar-only read needed |
| Consumer | XLY | none | Consumer Discretionary Select SPDR |
| Defence | ITA | none | iShares US Aerospace & Defense; SHLD = defence-tech tilt |
| Defensive | XLP | none | Consumer Staples Select SPDR |
| Energy | XLE | none | Energy Select SPDR; OIH for the services leg |
| Financials | XLF | none | Matches the the strategic-conviction model XLF signal directly |
| Gold | GDX + GLD | none | Miners + metal, per `input/tracking/universe.md` |
| GrowthSW | IGV | none | iShares Expanded Tech-Software |
| Healthcare | XLV | none | Health Care Select SPDR |
| Index | — | none | Indices are their own bellwethers |
| Japan | EWJ | none | iShares MSCI Japan |
| Materials | XLB | none | Broad; REMX closer for critical metals |
| Mexico | EWW | none |  |
| MegaTech | MAGS | none | Roundhill Magnificent Seven |
| Quantum | QTUM | none | Defiance Quantum & Machine Learning |
| Rail | IYT | none | Transports proxy |
| Semis | SMH | none | VanEck Semiconductor |
| Shipping | BOAT | none | SonicShares Global Shipping |
| Uranium | URA | none | Global X Uranium |
| Utility | XLU | none | Utilities Select SPDR |

*Note on dual keys: a bare ticker and its `.L`-suffixed form may both appear —
this is a lookup map keyed by ticker string, and duplicate keys cannot
double-count the rotation read (counts derive from screened tickers, not map
rows). Keep both rows if your tools spell them differently.*

| Ticker | Sector |
|---|---|
| ABAT | Materials |
| AMAT | Semis |
| AMD | Semis |
| AVAV | Defence |
| AVGO | Semis |
| BWXT | Defence |
| CASHGBP | Cash |
| CNX1.L | Index |
| CVX | Energy |
| FCX | Materials |
| HWM | Defence |
| ICE | Financials |
| LIN | Materials |
| LMT | Defence |
| MP | Materials |
| MSFT | MegaTech |
| NVDA | Semis |
| SILG.L | Gold |
