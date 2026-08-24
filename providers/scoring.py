#!/usr/bin/env python3
"""
scoring.py — primitives shared by any provider that builds a pillar composite.

Extracted from tools/fundamentals.py so a provider does not have to import the
orchestrator that calls it (which would be circular), and so a third-party
provider can reuse the banding maths without copying it. Behaviour is
byte-for-byte the same as before the move; this is a relocation, not a rewrite.
"""

_KNOWN_FUND_VEHICLES = {
    # London UCITS ETF wrappers — LSE lines whose underlying is a US fund/ETF
    # and whose the curated source URL pattern has no per-ticker page. Listed in
    # `input/tracking/sector_map.md`'s bellwether + `Investable line` table.
    "EQQU.L", "XLVP.L", "XLVP", "SPAG.L", "IJPN.L", "CNX1.L", "UIFS.L",
    "GIGB.L", "GIGB", "XDEW.L", "IUCD.L", "IUCS.L", "IUES.L", "IHCU.L", "IUUS.L",
    # Global X Silver Miners UCITS wrapper — curated returned score 0
    # "Insufficient Data" with status OK for it (head-to-head, 18 Aug 2026),
    # which is a fund wearing a stock row. Both spellings, like QQQ3.
    "SILG.L", "SILG",
    # NASDAQ-100 3x leveraged ETP (WisdomTree). Both spellings: `input/ii.csv`
    # carries the bare form while the roster and `sector_map.md` carry the `.L`
    # line, and it is the `.L` form that reaches this call — so the bare-only
    # entry never fired the short-circuit and the row FAILed on a 404 every run
    # (20, 21, 22 Aug 2026).
    "QQQ3.L", "QQQ3",
    # LSE-listed ETF / ETC wrappers added to `input/watchlist.md` on 22 Aug
    # 2026. Each verified against the price feed as a fund wrapper rather than
    # an operating company, and each 404s on the curated source by design; together
    # they were 8 of the 9 FAIL rows on the 22 Aug run.
    "SGLN.L", "SGLN",   # iShares Physical Gold ETC
    "URNG.L", "URNG",   # Global X Uranium UCITS ETF (Acc)
    "ROBG.L", "ROBG",   # L&G ROBO Global Robotics and Automation UCITS ETF
    "ALUM.L", "ALUM",   # WisdomTree Aluminium ETC
    "ISPY.L", "ISPY",   # L&G Cyber Security UCITS ETF
    "SEMI.L",           # iShares MSCI Global Semiconductors UCITS ETF (Acc)
    "ISF.L",            # iShares Core FTSE 100 UCITS ETF (Dist)
    "MINE.L",           # iShares Copper Miners UCITS ETF (Acc)
    # The last three are deliberately `.L`-only. The bare-spelling convention
    # exists for tickers that reach us in either form (QQQ3, XLVP, GIGB, SILG);
    # these eight only ever enter the roster from `watchlist.md` as `.L` lines,
    # and `SEMI` / `ISF` / `MINE` are generic enough as bare strings to risk
    # short-circuiting a real equity row. The set is explicit by design.
    # UK `nanocap` fund-handled LSE ticker; historically 404 on the curated source.
    # (PRTC.L, CHG.L, KNT.TO etc. are *equity*, not funds, even though their
    # ticker strings overlap with the bellwether format — keep them on the
    # score card.)
}


def is_fund_vehicle(ticker):
    """True if `ticker` is a fund / ETF / basket whose composite score is
    structurally invalid — the the curated source Curated page returns 404 by
    design (the publisher scores companies, not baskets). We short-circuit
    before any HTTP call so the row is `FUND-VEHICLE`, not a noisy FAIL.
    The Trader routes these rows through the **ETF (E) card**; gate 1 lives
    in the radar rotation read per `rules/02_SLEEVE_RULES.md:82`.

    Membership is *explicit*, not a suffix heuristic — `CHG.L` and `PRTC.L`
    are UK-listed equities with real Curated coverage (composites 50, 27 in
    the prior run), and a generic `.L` rule would wrongly re-route them.
    Keep the set curated and update when new fund wrappers land.
    """
    return ticker.upper() in _KNOWN_FUND_VEHICLES


def _band(x, lo, hi, pts):
    """Linear score of x onto 0..pts over [lo, hi]; None stays None."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    f = (x - lo) / (hi - lo)
    return round(max(0.0, min(1.0, f)) * pts)


def _band_inv(x, lo, hi, pts):
    """Inverse band — lower x is better (debt, PE …)."""
    s = _band(x, lo, hi, pts)
    return None if s is None else pts - s


def _pillar(parts, mx):
    """Sum scored parts into (n, mx, label) or None if every part is missing."""
    known = [p for p in parts if p is not None]
    if not known:
        return None
    n = min(mx, sum(known))
    frac = n / mx
    label = ("Strong~" if frac >= 0.75 else
             "Good~" if frac >= 0.5 else
             "Mixed~" if frac >= 0.3 else "Weak~")
    return (n, mx, label)


def derive_accel_record(eps_quarterly):
    """Per `docs/DATA_SOURCES.md:46-49`:

       ACCEL: last three quarters show monotonically increasing YoY EPS growth
       RECORD: latest quarter's EPS is the highest on record

    The series array order is the publish order (periodEnd asc). We treat the
    tail as "latest" — never re-sort by periodEnd, because a re-sort would
    mask entries reordered at the publisher's side, and the monotonic test
    is over the *growth rates as published*.

    Returns `(accel: bool|None, record: bool|None)`. None means "not enough
    data to decide" — a None result is propagated as INFERRED, not as
    quietly-tagged ACCEL.
    """
    if not eps_quarterly or len(eps_quarterly) < 3:
        return None, None
    # ACCEL: last 3 quarters — i.e., entries [-1], [-2], [-3]. growth may be None.
    tail = [(lab, val, grow) for (lab, val, grow) in eps_quarterly[-3:]]
    growths = [g for (_, _, g) in tail]
    accel = (None not in growths and growths[0] < growths[1] < growths[2])

    # RECORD: latest quarter's EPS ≥ max of the series values.
    vals = [v for (_, v, _) in eps_quarterly if v is not None]
    record = bool(vals) and tail[-1][1] is not None and tail[-1][1] >= max(vals)

    return accel, record
