# Tracking — Sector-Coverage Backing

*Replaces `input/universe.md` for the sector-rotation-read quorum-backing use
case specifically — see `input/tracking/README.md` for the two-swimlane layout.*

This file holds the **deliberate, named** quorum-backing tickers for thin
sectors — not aspirational candidates, not sweep output.

**There is no cap.** The old "8 names per sector" belonged to the
pre-26-Jul-2026 rotation read, where a sector's direction came from member
counts and stacking a thin sector was how you made it readable. Bellwether ETFs
supply direction now (see the bellwether table in `sector_map.md`), so pool size
no longer buys read quality.

**What survives is a floor of 3, and it is soft.** Since 2026-08-23 `heartbeat_radar.classify()` treats both sides
alike — for a sector of n ≤ 2 members, the floor drops to 1 **and** the
bellwether gauge must CONFIRM the direction. Before that, `in_min` dropped to 1
but `out_min` stayed at 3, so a one- or two-member sector could signal arrival
from its own members and could never signal departure from them.

So the job of this file is narrower than it used to be: **hold a sector at ≥ 3
screened members only if you want its member cluster to carry an exit read
without the bellwether having to agree.** Below three, an exit still reads — it
just needs the gauge to confirm it. Note "screened members" is the live count,
not the row count here: Utility and CleanEnergy screen **1** name each and
Uranium **2**, well below what `sector_map.md` suggests.

Add to `sector_map.md` for every ticker here, or the row screens as
`Unclassified`. Nothing is ever silently trimmed. See `docs/BACKLOG.md` item 23.

| Ticker | Sector | Notes |
|---|---|---|
| UNH | Healthcare | Sector-rotation backing (large-cap US HMO) |
| JNJ | Healthcare | Sector-rotation backing (US pharma) |
| PFE | Healthcare | Sector-rotation backing (US pharma) |
| MRK | Healthcare | Sector-rotation backing (US pharma) |
| UNP | Rail | Sector-rotation backing (US Class I railroad) |
| CSX | Rail | Sector-rotation backing (US Class I railroad) |
| CP  | Rail | Sector-rotation backing (Canadian Class I railroad) |
| BA.L  | Defence | EU/UK Defence (NATO restocking lane) |
| RR.L  | Defence | EU/UK Defence (Rolls-Royce) |
| SAFRY | Defence | EU/UK Defence (Safran) |
