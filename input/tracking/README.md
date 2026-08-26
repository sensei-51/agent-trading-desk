# Tracking — Tier 0 of the membership model

This directory holds the names the radar screens but the daily evaluation
**does not** evaluate. Tracking is the budget-friendly tier for ideas that
need watching but aren't ready for the gate card.

## Lifecycle

```
YouTube / curated screens / manual research / podcast quote
              │
              ▼
   input/tracking/universe.md          (Tier 0 — radar-only, discovery)
              │
              │ (radar flags something interesting)
              │ (you decide the thesis is strong enough to evaluate)
              ▼
   input/watchlists/<your list>.md     (Tier 1 — full gate card every run)
              │
              │ (gates pass; you buy)
              ▼
   input/*.csv (broker export)         (Tier 2 — held position)
```

Sectors with too few members also need a tracking pool, in a separate
swimlane so it can't be confused with aspirational candidates — see
[`sector-coverage.md`](sector-coverage.md).

## Two swimlanes

| File | Role | Adds noise? |
|---|---|---|
| `universe.md` | Discovery names — anything from an outside source. Promote when warranted; drop when not. | Yes — wipe stale rows regularly. |
| `sector-coverage.md` | Sector-coverage quorum backing. Deliberate, named names per thin sector. **Not** an ideas pool. Narrower since 2026-08-23 — bellwether ETFs supply sector direction, so this file no longer props up the read; it holds a thin sector at ≥3 screened members so its own cluster can carry an exit without the gauge agreeing. Neither file is capped. | No — entries here are intent-stated, kept indefinitely. |

Both files are read by `engine/heartbeat_radar.py` and feed the same radar
screen. The difference is editorial.

## What tracking is NOT

- **Not discovery.** Discovery (the weekly sweep output) belongs in `universe.md` —
  that file is the in-repo noun for ideas that arrive from external research.
- **Not a watchlist.** The gate card is not run. Stop levels are not set.
  The radar flag is a single-line entry in `output/radar/Heartbeat_Radar_<date>.md`, not a
  buy recommendation.
- **Not a sector ETF filer.** Sector coverage is read quorum; entries
  here are "the sector needs these names to read", not "I want exposure".
  Since the bellwether change the phrasing is looser than the mechanism: a
  thin sector *can* read without them, but its exit signal then depends on the
  bellwether confirming. See `sector-coverage.md`.

## `sector_map.md` lives here too

`input/tracking/sector_map.md` is the third file in this directory. Unlike
`universe.md` and `sector-coverage.md`, it is **not a ticker pool** — the
engine's tracking loader skips it specifically so its rows do not double-count
as membership. What it carries:

- **Ticker → sector mapping** for every screened ticker (2-column rows).
  The override for ticker resolution: a row here is authoritative.
- **Per-sector bellwether ETF table** (4-column rows at the top). The gauge
  the sector rotation read corroborates against — also used for the new
  gauge-led fallback in `heartbeat_radar.py` (Change B).

Edit when adding a ticker (any new ticker's sector belongs here) or when the
sector gauge changes (rare). The tracking loader is selective — it does
NOT contribute its rows to the membership pool.

## Convention

- One row per ticker per pool file. Don't list the same name in
  `universe.md` and `sector-coverage.md`.
- Tickers in `universe.md` darkpool in via paste-and-forget; delete the row
  on promotion (to a watchlist) or after several sweeps of no follow-through.
- Tickers in `sector-coverage.md` are kept intentionally; remove only when
  the sector has gained enough own-roster members to read without them.
- All tracking files require a corresponding `sector_map.md` row, or the
  ticker screens as `Unclassified` and produces no sector vote.
