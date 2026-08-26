#!/usr/bin/env python3
"""
contracts.py — what a provider must declare, and what it must return.

A "leg" is one of the three evidence sources the method runs on:

    fundamentals   is this a good business?          per-ticker
    darkpool           what is being traded right now?   whole-portfolio
    conviction     what does the strategic source say? whole-portfolio

A "provider" is one implementation of one leg — Curated, a Yahoo-derived proxy,
a file you maintain by hand, or nothing at all. Providers are plain Python
modules discovered from disk (see `providers/__init__.py`); this file is the
contract they are held to.

WHY A CONTRACT AND NOT A DUCK TYPE. The previous design (`ADAPTERS` dict in
tools/fundamentals.py) was duck-typed and hardcoded: adding a source meant
editing two core files, and a source that returned a differently-shaped dict
failed somewhere downstream with no useful error. Worse, the gates assumed one
particular source's shape — a provider that supplies a score but no
ACCEL/RECORD made `gate1` return FAIL(no-ACCEL/RECORD-data) for every name in
the book, rendering a *data gap* as a *quality failure*. `CAPABILITIES` below
is the fix: a provider declares what it can supply, and the gates degrade the
clauses it cannot rather than poisoning the verdict.
"""

# ---------------------------------------------------------------- legs

LEGS = ("fundamentals", "darkpool", "conviction")

# Legs that answer per-ticker (provider exposes `fetch(ticker, ctx)`) vs legs
# that answer for the whole book at once (provider exposes `load(ctx)`).
PER_TICKER_LEGS = ("fundamentals",)
WHOLE_BOOK_LEGS = ("darkpool", "conviction")

# ---------------------------------------------------------------- status

# The row-level verdict. Meanings are load-bearing — `build_row`'s fallback
# fires on FAIL and nothing else, and the gates branch on NONE / FUND-VEHICLE.
OK            = "OK"             # full data
PARTIAL       = "PARTIAL"        # some fields missing, what is present is real
FAIL          = "FAIL"           # this provider could not answer — fallback may fire
NONE          = "NONE"           # no source configured; gates go INFERRED
FUND_VEHICLE  = "FUND-VEHICLE"   # ETF/OEIC — the stock card does not apply

STATUSES = (OK, PARTIAL, FAIL, NONE, FUND_VEHICLE)

# ---------------------------------------------------------------- capabilities

# What a provider may declare in `PROVIDER["supplies"]`. A capability absent
# from the set means "this provider cannot answer that question" — which is a
# different thing from answering "no", and the gates must treat it differently.
CAPABILITIES = {
    "fundamentals": {
        "score",      # 0-100 composite
        "pillars",    # {name: (n, max, label)}
        "accel",      # earnings acceleration tag
        "record",     # record-quarter tag
        "eps",        # quarterly EPS series
        "revenue",    # quarterly revenue series
        "insiders",   # Form 4 insider buy/sell
        "congress",   # legislator disclosures
    },
    "darkpool": {
        "premium",    # currency-weighted darkpool per ticker
        "direction",  # bullish/bearish split
        "prints",     # individual trade detail
        "unusual",    # unusualness / conviction score per print
    },
    "conviction": {
        "regime",     # cash / moderate / aggressive style signal
        "weights",    # model-portfolio position weights
        "changes",    # deltas since the previous publication
    },
}

INGESTION_MODES = (
    "fetch",    # provider makes its own network calls
    "file",     # provider reads a file the user drops in
    "browser",  # a human or agent captures from a logged-in session to a file
)

REQUIRED_KEYS = ("name", "leg", "ingestion", "supplies", "approx", "private")


class ProviderError(Exception):
    """A provider is malformed. Raised at discovery, never swallowed —
    a broken provider must be loud, because the alternative is a leg that
    silently reports NONE and a book that silently goes un-gated."""


def validate_declaration(mod, source):
    """Check a module's PROVIDER dict. Returns the dict; raises ProviderError.

    `source` is the file path, quoted in errors so a contributor debugging
    their own provider is told exactly which file is wrong.
    """
    d = getattr(mod, "PROVIDER", None)
    if not isinstance(d, dict):
        raise ProviderError(f"{source}: no PROVIDER dict")

    missing = [k for k in REQUIRED_KEYS if k not in d]
    if missing:
        raise ProviderError(f"{source}: PROVIDER missing key(s): {', '.join(missing)}")

    leg = d["leg"]
    if leg not in LEGS:
        raise ProviderError(f"{source}: leg {leg!r} unknown (expected one of {LEGS})")

    if d["ingestion"] not in INGESTION_MODES:
        raise ProviderError(f"{source}: ingestion {d['ingestion']!r} unknown "
                            f"(expected one of {INGESTION_MODES})")

    supplies = set(d.get("supplies") or ())
    unknown = supplies - CAPABILITIES[leg]
    if unknown:
        raise ProviderError(f"{source}: unknown capability {sorted(unknown)} for leg "
                            f"{leg!r}; known: {sorted(CAPABILITIES[leg])}")

    entry = "fetch" if leg in PER_TICKER_LEGS else "load"
    if not callable(getattr(mod, entry, None)):
        raise ProviderError(f"{source}: leg {leg!r} requires a callable {entry}()")

    if not isinstance(d["approx"], bool) or not isinstance(d["private"], bool):
        raise ProviderError(f"{source}: 'approx' and 'private' must be booleans")

    # max_age_days is optional but must be sane where present. A `browser` or
    # `file` provider with no staleness bound is a silent-gap risk: the capture
    # goes unread for a week and the run keeps quoting it as current.
    age = d.get("max_age_days")
    if age is not None and (not isinstance(age, int) or age < 1):
        raise ProviderError(f"{source}: max_age_days must be a positive int or None")
    if d["ingestion"] in ("file", "browser") and age is None:
        raise ProviderError(f"{source}: ingestion {d['ingestion']!r} requires "
                            f"max_age_days — an unbounded capture is quoted as live "
                            f"forever, which is the exact failure the honesty checks exist "
                            f"to catch")
    return d


def validate_payload(leg, payload, source):
    """Shape-check what a provider returned. Cheap, and it turns a downstream
    AttributeError three functions later into a named error here."""
    if not isinstance(payload, dict):
        raise ProviderError(f"{source}: returned {type(payload).__name__}, expected dict")
    st = payload.get("status")
    if st not in STATUSES:
        raise ProviderError(f"{source}: status {st!r} not in {STATUSES}")
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, (list, tuple)):
        raise ProviderError(f"{source}: 'notes' must be a list")
    return payload


def supplies(provider, capability):
    """True when `provider` declares it can answer `capability`.

    Use this in a gate before consulting a field, so a provider that does not
    offer (say) ACCEL/RECORD produces an INFERRED clause naming the gap rather
    than a FAIL that reads as a judgement about the company.
    """
    return capability in (provider.declaration.get("supplies") or ())
