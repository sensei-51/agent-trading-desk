#!/usr/bin/env python3
"""
handoff.py — the structured half of every cross-agent handoff.

THE PRINCIPLE (docs/BACKLOG.md item 2, set by the user 2026-08-22)
  The evaluation a human reads stays prose. Every *other* handoff — agent to
  agent, agent to script — carries a structured form alongside it.

WHY. `eval_reviewer.py` recovered facts by parsing English, and three separate
structural false positives came out of it in one morning: the radar-staleness
substring test that no report carrying its own mandatory disclaimer could pass;
the x-ray check that demanded ████░░░ bar art be reproduced byte-for-byte; and
the CHASING check that read the wrong half of a block. Each blocked a run. A
better parser is not the fix — not parsing is the fix.

WHAT THIS MODULE IS NOT. It does not make an agent emit anything. An LLM writes
these files by following its canonical in `agents/`, and it may not. So:

    ABSENT  → the consumer falls back to its existing prose path. Never a
              failure. A missing sidecar must never be able to block a run,
              which is precisely the trap this whole backlog item came out of.
    PRESENT → validated here. Malformed or contradicted is a real defect,
              because a sidecar that lies is worse than no sidecar.

Schemas are deliberately small. Every field is one an agent already states in
prose somewhere; none asks it to compute anything new.

Usage
    python3 tools/handoff.py --check <path>        validate one file
    python3 tools/handoff.py --check-all [--date D] validate all three for a date
    python3 tools/handoff.py --selftest            schema round-trip
Exit  0 = valid (or honestly absent), 1 = present and malformed.
"""

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))
STATE_DIR = os.path.join(OUTPUT_DIR, ".state")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")

# Three states, per agents/manager.md "Output format" — NOT two. `PASS WITH
# DEFECTS` is presentation/formatting only and does not trigger the
# orchestrator's defect loop; only FAIL does.
VERDICTS = ("PASS", "PASS WITH DEFECTS", "FAIL")
LEG_STATUS = ("OK", "PARTIAL", "FAIL", "NONE", "ABSENT", "STALE")

# kind -> (path template, required top-level keys, row spec)
# A row spec is (list-key, {field: type-or-None}); None means "any scalar".
SCHEMAS = {
    "analyst": {
        "path": os.path.join(DATA_DIR, "analyst_{date}.json"),
        "top": {"date": str, "legs": list},
        "rows": ("legs", {"leg": str, "status": str}),
        "doc": "Analyst → Trader. The per-leg source status, structured.",
    },
    "eval": {
        "path": os.path.join(STATE_DIR, "eval_manifest_{date}.json"),
        "top": {"date": str, "radar_verdict": str, "coverage": dict,
                "sections": list},
        "rows": ("gates", {"ticker": str, "card": str}),
        # gates[] IS THE LEDGER'S INPUT, so a sidecar without it is not a
        # smaller sidecar — it is a sidecar that silently demotes the permanent
        # audit trail back to the prose parser. The whole-sidecar contract stays
        # additive (no file at all is honest, and every consumer falls back);
        # what is refused is a file that claims to say what the Trader did while
        # omitting the one field the ledger reads. On 2026-08-24 the Trader
        # emitted exactly that, `--check-all` reported ✅ because the row check
        # below skips an absent key, and the run wrote its ledger from prose.
        "requires_rows": True,
        "doc": ("Trader → Reviewer → ledger. What the Trader asserts it did. "
                "`gates[]` is also the ledger's input — see LEDGER FIELDS below."),
    },
    "review": {
        "path": os.path.join(STATE_DIR, "review_{date}.json"),
        "top": {"date": str, "verdict": str, "defects": list},
        "rows": ("defects", {"id": None, "check": str}),
        "doc": "Reviewer → orchestrator. Verdict + numbered defects.",
    },
}


# Ledger currencies. `GBp` is pence — the broker export's own spelling, and the
# distinction that `tools/append_gate_ledger.py:parse_price` exists to preserve.
CCY = {"USD", "GBP", "GBp", "EUR", "CAD"}


def path_for(kind, date):
    return SCHEMAS[kind]["path"].format(date=date)


def load(kind, date):
    """(payload|None, note). Absent is a normal state and returns (None, why)."""
    p = path_for(kind, date)
    if not os.path.exists(p):
        return None, f"no {os.path.basename(p)} — consumer falls back to prose"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f), os.path.basename(p)
    except (ValueError, OSError) as e:
        return None, f"{os.path.basename(p)} unreadable: {type(e).__name__}: {e}"


def validate(kind, payload, date=None):
    """[] when the payload satisfies the schema, else a list of problems."""
    spec = SCHEMAS[kind]
    bad = []
    if not isinstance(payload, dict):
        return [f"{kind}: top level is {type(payload).__name__}, expected object"]

    for key, typ in spec["top"].items():
        if key not in payload:
            bad.append(f"{kind}: missing required key {key!r}")
        elif not isinstance(payload[key], typ):
            bad.append(f"{kind}: {key!r} is {type(payload[key]).__name__}, "
                       f"expected {typ.__name__}")

    # A sidecar carrying the wrong date is the cross-date bug that produced
    # eval_reviewer's false x-ray defects. Refuse it rather than compare it.
    if date and payload.get("date") not in (None, date):
        bad.append(f"{kind}: date is {payload.get('date')!r}, reviewing {date!r} "
                   f"— stale sidecar, do not compare")

    list_key, fields = spec["rows"]
    rows = payload.get(list_key)
    if rows is None and spec.get("requires_rows"):
        bad.append(f"{kind}: missing {list_key!r} — this sidecar exists to carry "
                   f"it, and it is the ledger's input. Omit the whole file if "
                   f"you cannot produce it; do not ship it without {list_key}.")
    elif not rows and spec.get("requires_rows") and isinstance(rows, list):
        bad.append(f"{kind}: {list_key!r} is empty — a run that ran no gate "
                   f"cards has no evaluation to review.")
    if rows is not None:
        if not isinstance(rows, list):
            bad.append(f"{kind}: {list_key!r} is not a list")
        else:
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    bad.append(f"{kind}: {list_key}[{i}] is not an object")
                    continue
                for f, typ in fields.items():
                    if f not in row:
                        bad.append(f"{kind}: {list_key}[{i}] missing {f!r}")
                    elif typ and not isinstance(row[f], typ):
                        bad.append(f"{kind}: {list_key}[{i}].{f} is "
                                   f"{type(row[f]).__name__}, expected {typ.__name__}")

    if kind == "review" and payload.get("verdict") not in VERDICTS:
        bad.append(f"review: verdict {payload.get('verdict')!r} not one of {VERDICTS}")
    if kind == "analyst":
        for i, leg in enumerate(payload.get("legs") or []):
            s = (leg or {}).get("status")
            if isinstance(s, str) and s.upper() not in LEG_STATUS:
                bad.append(f"analyst: legs[{i}].status {s!r} not one of {LEG_STATUS}")
    if kind == "eval":
        cov = payload.get("coverage") or {}
        for k in ("covered", "roster"):
            if k not in cov:
                bad.append(f"eval: coverage missing {k!r}")
        for i, g in enumerate(payload.get("gates") or []):
            g = g or {}
            # "-" IS A THIRD LEGITIMATE ANSWER, and leaving it out cost a row.
            # A name can carry a decision without carrying a card: on 2026-08-24
            # SSLN.L was a 🔴 SELL whose vehicle the run could not confirm, so
            # the report asserted no card at all. With only S/E permitted, the
            # Trader had one way to stay schema-valid — omit the row — and the
            # day's most consequential call was the one call absent from the
            # permanent record. THE LEDGER RECORDS DECISIONS, NOT GATE CARDS.
            # Use "-" when no card was asserted, and leave `result` empty.
            if g.get("card") not in ("S", "E", "-", None):
                bad.append(f"eval: gates[{i}].card {g.get('card')!r} not 'S', 'E' "
                           f"or '-' — the stock/fund split AGENTS.md requires, "
                           f"or '-' for a decision taken with no card asserted")
            if g.get("card") == "-" and str(g.get("result") or "").strip():
                bad.append(f"eval: gates[{i}].card is '-' (no card asserted) but "
                           f"result is {g.get('result')!r} — a gate result "
                           f"without a card is one of the two things lying")
            # LEDGER FIELDS. `tools/append_gate_ledger.py` drafts from these
            # rather than re-parsing the report's prose. Each is a value the
            # Trader already writes in the board row, so none asks it to
            # compute anything new — the rule at the top of this file.
            sig = g.get("signal")
            if sig is not None and not str(sig).strip():
                bad.append(f"eval: gates[{i}].signal is empty — omit the key "
                           f"or state the signal; a blank drafts a blank row")
            ccy = g.get("ccy")
            if ccy is not None and ccy not in CCY:
                bad.append(f"eval: gates[{i}].ccy {ccy!r} not one of {sorted(CCY)}")
            px = g.get("px")
            if px is not None:
                try:
                    float(str(px).replace(",", ""))
                except ValueError:
                    bad.append(f"eval: gates[{i}].px {px!r} is not a number — "
                               f"state the bare figure, currency goes in `ccy`")
        # SIGNAL COVERAGE, stated once. `signal` is optional by design — the rule
        # at the top of this file is that absent is always fine and the consumer
        # falls back. A manifest with none of them is an honest older-style
        # manifest; `append_gate_ledger.py` parses the prose instead. A manifest
        # with *some* is the suspicious case: the ledger would silently draft a
        # partial day and look like it succeeded.
        gates = payload.get("gates") or []
        withsig = [g for g in gates if (g or {}).get("signal")]
        if gates and 0 < len(withsig) < len(gates):
            bad.append(f"eval: gates[] carries 'signal' on {len(withsig)} of "
                       f"{len(gates)} rows — partial. The ledger drafts only "
                       f"from rows that have it, so a partial day would look "
                       f"like a complete one. Emit it on all rows or none.")
    return bad


def check_file(path):
    kind = next((k for k, s in SCHEMAS.items()
                 if os.path.basename(s["path"]).split("_{")[0]
                 in os.path.basename(path)), None)
    if kind is None:
        print(f"⛔ {path}: not a recognised handoff file")
        return 1
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (ValueError, OSError) as e:
        print(f"⛔ {path}: {type(e).__name__}: {e}")
        return 1
    bad = validate(kind, payload)
    for b in bad:
        print(f"⛔ {b}")
    print(("✅ " if not bad else "⛔ ") + f"{os.path.basename(path)} ({kind})")
    return 1 if bad else 0


def check_all(date):
    rc = 0
    for kind in SCHEMAS:
        payload, note = load(kind, date)
        if payload is None:
            print(f"⚪ {kind:8s} {note}")
            continue
        bad = validate(kind, payload, date)
        for b in bad:
            print(f"⛔ {b}")
        print(("✅ " if not bad else "⛔ ") + f"{kind:8s} {note}")
        rc |= 1 if bad else 0
    return rc


def selftest():
    """Round-trip a good and a bad payload per schema."""
    good = {
        "analyst": {"date": "2026-08-22",
                    "legs": [{"leg": "fundamentals", "adapter": "curated",
                              "status": "OK", "notes": "101/101"},
                             {"leg": "conviction", "adapter": "convictionsource",
                              "status": "ABSENT", "notes": "no capture"}]},
        "eval": {"date": "2026-08-22", "radar_verdict": "FRESH",
                 "coverage": {"covered": 97, "roster": 97},
                 "sections": ["Market snapshot", "Rotation read"],
                 "gates": [{"ticker": "NVDA", "card": "S", "result": "S 7/7",
                            "signal": "HOLD", "px": "174.04", "ccy": "USD"}]},
        "review": {"date": "2026-08-22", "verdict": "PASS", "defects": []},
    }
    bad = {
        "analyst": {"date": "2026-08-22",
                    "legs": [{"leg": "facts", "status": "SPLENDID"}]},
        "eval": {"date": "2026-08-22", "radar_verdict": "FRESH",
                 "coverage": {"covered": 97}, "sections": [],
                 "gates": [{"ticker": "NVDA", "card": "X", "signal": "",
                            "px": "$174", "ccy": "DOLLARS"},
                           {"ticker": "AMD", "card": "S", "signal": "HOLD"}]},
        "review": {"date": "2026-08-22", "verdict": "MAYBE", "defects": []},
    }
    fails = 0
    for kind in SCHEMAS:
        g = validate(kind, good[kind], "2026-08-22")
        b = validate(kind, bad[kind], "2026-08-22")
        s = validate(kind, dict(good[kind], date="1999-01-01"), "2026-08-22")
        ok = (not g) and bool(b) and bool(s)
        # THE 2026-08-24 CASE: envelope perfect, row list gone. Only the kinds
        # that declare requires_rows may refuse it; the others still accept it.
        if SCHEMAS[kind].get("requires_rows"):
            stripped = {k: v for k, v in good[kind].items()
                        if k != SCHEMAS[kind]["rows"][0]}
            ok = ok and bool(validate(kind, stripped, "2026-08-22"))
        fails += not ok
        print(f"  {'ok   ' if ok else 'FAIL '}{kind:8s} "
              f"good={len(g)} bad={len(b)} stale-date={len(s)}")
    print(f"\n{len(SCHEMAS) - fails}/{len(SCHEMAS)} schemas behave as specified.")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description="Validate cross-agent handoff sidecars.")
    ap.add_argument("--check", metavar="PATH")
    ap.add_argument("--check-all", action="store_true")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.check:
        return check_file(a.check)
    if a.check_all:
        return check_all(a.date)
    for kind, s in SCHEMAS.items():
        print(f"{kind:8s} {os.path.relpath(s['path'].format(date='<date>'), ROOT)}")
        print(f"         {s['doc']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
