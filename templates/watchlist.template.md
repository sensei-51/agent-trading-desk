# Watchlist — <sleeve name>

**Paired file: `rules/02_SLEEVE_RULES.md`** — the gate cards (stock and ETF), tiers, sizing, stops and ratchet. That file governs *how much and whether*; this file governs *what*.

**Hierarchy:** `rules/01_METHOD.md` (method) → `rules/02_SLEEVE_RULES.md` (gates & sizing) → this file (candidates). **Stricter rule always wins.**

---

## How to use this file

*A **stateless** list of candidates under monitoring. **No evaluation state lives here** — no status, breakout points, stops, gate results or entry conditions. All of that is produced fresh in the evaluation file on every run, for every symbol below plus every holding in the CSV.*

**A name on this list means: "evaluate me every run."**

| Field | Meaning |
|---|---|
| **Symbol** | Ticker as the radar should resolve it (`.L` suffix for LSE lines) |
| **Name** | Full instrument name |
| **Type** | `Stock` / `ETF` + trading currency |
| **Source** | Where the idea originated, with a date |
| **Thesis** | Why it's on the list — **timeless, no chart state** |

> **Row format matters.** The radar parses rows of the form `| **TICKER** | ...`. Keep the bold ticker in the first cell or the name will not be screened.

> **Tag speculative candidates `SPECULATIVE`** in the Source or Thesis cell — the radar detects the tag and excludes them from RS percentile ranking.

---

## Index / Core Beta

| Symbol | Name | Type | Source | Thesis |
|---|---|---|---|---|
| **EXMPL** | Example Index ETF | ETF USD | Sweep 01 Jan | One-line durable reason this is on the list. No prices, no levels. |

## <Theme 1 — e.g. AI Infrastructure>

| Symbol | Name | Type | Source | Thesis |
|---|---|---|---|---|
| **EXMP2** | Example Co | Stock | Sweep 01 Jan | Durable thesis. |

## <Theme 2 — e.g. Defence>

| Symbol | Name | Type | Source | Thesis |
|---|---|---|---|---|
| | | | | |

## Speculative

*Fixed small stake, no initial stop, score floor ≥ 15. Max 5 concurrent. See the Speculative Tier in `rules/02_SLEEVE_RULES.md`.*

| Symbol | Name | Type | Source | Thesis |
|---|---|---|---|---|
| **EXMP3** | Example Speculative Co | Stock | SPECULATIVE — research note 01 Jan | Catalyst, named and dated. |

---

## Maintenance rules

1. **Promotion from discovery deletes the `input/tracking/universe.md` row.** A name lives in exactly one membership source; two rows double-count it in the rotation read.
2. **Never write evaluation state back here.** If you find a stop level or a gate result in this file, delete it — it is already stale.
3. **Add a `input/tracking/sector_map.md` row for every new ticker**, or it screens as `Unclassified`.
4. **Removing a name is a decision** — log it in `output/ledger/Gate_Ledger.csv` with a `Price_At_Decision`, or you can never score whether dropping it was right.
