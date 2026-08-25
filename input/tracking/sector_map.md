# Sector Map

Authoritative ticker → sector classification for **every** screened name: holdings,
watchlist candidates and discovery names alike.

Created 26 Jul 2026, when `input/tracking/universe.md` became discovery-only. The `@Sector` tags had
been living inside the membership list, so stripping holdings and watchlist names out of
that file would have lost their classification. Holdings and watchlist names appear in no
other tagged file, which is why this one exists.

**Resolution order:** this file → the `Sector` column in `input/tracking/universe.md` → `Unclassified`
(reported as a warning on every run).

**A caution on reading the rotation table.** The In/Out columns count member flags, so a
sector with 34 names and a sector with 1 are not comparable by count — Gold (34) and Semis
(29) dominate; Healthcare and Rail rest on a single stock each. Since 26 Jul 2026 the radar
reads each sector's own level and direction from the bellwether table below (backlog #1,
done); the member counts remain as a breadth measure. **Treat thin sectors' In/Out counts
as anecdotes and lean on the gauge column for direction.**

## Bellwether ETFs (added 26 Jul 2026)

One reference ETF per sector. **Measurement-only rules:**

- Bellwethers supply the sector's **level, trend and momentum** in the rotation read. Member
 names still generate their own per-name flags.
- A bellwether is **never** a candidate, never counted in the rotation In/Out columns, takes
 **no RS percentile**, and can never be tagged RS-LEADER — same separation as speculatives.
 Otherwise XLP breaking out would itself count as "Defensive arriving" and pollute the read.
- US-listed lines chosen deliberately: longest daily history and cleanest Yahoo fetches.
 These are gauges, not GBP-preference holdings.
- **Wired into `heartbeat_radar.py` since 26 Jul 2026** (`load_bellwethers()`). Fetch
 failures on any gauge surface in the radar's "Bellwether fetch failures" list.

The **Investable line** column is the bridge from a rotation signal to a buyable ticker:
when a sector tags ROTATION-IN, the evaluation looks up this column and runs that vehicle
through the gate card — the rotation call must land on a ticker, not a sector name. "none"
means the roster carries no vehicle: finding one becomes that run's EXPANSION task.

| Sector | Bellwether | Investable line | Note |
|---|---|---|---|
| AIInfra | DTCR | VPNG.L ; VRT, STRL, AGX stocks | Global X Data Center & Digital Infra — REIT-tilted, approximate for the E&C/power names. VPNG.L is DTCR's UCITS GBp twin, same tilt caveat |
| Agri | MOO | SPAG.L | VanEck Agribusiness |
| CleanEnergy | ICLN | INRG.L ; NXT stock | iShares Global Clean Energy; TAN if solar-only read needed. INRG.L is ICLN's UCITS GBp twin |
| Consumer | XLY | IUCD.L ; TXRH roster, RSI stocks | Consumer Discretionary Select SPDR. IUCD.L = S&P 500 sector UCITS twin, USD line on LSE |
| Defence | ITA | DFEU.L ; DRON.L/JEDG.L for drones; CHG.L roster stock | iShares US Aerospace & Defense; SHLD = defence-tech tilt |
| Defensive | XLP | IUCS.L ; CHD stock | Consumer Staples Select SPDR. IUCS.L = S&P 500 sector UCITS twin, USD line on LSE |
| Energy | XLE | IUES.L ; CVX stock | Energy Select SPDR; OIH for the services leg. IUES.L = S&P 500 sector UCITS twin, USD line; SPOG.L if the E&P tilt is wanted instead |
| Financials | XLF | UIFS.L ; PNC/WISE.L stocks | Matches the the strategic-conviction model XLF signal directly |
| Gold | GDX + GLD | SGLN.L + SSLN.L | Miners + metal, per `input/tracking/universe.md` |
| GrowthSW | IGV | ROBG.L | iShares Expanded Tech-Software |
| Healthcare | XLV | PRTC.L stock — no ETF line adopted (IUHC USD line exists, unverified) | Health Care Select SPDR |
| Index | — | ISF.L · CNX1.L · EQQU.L · XDEW.L (all roster) | Indices are their own bellwethers. Broad US/UK market beta only — a single-country, factor, leveraged or fixed-income vehicle belongs in its own bucket (see Japan, added 22 Aug 2026) |
| Japan | EWJ | IJPN.L (roster) | iShares MSCI Japan. Split from Index 22 Aug 2026: a single-country bet was sitting in a bucket that has no gauge, so member composition alone drove its read. One member — treat the In/Out count as an anecdote and lean on the gauge, per the caution above |
| Materials | XLB | LIN stock — no ETF line adopted (SXLB USD line exists, unverified) | Broad; REMX closer for critical metals |
| MegaTech | MAGS | via index lines (CNX1.L/EQQU.L/XDEW.L) | Roundhill Magnificent Seven |
| Quantum | QTUM | QANT.L — speculative territory | Defiance Quantum & Machine Learning |
| Rail | IYT | NSC stock — structurally stock-only, no pure-rail ETF exists | Transports proxy |
| Semis | SMH | SEMI.L ; IKOR.L | VanEck Semiconductor |
| Shipping | BOAT | INSW/ESEA stocks — structurally stock-only: no UCITS shipping ETF exists (last one closed 2014; BOAT is US-only, PRIIPs-blocked) | SonicShares Global Shipping |
| Uranium | URA | URNU.L · NUCG.L · URNG.L · YCA.L | Global X Uranium |
| Utility | XLU | INFR.L ; UTL stock | Utilities Select SPDR |

*Note on dual keys: a bare ticker and its `.L`-suffixed form may both appear — this is a
lookup map keyed by ticker string, and duplicate keys cannot double-count the rotation read
(counts derive from screened tickers, not map rows). Keep both rows if your tools spell them
differently.*

| Ticker | Sector |
|---|---|
| AAPL | MegaTech |
| ABAT | Materials |
| ACHR | Defence |
| ADI | Semis |
| ADM | Agri |
| AEM | Gold |
| AFRM | Financials |
| AG | Gold |
| AGI | Gold |
| AGX | AIInfra |
| ALAB | Semis |
| ALUM.L | Materials |
| AMAT | Semis |
| AMD | Semis |
| AMKR | Semis |
| AMZN | MegaTech |
| ANDE | Agri |
| ANET | Semis |
| ARIS.TO | Gold |
| ASML | Semis |
| ASWC.L | Defence |
| AU | Gold |
| AUGO | Gold |
| AVAV | Defence |
| AVGO | Semis |
| B | Gold |
| B5M5KY1 | Index |
| B62H2K4 | CleanEnergy |
| BA.L | Defence |
| BETA | Defence |
| BLK | Financials |
| BRDXDH2 | Bonds |
| BSGQ3Y2 | Cash |
| BSGQBJ3 | Cash |
| BSGQN31 | Cash |
| BTG | Gold |
| BTJTP27 | Bonds |
| BWXT | Defence |
| CASHGBP | Cash |
| CCJ | Uranium |
| CDE | Gold |
| CEG | AIInfra |
| CGAU | Gold |
| CGG.TO | Gold |
| CHD | Defensive |
| CHG.L | Defence |
| CLBT | GrowthSW |
| CNX1.L | Index |
| COMM.L | Materials |
| CP | Rail |
| CRDO | Semis |
| CRML | Materials |
| CRUS | Semis |
| CSX | Rail |
| CUKX.L | Index |
| CVX | Energy |
| DE | Agri |
| DELL | Semis |
| DFEU.L | Defence |
| DPM.TO | Gold |
| DRNZ | Defence |
| DRON.L | Defence |
| DSV.TO | Gold |
| DT | GrowthSW |
| EGO | Gold |
| EME | AIInfra |
| ENB | Energy |
| EQIX | AIInfra |
| EQQU.L | Index |
| EQX | Gold |
| ESEA | Shipping |
| ESLT | Defence |
| EXFY | GrowthSW |
| FCEL | CleanEnergy |
| FCX | Materials |
| FFIV | Semis |
| FNV | Gold |
| FSM | Gold |
| FWRG.L | Index |
| GEV | AIInfra |
| GIGB.L | Materials |
| GLW | Semis |
| GMIN.TO | Gold |
| GOOGL | MegaTech |
| HEI | Defence |
| HL | Gold |
| HUBB | AIInfra |
| HWM | Defence |
| IAG | Gold |
| IBKR | Financials |
| ICE | Financials |
| IHCU.L | Healthcare |
| IJPN.L | Japan |
| IKOR.L | Semis |
| INFR.L | Utility |
| INRG.L | CleanEnergy |
| INSW | Shipping |
| INTC | Semis |
| INXG.L | Bonds |
| IONQ | Quantum |
| ISF.L | Index |
| ISPY.L | GrowthSW |
| IUCD.L | Consumer |
| IUCS.L | Defensive |
| IUES.L | Energy |
| IUUS.L | Utility |
| IWFQ.L | Index |
| JCI | AIInfra |
| JEDG.L | Defence |
| JNJ | Healthcare |
| KEYS | Semis |
| KGC | Gold |
| KLAC | Semis |
| KNT.TO | Gold |
| KTOS | Defence |
| LEU | Uranium |
| LIN | Materials |
| LLY | Healthcare |
| LMT | Defence |
| LNG | Energy |
| LOAR | Defence |
| LRCX | Semis |
| LUG.TO | Gold |
| MCHP | Semis |
| META | MegaTech |
| MINE.L | Materials |
| MOS | Agri |
| MP | Materials |
| MRK | Healthcare |
| MSFT | MegaTech |
| MTSI | Semis |
| MU | Semis |
| NBIS | AIInfra |
| NEO.TO | Materials |
| NFLX | MegaTech |
| NGD | Gold |
| NOW | GrowthSW |
| NSC | Rail |
| NTAP | Semis |
| NTNX | GrowthSW |
| NUCG.L | Uranium |
| NVDA | Semis |
| NVMI | Semis |
| NXT | CleanEnergy |
| OKE | Energy |
| OKTA | GrowthSW |
| ONDS | Defence |
| OR | Gold |
| ORCL | GrowthSW |
| ORLA | Gold |
| PAAS | Gold |
| PFE | Healthcare |
| PLTR | GrowthSW |
| PM | Defensive |
| PNC | Financials |
| PRTC.L | Healthcare |
| QANT.L | Quantum |
| QBTS | Quantum |
| QQQ | Index |
| QQQ3.L | Index |
| QQQA.L | Index |
| QUBT | Quantum |
| RCAT | Defence |
| RGLD | Gold |
| RGTI | Quantum |
| ROBG.L | GrowthSW |
| RR.L | Defence |
| RSI | Consumer |
| SAFRY | Defence |
| SCHW | Financials |
| SEMI.L | Semis |
| SGLN.L | Gold |
| SILG.L | Gold |
| SIMO | Semis |
| SLS | Materials |
| SMCI | Semis |
| SNDK | Semis |
| SPAG.L | Agri |
| SPCX | Defence |
| SPY | Index |
| SSLN.L | Gold |
| SSRM | Gold |
| STRL | AIInfra |
| STX | Semis |
| TENB | GrowthSW |
| TER | Semis |
| TEVA | Healthcare |
| TFPM | Gold |
| TSLA | MegaTech |
| TXG.TO | Gold |
| TXN | Semis |
| TXRH | Consumer |
| UAVS | Defence |
| UCTT | Semis |
| UIFS.L | Financials |
| UMAC | Defence |
| UNH | Healthcare |
| UNP | Rail |
| URNG.L | Uranium |
| URNU.L | Uranium |
| UROY | Uranium |
| UTL | Utility |
| VICR | Semis |
| VPNG.L | AIInfra |
| VRT | AIInfra |
| VST | AIInfra |
| WDO.TO | Gold |
| WILC | Agri |
| WISE.L | Financials |
| WPM | Gold |
| XDEW.L | Index |
| XLVP.L | Healthcare |
| XOM | Energy |
| YCA.L | Uranium |
