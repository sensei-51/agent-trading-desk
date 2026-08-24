#!/usr/bin/env python3
"""
derived — a Curated-shaped composite rebuilt from free Yahoo data.

This is the PUBLIC fallback for the fundamentals leg, and the reference
instance of an `approx: True` provider: every number it produces is an
estimate, it says so, and the honesty machinery downstream (the `~` markers,
the GATE*-BORDERLINE zones) keys off that flag rather than off this provider's
name.

Calibrated against 86 real curated composites on 18 Aug 2026 —
`docs/DERIVED_CALIBRATION_2026-08-18.md`: r = 0.88, runs +3.4 points hot
(median +2.5, sigma 8.8), ACCEL/RECORD tag agreement 81%. The borderline rules
took gate-1 false passes from 5 to 1 and gate-2 from 3 to 0. That acceptance
test — false passes driven toward zero, because a false FAIL costs a look and
a false PASS moves money — is the bar any replacement should be held to.

Pillar maxima deliberately match the curated source (Q/30 G/20 CF/10 Stab/10
Val/10 Own/15) so the gate thresholds in tools/fundamentals.py read the same
numbers whichever provider answered.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring import (_band, _band_inv, _pillar, is_fund_vehicle,   # noqa: E402
                     derive_accel_record)

PROVIDER = {
    "name": "derived",
    "leg": "fundamentals",
    "ingestion": "fetch",
    "supplies": {"score", "pillars", "accel", "record", "eps"},
    "approx": True,
    "private": False,
    "max_age_days": None,
}


def fetch(ticker, ctx=None):
    return _fetch(ticker)


def derived_eps_series(tk):
    """[(period, eps, growth_yoy)] ascending, from reported-EPS history.

    Yahoo's earnings-dates feed carries ~2 years of reported EPS — enough for
    the YoY growth series ACCEL needs (t vs t-4). Rows without a reported
    figure (future dates) are dropped; growth is None until 4 priors exist,
    and None growth propagates to `accel=None` → INFERRED, never a quiet tag.
    """
    try:
        df = tk.get_earnings_dates(limit=16)
    except Exception:
        return None
    if df is None or getattr(df, "empty", True):
        return None
    col = next((c for c in df.columns if "reported" in c.lower()), None)
    if col is None:
        return None
    pts = []
    for idx, val in df[col].items():
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v != v:
            continue
        pts.append((idx.date().isoformat() if hasattr(idx, "date") else str(idx), v))
    pts.sort()
    if len(pts) < 3:
        return None
    out = []
    for i, (lab, v) in enumerate(pts):
        g = None
        if i >= 4 and pts[i - 4][1]:
            g = round((v - pts[i - 4][1]) / abs(pts[i - 4][1]) * 100, 1)
        out.append((lab, v, g))
    return out


def _fetch(ticker):
    """Yahoo-proxied pillar scores on the curated scale. Approximate (~)."""
    if is_fund_vehicle(ticker):
        return {
            "score": None, "grade": None, "pillars": None,
            "eps_quarterly": None, "revenue_quarterly": None,
            "status": "FUND-VEHICLE",
            "notes": ["fund/ETF wrapper — company scoring structurally invalid; "
                      "E card, gate 1 from the rotation read"],
        }
    try:
        import yfinance as yf
    except ImportError:
        return {
            "score": None, "grade": None, "pillars": None,
            "eps_quarterly": None, "revenue_quarterly": None,
            "status": "NONE",
            "notes": ["the `derived` provider needs yfinance — `pip install yfinance` "
                      "(or set the fundamentals provider back to `none`)"],
        }
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as e:
        return {"score": None, "grade": None, "pillars": None,
                "eps_quarterly": None, "revenue_quarterly": None,
                "status": "FAIL", "notes": [f"Yahoo fetch failed: {e!r}"]}
    if not info or info.get("quoteType", "EQUITY") not in ("EQUITY", None):
        if info.get("quoteType") == "ETF":
            return {"score": None, "grade": None, "pillars": None,
                    "eps_quarterly": None, "revenue_quarterly": None,
                    "status": "FUND-VEHICLE",
                    "notes": ["Yahoo reports quoteType=ETF — E card; consider "
                              "adding to _KNOWN_FUND_VEHICLES"]}

    g = info.get
    ocf, ni = g("operatingCashflow"), g("netIncomeToCommon")
    fcf, rev = g("freeCashflow"), g("totalRevenue")
    pillars = {
        "quality": _pillar([_band(g("grossMargins"), 0.20, 0.60, 10),
                            _band(g("operatingMargins"), 0.05, 0.30, 10),
                            _band(g("returnOnEquity"), 0.05, 0.30, 10)], 30),
        "growth": _pillar([_band(g("revenueGrowth"), -0.05, 0.30, 10),
                           _band(g("earningsGrowth"), -0.10, 0.50, 10)], 20),
        "cash_flow": _pillar([_band((fcf / rev) if fcf and rev else None,
                                    0.0, 0.25, 5),
                              _band((ocf / ni) if ocf and ni and ni > 0 else None,
                                    0.8, 1.5, 5)], 10),
        "stability": _pillar([_band_inv(g("debtToEquity"), 0, 200, 4),
                              _band(g("currentRatio"), 1.0, 2.5, 3),
                              _band_inv(g("beta"), 0.5, 2.0, 3)], 10),
        "valuation": _pillar([_band_inv(g("trailingPE"), 10, 60, 4),
                              _band_inv(g("pegRatio") or g("trailingPegRatio"),
                                        0.5, 3.0, 3),
                              _band_inv(g("priceToSalesTrailing12Months"),
                                        1, 15, 3)], 10),
        "ownership": _pillar([_band(g("heldPercentInstitutions"), 0.0, 0.90, 9),
                              _band(g("heldPercentInsiders"), 0.0, 0.20, 6)], 15),
    }
    have = {k: v for k, v in pillars.items() if v is not None}
    if not have:
        return {"score": None, "grade": None, "pillars": None,
                "eps_quarterly": None, "revenue_quarterly": None,
                "status": "FAIL",
                "notes": ["Yahoo returned no scoreable fundamentals"]}
    # Composite: sum of scored pillars rescaled to /100 over the maxes we
    # actually had data for — a missing pillar shrinks the denominator
    # instead of counting as zero (which would punish data gaps as quality).
    got = sum(v[0] for v in have.values())
    of = sum(v[1] for v in have.values())
    score = round(got / of * 100) if of else None
    grade = ("Exceptional~" if score >= 80 else "Good~" if score >= 65 else
             "Average~" if score >= 50 else "Weak~" if score >= 35 else "Poor~")
    eps_q = derived_eps_series(tk)
    missing = sorted(set(pillars) - set(have))
    notes = ["~derived from Yahoo Finance proxies — approximate, "
             "not a curated composite (DATA_SOURCES rule 4)"]
    if missing:
        notes.append("no data for pillar(s): " + ", ".join(missing))
    if eps_q is None:
        notes.append("no reported-EPS history — ACCEL/RECORD undecidable "
                     "(gate 1 reads no-ACCEL/RECORD-data, a data fail not a "
                     "quality fail)")
    return {"score": score, "grade": grade, "pillars": pillars,
            "eps_quarterly": eps_q, "revenue_quarterly": None,
            "status": "OK" if not missing else "PARTIAL",
            "approx": True,  # gates apply the proxy-resolution BORDERLINE zones
            "notes": notes}
