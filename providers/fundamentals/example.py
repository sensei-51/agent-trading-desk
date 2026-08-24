#!/usr/bin/env python3
"""
example — a working template for a fundamentals provider. Copy, rename, edit.

This file is a real provider (it satisfies the contract and would run), but it
is filtered out of the selectable list, so it can stay honest without ever
being chosen by accident.

WHAT TO CHANGE
  1. `PROVIDER["name"]`      — how the config refers to you.
  2. `PROVIDER["ingestion"]` — see below.
  3. `PROVIDER["supplies"]`  — declare ONLY what you can really answer.
  4. `fetch()`               — return the payload described at the bottom.

Nothing in core needs editing. Drop this file in `providers/fundamentals/`,
point `input/config/providers.json` at its name, and it runs.

--------------------------------------------------------------------------
CHOOSING AN INGESTION MODE

  "fetch"    You call an API or public page yourself. Fastest to use, but
             check the source's terms first: several retail research
             platforms prohibit automated access outright, and a provider
             that quietly breaches those puts the user's subscription at
             risk, not yours.

  "file"     You read a file the user drops in — an export, a download.
             Preferred where the platform offers a first-party export,
             because an export is sanctioned, stable, and usually richer
             than what a page scrape can reconstruct.

  "browser"  A human or agent reads a logged-in screen and writes a capture
             file which you then parse. Use where there is no API and no
             export.

  "file" and "browser" MUST set `max_age_days`. An unbounded capture is
  quoted as live forever, which is precisely the silent-gap failure the
  honesty checks exist to catch.

--------------------------------------------------------------------------
DECLARING CAPABILITIES HONESTLY — THE PART THAT MATTERS

`supplies` is not documentation. The gates consult it before they consult
your data.

If you cannot produce an earnings-acceleration tag, leave "accel" out. Gate 1
will then return `GATE1-INFERRED(provider-supplies-no-accel)` for that clause
— a visible gap, correctly attributed to your provider. If you instead
declare "accel" and return None, gate 1 reads that as "checked, and the
company does not accelerate", and returns FAIL. Same missing data, but one
version blames your provider and the other blames the company. Only one of
those is true.

Over-declaring is the single most damaging thing a provider can do here, and
it fails silently.

--------------------------------------------------------------------------
APPROXIMATE DATA

Set `approx: True` if your numbers are estimates or proxies rather than a
curated composite. You do not need to do anything else — the `~` grade
markers, the GATE1/GATE2-BORDERLINE zones, and the report caveats all key off
this flag. See `providers/fundamentals/derived.py` for a calibrated example.

If you ship an `approx` provider for others to use, calibrate it against a
curated source first and publish the confusion matrix, as
`docs/DERIVED_CALIBRATION_2026-08-18.md` does. The acceptance test is false
passes driven to zero: a false FAIL costs a look, a false PASS moves money.
"""

PROVIDER = {
    "name": "example",
    "leg": "fundamentals",
    "ingestion": "fetch",
    "supplies": {"score", "pillars"},
    "approx": True,
    "private": False,
    "max_age_days": None,
}


def fetch(ticker, ctx=None):
    """Return one row for `ticker`.

    `ctx` carries run context (paths, the run date) and may be ignored.

    Required key
    ------------
    status : "OK" | "PARTIAL" | "FAIL" | "NONE" | "FUND-VEHICLE"
        OK            full data
        PARTIAL       some fields missing, what is present is real
        FAIL          you could not answer — the configured fallback fires
        NONE          no source configured (the `none` provider's state)
        FUND-VEHICLE  an ETF/basket; the stock card does not apply

        Only FAIL triggers the fallback. Returning FAIL when you mean
        "no data exists for this name" will silently promote the fallback's
        approximate answer over your curated one, so reserve it for
        "my source was unreachable or unparseable".

    Optional keys (supply what you declared)
    ----------------------------------------
    score             int 0-100
    grade             str, e.g. "Good"
    pillars           {name: (n, max, label)}
    accel             bool | None   earnings acceleration
    record            bool | None   record quarter
    eps_quarterly     [(period, value, yoy_growth_pct), ...] oldest first
    revenue_quarterly same shape
    notes             [str] — surfaced in the report; say why data is missing
    approx            bool — overrides the declaration for this row only
    """
    return {
        "score": None,
        "grade": None,
        "pillars": None,
        "eps_quarterly": None,
        "revenue_quarterly": None,
        "status": "NONE",
        "notes": ["example provider — copy this file and implement fetch()"],
    }
