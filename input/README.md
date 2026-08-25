# input/

**Everything in here is yours to edit. Nothing in here is generated.**

**Only the broker CSVs are required.** The other directories are optional and the radar
runs without them.

```
input/
├── *.csv             Broker exports — drop CSVs here          ← REQUIRED
│                      (gitignored)
├── sample.example.csv  Bundled demo book — used only when no
│                      real export is present            (committed)
├── watchlist.md    Tier 1 — candidate registry                 optional
│                      (gitignored) — or watchlist_*.md for splits
├── tracking/        Tier 0 — radar-only coverage               optional
│   ├── README.md             (workflow, swimlanes)
│   ├── universe.md           (discovery — sweep / manual research)
│   ├── sector-coverage.md    (sector-quorum backing)
│   └── sector_map.md         (ticker → sector + bellwether ETFs; reference)
```

See [`tracking/README.md`](tracking/README.md) for the long-term workflow notes; the
short version: a name in `tracking/` is radar-screened but not evaluated by the daily
run. Move it to a watchlist when the radar flag matches a thesis you actually support.

## Broker CSVs — the only thing you have to supply

Drop the CSV in **exactly as the broker exports it.** Don't rename it, don't reformat it,
don't reorder the columns. Every `*.csv` in `input/` is picked up automatically and
the column names are worked out at runtime:

| Wanted | Matched against |
|---|---|
| Ticker | `Symbol`, `Ticker`, `EPIC`, `Instrument Code`, `Code` |
| Name | `Name`, `Investment`, `Description`, `Title`, `Security`, `Holding` |
| Total gain % | `Gain/Loss %`, `Total return %`, `Change (%)`, `Return %`, … |
| Currency | `Market currency`, `Trading currency`, `Currency`, `CCY` |

> **The day-move column is explicitly excluded.** Brokers ship `Day Gain/Loss %` right
> next to `Gain/Loss %`, and `Price +/- today (%)` next to `Change (%)`. Silently picking
> the wrong one turns every gain figure in the report into a one-day move — which reads
> as plausible, which is what makes it dangerous. The bundled `sample.example.csv`
> carries the trap deliberately — `Day Gain/Loss %` sits immediately left of
> `Gain/Loss %`, and a correct run reports the latter.

The sleeve label comes from the filename, so `holdings_isa.csv` reports as `ISA`.

**Rows with no price series** — OEICs, gilts, T-bills, cash — are skipped by design.
They are **counted and named in the run log**, never dropped quietly.

### The three kinds of CSV

| Filename | Means | Committed? | Radar behaviour |
|---|---|---|---|
| `anything.csv` | Your untouched broker export | **no** — gitignored | Real holdings |
| `anything.public.csv` | Real positions scaled to a nominal NAV by `tools/anonymise.py` | yes | Real holdings |
| `anything.example.csv` | Bundled demo book | yes | **Ignored** whenever any of the above is present |

`sample.example.csv` ships with the repo so a fresh clone has a roster and
`atd-daily` runs end to end before you have supplied anything. Eight real tickers
across eight sectors, **invented quantities**, plus a cash line carrying the balance
to the nominal £100,000 sleeve the rules files use in their worked examples. Each
risk line sits near 4% of NAV, inside the 5% Tier-1 cap, so the demo book passes the
repo's own concentration checks rather than warning on every row — a first run should
show you the pipeline working, not a book already in breach.

**The demo book is only ever a fallback.** The moment one real `*.csv` or
`*.public.csv` appears in `input/`, every `*.example.csv` drops out of the roster —
there is no mixing, and no need to delete the demo file. A run that is using it says
`DEMO DATA` at the top of the reports and in the run log.

If the published repo also ships real *positions* — via `*_a.public.csv` /
`*_b.public.csv` or your equivalent — those are the structure of a populated book and
**not recommendations**, see [`DISCLAIMER.md`](../DISCLAIMER.md).

### Publishing your positions

```bash
python3 tools/anonymise.py ~/Downloads/export.csv --ledger output/ledger/Gate_Ledger.csv
```

Scales quantities and cash by one factor across all files so relative weights survive
exactly, drops account-number and client-reference columns, leaves prices and every
percentage untouched, and recomputes value/cost/gain from the rounded quantity so the
arithmetic still reconciles. The scale factor is printed to your terminal and **written
to no file** — anything recording it gives your real NAV back by division.

Then regenerate `output/` from the scaled files. The reports are built from whatever was
in `input/` at the time, so a report generated before you scaled still carries
the real figures.

### How your ticker becomes a price feed ticker

Resolved at runtime, in this order, with the basis for each printed on every run:

1. **Already suffixed** — `ISF.L` is taken as given.
2. **Venue in the instrument name** — `iShares Physical Gold ETC (LSE:SGLN)` → `SGLN.L`.
   The most reliable signal there is, and most brokers emit it.
3. **`sector_map.md`** — a hit settles the question, in the bare form or in whatever
   suffixed form the map carries (`KNT.TO`, `SILG.L`). Listing *both* forms of one
   symbol settles nothing and fails `checks --pre`: they are usually different
   securities on different exchanges.
4. **Priced in sterling** — `GBP`/`GBX` with no other evidence → `.L`.
5. **Otherwise** a bare symbol, flagged `unconfirmed` in the log.

**To override any of it, add a row to `input/tracking/sector_map.md`** with the exact ticker you want.
And if a guess is simply wrong, the fetch catches it: a ticker the price feed doesn't
recognise is retried in its other form before being written off, and the correction is
printed.

## watchlist.md *(optional)*

The canonical Tier-1 candidate registry. One file. Radar screens every ticker in
the registry, the daily evaluation covers them under the roster contract. Copy
`templates/watchlist.template.md` if you want a fresh one — or split into multiple
lists via `watchlist_<theme>.md` (the engine accepts any filename starting with
`watchlist` at the top level of `input/`).

> **Stateless means stateless.** No stops, no breakout points, no gate results, no chart
> state. All of that is produced fresh in the evaluation on every run. If you find a stop
> level in here, delete it — it is already stale.

Rows must be shaped `| **TICKER** | ...`. Keep the bold ticker in the first cell or the
name will not be screened. Bare symbols whose suffixed form appears in `sector_map.md`
take that suffix automatically. Tag speculative names `SPECULATIVE` in any cell or section
heading and they are excluded from the RS percentile ranking.

## sector_map.md *(optional)*

Located at [`tracking/sector_map.md`](tracking/sector_map.md) since 17 Aug 2026.
Holds the **ticker → sector mapping** for every screened name, plus the per-sector
**bellwether ETF table** (the 4-cell block at the top of the file). It is the
**override file for ticker resolution** — an entry here is authoritative. Names
missing from it still screen; they just report as `Unclassified` and take no sector
in the rotation read. **A superset is fine** — inert rows cost nothing.

## tracking/ *(optional — Tier 0 radar-only coverage)*

Three-tier member model since 17 Aug 2026:

| Tier | File | Radar-screened? | Evaluation-coated? |
|---|---|---|---|
| Hold | broker CSVs | yes | yes — full gate card |
| Watchlist | `input/watchlist.md` (or `watchlist_*.md`) | yes | yes — full gate card |
| **Tracking** | `input/tracking/*.md` | yes | **no** — radar flags only |

Two swimlanes today:

- `universe.md` — discovery rows from a fundamentals sweep, YouTube / curated screens /
  podcasts / manual research notes. **Promote-on-improvement** — drop stale
  rows regularly.
- `sector-coverage.md` — sector-rotation quorum backing. Intent-stated, kept until
  the sector has enough own-roster names to read without them.

The radar reads both tracking files; the daily evaluation does **not**. That's the
separation the tier model enforces — gate cards are not run on tracking names, but
the radar flags fire there so promotion is signal-driven, not arbitrary.

**No per-sector cap** — the old cap of 8 was retired 23 Aug 2026 with the
count-based rotation read it served (`docs/BACKLOG.md` item 23). What remains is
a floor of 3 screened members, below which a thin sector's own cluster cannot
carry an exit read without the bellwether confirming; see
[`tracking/sector-coverage.md`](tracking/sector-coverage.md).

Promotion rule: move the row from `tracking/universe.md` to `input/watchlist.md`
and delete the tracking row. **Demotion is the same move in reverse** and is a
legitimate way to cut evaluation cost on names that never action. Two trackers
dual-listed = a momentum calculation bug, same as the old universe.md
double-count failure mode.

See [`tracking/README.md`](tracking/README.md) for the in-repo workflow.

---

## Adding a second sleeve

Drop its export in `input/` and, if it has one, its watchlist as another
`watchlist_<sleeve>.md` in the same `input/`. Picked up automatically; the
sleeve label comes from the broker export filename.

To keep sleeves fully separate instead, `--input-dir` and `--output-dir` (or `TP_INPUT` /
`TP_OUTPUT`) let one checkout serve several portfolios without them ever seeing each
other's data.
