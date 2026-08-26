# Dark-pool capture spec

*Source-agnostic. Written 25 Aug 2026, extracting the retired vendor provider's docstring,
`docs/SMART_MONEY_BOARD.md` §3 and §7, and the parsing behaviour of `tools/darkpool.py` into one
place that belongs to no vendor. Closes `docs/BACKLOG.md` item 6.*

---

## 0. Why this file exists

**D5 (22 Aug 2026) made darkpool a permanent optional overlay** — a layer whose source can be
lost, swapped or paused without breaking a run. That property is only real if the format is
written down somewhere other than one vendor's parser.

On 25 Aug 2026 the only vendor parser was removed. **This file is what that removal had to
leave behind.** Everything below is what a new darkpool provider needs in order to exist, and
what the seven captures already in `input/capture/` mean now that nothing on disk parses
them.

Nothing here is a rule about what darkpool *means*. The rules live in `rules/`, the rendering
lives in `tools/darkpool.py`, and no gate reads either — by decision, permanently.

---

## 1. Ingestion is `browser`, and that is not a detail

Retail options/dark-pool platforms generally prohibit unattended automated access. Where
that is so, `ingestion: "browser"` is the only honest mode:

> A human reads the logged-in screen and writes a capture file, **or** an agent does so via
> the user's own logged-in session at the user's direct instruction each time — acting as the
> subscription holder's own hands, never as a background scraper. Either way the provider
> only ever parses a capture file that already exists.

**A conforming darkpool provider contains no network code.** Not "no scraping today" — no HTTP
client, no browser driver, no credentials, no session handling. The subscription at risk
belongs to the user, not to the repo. A scraper labelled `"fetch"` is the failure this
clause exists to prevent.

`providers/contracts.py` enforces the consequence: `ingestion` of `browser` or `file`
**must** declare `max_age_days`, because an unbounded capture is quoted as live forever.

---

## 2. The capture file

**Path:** `input/capture/darkpool_<YYYY-MM-DD>.md` (under `$TP_INPUT` when set).

> **The date in the filename is the SESSION date — the trading day the data describes — not
> the day you captured it.** A Friday session captured on Saturday and read on Monday is
> `darkpool_<Friday>.md`. Getting this backwards makes staleness unmeasurable.

```markdown
# Darkpool capture — 2026-08-20
source: <vendor and screens, free text>
read_at: 2026-08-21T07:05:00Z
method: side_filter=buy_side; trade_types=call,put; index_excluded=no; min_premium=0

## Market
pct_bullish: 36
call_premium: 3.0B
put_premium: 5.3B
label: Bearish

## Tickers
| ticker | pct_bullish | call_premium | put_premium | trades |
|---|---|---|---|---|
| GLD | 86 | 113M | 18M | |
| URA | 100 | 84K | 0 | 1 |
| PLTR | | | | |
```

### Header — key/value lines before the first `##`

| Key | Required | Meaning |
|---|---|---|
| `source` | recommended | Vendor and which screens. Free text; travels into `notes`. |
| `read_at` | **yes** | ISO8601, when you looked. Staleness fires on this. Absent → file mtime is used and a note says so, which reads *younger* than the truth. |
| `method` | **yes** | The convention behind every number below. Absent → provider returns `PARTIAL`. |

### `## Market` — the whole-book summary

Keys: `pct_bullish`, `call_premium`, `put_premium`, `label`. All optional; the section may
be omitted entirely. `pct_bearish` is derived, never written.

### `## Tickers` — one row per ticker looked at

Columns in order: `ticker`, `pct_bullish`, `call_premium`, `put_premium`, `trades`.
A header row (`ticker` or `symbol`) and a `|---|` separator row are skipped. `trades` is
optional.

> **A row with a ticker and nothing else is a zero-premium observation — "I looked, there
> was no darkpool."** That is meaningfully different from the ticker being absent, which means
> "not looked at." Preserve the distinction; it is the only way an empty result is
> distinguishable from an unfinished capture.

---

## 3. Parsing conventions

**Money.** Optional leading `+`/`-`; optional `$`, `£` or `€`; commas stripped; optional
`K`/`M`/`B` suffix, case-insensitive. `-`, `—`, `n/a`, `N/A` and empty all parse to `None`.
So `$113M`, `113000000`, `1.4M`, `84K`, `967K` are all valid. **Everything is stored in the
`_usd` fields regardless of the symbol typed** — if your source quotes another currency,
say so in `method` and convert at capture time.

**Percentages.** A trailing `%` is stripped. `98` and `98%` are the same.

**Derivation and validation:**

- `premium_usd` = `call_premium` + `put_premium`, treating `None` as zero.
- `pct_bullish` omitted but premiums present → derived as `call / (call + put) × 100`, 1dp.
- `pct_bearish` = `100 - pct_bullish`, 1dp. Never captured directly.
- `pct_bullish` outside `0–100` → **the row is dropped** and a warning is added to `notes`.
  A malformed row must not enter the book silently.

---

## 4. The provider return shape

A darkpool provider is a whole-book leg: it exposes `load(ctx)` and returns one dict for the
entire capture. `ctx` may carry `session_date` to request one specific session; absent that,
the provider takes the newest capture on disk.

| Key | Type | Notes |
|---|---|---|
| `status` | `"OK"` \| `"PARTIAL"` \| `"FAIL"` \| `"NONE"` | See the status ladder below |
| `session_date` | `"YYYY-MM-DD"` | The session described. `None` when absent |
| `read_at` | ISO8601 | When it was captured |
| `method` | `dict` \| `None` | `{"raw": "<the whole line>", "<k>": "<v>", …}` — the `k=v` pairs split on `;` **plus** `raw` kept verbatim. Flat strings, not typed values |
| `market` | `dict` \| `None` | `pct_bullish`, `pct_bearish`, `call_premium_usd`, `put_premium_usd`, `label` |
| `tickers` | `dict` | `{TICKER: {...}}`, see below |
| `notes` | `list[str]` | Warnings, provenance, what was parsed |

Each ticker entry:

```python
{"premium_usd": 131_000_000,      # call + put, the sort key and the floor test
 "call_premium_usd": 113_000_000,
 "put_premium_usd":   18_000_000,
 "pct_bullish": 86,
 "pct_bearish": 14,               # derived
 "trade_count": None}             # int or None
```

> **`call_premium_usd` and `put_premium_usd` are load-bearing.** `tools/darkpool.py` renders them
> as the Calls and Puts columns. A provider that returns only `premium_usd` and `pct_bullish`
> parses cleanly and renders two empty columns.

**The status ladder:**

| Status | When |
|---|---|
| `OK` | A capture was found, with `method` and at least one ticker row |
| `PARTIAL` | Capture found but `method` missing, **or** no ticker rows (market summary only) |
| `NONE` | No capture file at all — the leg renders **ABSENT**, which is the honest state, not a failure |
| `FAIL` | Reserved. A darkpool provider that cannot read its own capture should say so in `notes` and return `PARTIAL` or `NONE` rather than inventing a failure the fallback machinery will act on |

`method` is not optional and degrading to `PARTIAL` is the point: **"86% bullish" computed
over buy-side premium with index names included is a different quantity from the same figure
computed over all prints.** Pooling two captures with different conventions silently corrupts
anything later calibrated on them. Record the convention with the data, every time — and if
it is missing, say the number is not poolable rather than guessing which convention produced
it.

---

## 5. The significance floor

**`SIGNIFICANCE_FLOOR_USD = 500_000`** — aggregate premium per ticker. Below it the read is
**`THIN`**: *not bullish, not bearish, not enough money to constitute an observation.*

The evidence, from the 20 Aug 2026 session:

- **URA** rendered **"100% bullish"** on a single **$84K** print —
- in the same table as **GLD**'s 86% on **$131M**. Same colour, unrelated meaning.
- Meanwhile **CCJ** carried **$1.4M of 97.9% bearish** darkpool — sixteen times URA's premium,
  same theme, opposite direction. A naïve read had uranium turning bullish. It was not.

**Any consumer that reads `pct_bullish` without reading `premium_usd` will be wrong roughly
whenever it matters least.**

> **The floor is not a property of the data and no provider may apply it.** A provider
> reports what was on the screen. The floor is a *parameter of this spec*, applied by the
> consumer, so that it can be recalibrated without re-capturing anything.

It lives as a constant in one consumer, `tools/darkpool.py`. The second copy went with
`tools/darkpool_backfill.py` when that was deleted (25 Aug 2026), so the two-constants-in-sync
problem of `docs/BACKLOG.md` item 10 is gone. **The other half of item 10 is not:** this is a
rule living in a reporting script rather than in `rules/` with the other bars. Naming it here
is a stopgap, not the fix.

---

## 6. Staleness

**The check fires on `read_at` — when you looked — never on `session_date`.** A fortnight-old
session read this morning is current information about a fortnight ago; this morning's
session read a fortnight ago is not information at all.

The bound is the provider's own `max_age_days`, and it is a judgement about capture cadence,
not about the data. The removed vendor provider used **4** with this reasoning, which is
worth keeping: *"Four days, not two: a Friday session captured Saturday and read on Monday is
three days old and perfectly current. Five would let a whole dead week be quoted as live."*

`tools/darkpool.py` renders `⚠️ STALE (Nd > Nd)` when exceeded. It does not suppress the data —
a stale reading clearly labelled is usable; a stale reading labelled OK is not.

---

## 7. What the consumer does with it

Documented here so a new provider knows which fields are actually read.
`tools/darkpool.py` → `output/data/darkpool_<date>.md`:

- Rows sorted by `premium_usd`, descending.
- `premium_usd < SIGNIFICANCE_FLOOR_USD` → **`THIN`**, and no direction is stated.
- Otherwise: `pct_bullish >= 60` → **bullish**; `<= 40` → **bearish**; between → **mixed**;
  `None` → `—`.
- Tickers held in the broker CSV are marked ✅.
- `method["raw"]` is printed verbatim under the header; when `method` is absent the renderer
  prints **"unrecorded — do not pool with another capture"** in its place.

---

## 8. Capture procedure — source-agnostic

1. **Market summary first.** Whole-market sentiment and both leaderboards, if the platform
   has them. One page read.
2. **Per-ticker second.** Filter to one ticker at a time and record what the platform's own
   sentiment header recomputes for it. *Expect the filter to be awkward* — the removed
   vendor's was a checkbox autocomplete where comma-separated pasting silently did not parse.
   Whatever the quirk is on your source, write it in the provider's docstring, not here.
3. **Record the convention in `method` while you are looking at it.** Which side filter,
   which contract types, whether index names are excluded, any minimum premium. Not
   afterwards from memory.
4. **Write the file, named for the session date.** `input/capture/` is gitignored and never
   published.
5. **Rows for tickers with no darkpool stay in, empty.** See §2.

---

## 9. Limits inherent to options-derived darkpool

These are properties of the data class, not of any vendor. A replacement source will have
them too, and the reason D5 declined to make this leg a backbone is here:

- **Coverage is structurally poor on the names this sleeve actually trades.** 8 of 10
  backfilled decisions read `THIN`. Darkpool is blind on small caps, thinly-followed
  names and quiet UK lines. **A backbone cannot abstain on the majority of the book; an
  overlay can.**
- **No LSE-native darkpool.** Every GBP line is read through a US twin — a proxy, and it must be
  labelled one on every row where it is used.
- **End-of-day only.** A pre-market run reads yesterday's session.
- **Direction is measured, not interpreted.** The contract type is fact — a put is a put. The
  *initiating side* is inferred by the platform from where the print landed against the
  bid/ask, and a bought call may be a hedge against a short or one leg of a spread priced
  separately. Observed 20 Aug 2026: **SLV showed $28M of calls against $18M of puts while the
  single largest print was a $12M December put.** Irreducible from this data. **Report the
  measurement; let the rules decide what it means.**
- **Stateless by design.** No darkpool history is persisted. To see change, capture two dates.

---

## 10. The GBP→US twin table

*Rehomed here 25 Aug 2026 from a deleted one-off scoring script. This is the
destination `docs/BACKLOG.md` item 9 named — "move `TWIN` out into a shared location, the
capture spec of item 6". It was the only twin table in the repo and it is 46 entries of
hand-checked work; it does not get to die with the script that happened to hold it.*

LSE lines carry no US darkpool. Their US twin is a **proxy, not the same instrument**,
and every row sourced this way must be labelled *"via `<twin>`"* so nobody later reads it as
a direct measurement.

> **A key that is ABSENT is worse than a key mapped to `None`.** A lookup should only report
> "no US twin" for keys that are *in* the table. An LSE line missing entirely falls through,
> gets queried against a US capture under its own ticker, finds nothing, and is recorded as
> "no darkpool" — **indistinguishable from a name that was checked and genuinely had none.**
> Every LSE line in the roster belongs here, mapped or explicitly `None`.

**50 entries · 45 mapped · 5 explicit `None` · 26 distinct targets.**

> **This table is READ BY CODE.** `tools/darkpool.py` parses the rows below to resolve GBP
> holdings to their US twins, the same way seven modules read `input/tracking/sector_map.md`.
> Keep it one row per line, `| LSE line | Twin | Tier | Note |`, with `—` in the Twin column
> for a line that has none. Prose outside the table is not parsed — **an entry that is only
> described in a sentence does not exist as far as the code is concerned.**

**Tiers, weakest last:**

| Tier | Means |
|---|---|
| `index` | Direct index equivalent — the twin is the same exposure, not a proxy |
| `gauge` | Sector-gauge proxy — reads the sector's declared bellwether, never the vehicle's own book |
| `single` | UK single stock read through a US sector ETF. **Weakest tier: sector context only, never a read on the name** |
| `none` | No usable twin. Present *precisely so the gap is explicit* — see the rule above |

| LSE line | Twin | Tier | Note |
|---|---|---|---|
| `BTEK.L` | `IBB` | index |  |
| `CNX1.L` | `QQQ` | index |  |
| `CUKX.L` | `EWU` | index | FTSE 100 tracker, as ISF.L |
| `EQQU.L` | `QQQ` | index |  |
| `GIGB.L` | `GDX` | index |  |
| `IJPN.L` | `EWJ` | index |  |
| `ISF.L` | `EWU` | index |  |
| `IUCD.L` | `XLY` | index |  |
| `IUCS.L` | `XLP` | index | iShares S&P 500 Consumer Staples — same index family, not a proxy |
| `IUES.L` | `XLE` | index |  |
| `IUUS.L` | `XLU` | index | same iShares S&P 500 sector family as IUES/IUCS/IUCD — XLU is the same index, not a proxy |
| `MINE.L` | `COPX` | index | iShares Copper Miners against Global X Copper Miners — different provider and index, same exposure, as `CUKX.L`→`EWU`. ⚠️ `COPX` shares `SIL`'s problem: outside the daily sweep, so a `Copper` split would have a gauge the overlay cannot read (BACKLOG 9.2) |
| `QQQ3.L` | `QQQ` | index | 3x leveraged ETP against the 1x — right direction, never the right magnitude |
| `QQQA.L` | `QQQ` | index |  |
| `SEMI.L` | `SMH` | index |  |
| `SGLN.L` | `GLD` | index |  |
| `SILG.L` | `SIL` | index |  |
| `SPAG.L` | `MOO` | index |  |
| `SSLN.L` | `SLV` | index |  |
| `UIFS.L` | `XLF` | index |  |
| `XDEW.L` | `RSP` | index |  |
| `XLVP.L` | `XLV` | index |  |
| `ASWC.L` | `ITA` | gauge | NOT an index fund: a Defence sector fund, though sector_map.md files it under Index. That misclassification inflates Index breadth and understates Defence — fix the map, not just this line |
| `CHG.L` | `ITA` | gauge | sector gauge — Defence; reads the sector, never the vehicle's own book |
| `DFEU.L` | `ITA` | gauge | sector gauge — Defence; reads the sector, never the vehicle's own book |
| `DFND.L` | `ITA` | gauge | sector gauge — Defence; reads the sector, never the vehicle's own book |
| `DRON.L` | `ITA` | gauge | sector gauge — Defence (drones); reads the sector, never the vehicle's own book |
| `FWRG.L` | `ACWI` | gauge | global all-world equity; ACWI is the same exposure. Often reads THIN, which is the honest answer. Do NOT map to SPY — a ~60%-US proxy returns a confident US-only read for a global fund |
| `IHCU.L` | `XLV` | gauge | sector gauge — Healthcare; reads the sector, never the vehicle's own book |
| `IKOR.L` | `SMH` | gauge | sector gauge — Semis; reads the sector, never the vehicle's own book |
| `INFR.L` | `XLU` | gauge | sector gauge — Utility; reads the sector, never the vehicle's own book |
| `INRG.L` | `ICLN` | gauge | sector gauge — CleanEnergy; reads the sector, never the vehicle's own book |
| `ISPY.L` | `IGV` | gauge | sector gauge — GrowthSW, the bucket `sector_map.md` files it under; reads the sector, never the vehicle's own book. ⚠️ Cyber is sold on security budgets and compliance cycles, not hyperscaler capex, so `IGV` is the *declared bellwether* rather than the accurate exposure. `CIBR` would read the theme properly and is the twin to use if a `Cyber` bucket is ever split out |
| `IWFQ.L` | `QUAL` | gauge | same iShares MSCI quality factor but USA-only against this line's World, ~70% overlap by weight. Factor direction, not geography |
| `JEDG.L` | `ITA` | gauge | sector gauge — Defence; reads the sector, never the vehicle's own book |
| `NUCG.L` | `URA` | gauge | sector gauge — Uranium; reads the sector, never the vehicle's own book |
| `QANT.L` | `QTUM` | gauge | sector gauge — Quantum; reads the sector, never the vehicle's own book |
| `ROBG.L` | `IGV` | gauge | sector gauge — GrowthSW; reads the sector, never the vehicle's own book |
| `URNG.L` | `URA` | gauge | sector gauge — Uranium; reads the sector, never the vehicle's own book |
| `URNU.L` | `URA` | gauge | sector gauge — Uranium; reads the sector, never the vehicle's own book |
| `VPNG.L` | `DTCR` | gauge | sector gauge — AIInfra; reads the sector, never the vehicle's own book |
| `YCA.L` | `URA` | gauge | sector gauge — Uranium; reads the sector, never the vehicle's own book |
| `BA.L` | `ITA` | single | BAE Systems — NOT Boeing. A US sector ETF reads the US sector, never a UK company's own book |
| `KNT.TO` | `GDX` | single | K92 Mining, TSX. A miner, so the gauge is `GDX` (the Gold bucket's miner leg) not `GLD`. Sector context only, never a read on the name. ⚠️ **NOT CURRENTLY PARSED** — `tools/darkpool.py` `_TWIN_ROW` hardcodes `\.L`, so this row is invisible to the code and `KNT.TO` still falls through to the no-darkpool ambiguity this table exists to prevent. Widen the regex to `[A-Z0-9.]+` before relying on it |
| `RR.L` | `ITA` | single | Rolls-Royce Holdings. Sector context only, never a read on the name |
| `ALUM.L` | — | none | WisdomTree Aluminium ETC — a commodity price, not an equity basket, so `XLB` is the same confident wrong read it would be for `COMM.L`. `AA` is one producer's own book, weaker than even the `single` tier for a metal price. Filed `Materials` in `sector_map.md`, which the watchlist already flags as its weakest mapping |
| `COMM.L` | — | none | filed Materials, but a commodity basket is not US materials equities, and sector_map.md adopts no ETF line for Materials at all. XLB would be a confident wrong read |
| `INXG.L` | — | none | UK index-linked gilts. TIP is the nearest US instrument but it is another country's inflation and rate curve — not a twin in any useful sense |
| `PRTC.L` | — | none | UK-specific |
| `WISE.L` | — | none | UK-specific |

> **Known gap:** `SIL` — `SILG.L`'s twin — sits outside the sweep that the daily darkpool render
> covers, so a `Silver` sector split would have a gauge the overlay cannot read.
> `docs/BACKLOG.md` item 9.2.
