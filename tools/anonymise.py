#!/usr/bin/env python3
"""
anonymise.py — turn a real broker export into a publishable one.

Scales every quantity and cash amount by a single factor so the sleeve totals a
nominal NAV (default £100,000), strips account-identifying columns, and leaves
tickers, prices, percentages and dates exactly as they are.

WHY A SCRIPT AND NOT A HAND EDIT. Publishing a portfolio is a one-line decision and a
permanent consequence: git history keeps whatever you commit. The risk is not the first
publish — it is the fifth refresh three months later, done in a hurry, where one real
quantity survives. A hand edit has no way to be right twice. This does.

WHAT IS PRESERVED — everything the repo's analysis actually reads:
  · tickers, instrument names, currencies, dates
  · unit prices and average entry prices          (unscaled — a price is not a secret)
  · every percentage: gain %, day move %, weights (unscaled — scaling would break them)
  · relative position weights, to the rounding tolerance below
Because the ruleset is entirely NAV-relative — 5% position cap, 0.8–1% risk per trade,
25% bloc ceiling, and a radar that reads gain percentages — a reader running the rules
against the scaled file reaches the same conclusions you do. Nothing is lost.

WHAT IS REMOVED:
  · absolute sleeve NAV and absolute position sizes
  · account numbers, client references, holder names

THE SCALE FACTOR IS NEVER WRITTEN TO ANY OUTPUT FILE. It is printed to your terminal
only. Anything that records it — a header comment, a log file, a commit message — hands
back the real NAV by division and undoes the entire exercise.

Usage:
    python3 tools/anonymise.py ~/Downloads/real-export.csv
    python3 tools/anonymise.py ~/Downloads/*.csv --ledger output/ledger/Gate_Ledger.csv
    python3 tools/anonymise.py real.csv --target-nav 250000 --out-dir /tmp/check

Standard library only, like everything else here.
"""

import argparse, csv, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
try:
    # Reuse the radar's column detection so the two can never disagree about which
    # column is the ticker. A second, independent parser would drift.
    from heartbeat_radar import (norm_header, read_csv_rows, pick_column,
                                 TICKER_HEADERS, NAME_HEADERS, is_screenable)
except Exception as e:                                     # pragma: no cover
    print(f"could not import engine/heartbeat_radar.py: {e}", file=sys.stderr)
    raise SystemExit(1)

# Columns holding a count of units or an amount of money — these scale.
SCALE_HINTS = ("qty", "quantity", "units", "shares", "value", "cost", "gain", "loss",
               "change", "book", "market value", "profit", "proceeds", "amount")

# Columns that must NEVER scale, checked first. A price stays a price at any sleeve
# size; a percentage is already relative and scaling it would corrupt it; an FX rate
# is not yours. "Gain/Loss %" matches both lists, which is exactly why this wins.
NO_SCALE = ("%", "percent", "price", "rate", "date", "time", "currency", "ccy",
            "yield", "per share", "per unit")

# Columns dropped outright.
ACCOUNT_HEADERS = ("account", "client", "customer", "holder", "nominee", "reference",
                   "ref no", "plan number", "sipp", "isa number", "user", "owner",
                   "national insurance", "nino", "address", "postcode", "email")

# Cell values that look like an account identifier, redacted wherever they appear.
ACCOUNT_VALUE = re.compile(r"^(?=.*\d)[A-Z0-9][A-Z0-9\-/]{7,}$", re.I)

# ...but dates match that shape too. "05-Jan-26" and "2026-01-05" are not account
# numbers, and redacting them corrupts the file while looking like it worked.
DATE_LIKE = re.compile(
    r"^\d{1,4}[-/. ]\d{1,2}[-/. ]\d{1,4}$"
    r"|^\d{1,2}[-/. ][A-Za-z]{3,9}[-/. ]\d{2,4}$"
    r"|^[A-Za-z]{3,9}[-/. ]\d{1,2}[-/. ]\d{2,4}$")


def is_scalable(header):
    n = norm_header(header)
    if any(x in n for x in NO_SCALE):
        return False
    return any(x in n for x in SCALE_HINTS)


def is_account_col(header):
    n = norm_header(header)
    # "Name"/"Investment" is the security name and must survive; only drop a name
    # column that is clearly about a person.
    if any(x in n for x in ("account name", "client name", "holder name")):
        return True
    return any(x in n for x in ACCOUNT_HEADERS)


def numeric(s):
    """('1,234.50', 1234.5) tolerant of currency symbols, commas and trailing %."""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    neg = t.startswith("(") and t.endswith(")")          # (123.00) accounting negative
    t2 = re.sub(r"[^0-9.\-]", "", t)
    if not t2 or t2 in ("-", ".", "-."):
        return None
    try:
        v = float(t2)
    except ValueError:
        return None
    return -v if neg else v


def reformat(original, value, min_dec=0):
    """Re-apply the original cell's formatting to a new number.

    Brokers are inconsistent — "$10,500.00", "10,500.00", "(500.00)" — and a reader
    should not be able to spot which rows were touched by their formatting alone.

    `min_dec` exists for quantities. A whole-share holding scaled down by a factor of
    five is not a whole number any more, and rounding it to an integer moves the
    position's weight by up to half a share — which at a three-figure share price is a
    visible distortion of the very weights this is meant to preserve.
    """
    s = str(original).strip()
    neg = value < 0
    dec = 2
    m = re.search(r"\.(\d+)", s)
    if m:
        dec = len(m.group(1))
    elif not re.search(r"\.", s):
        dec = 0
    dec = max(dec, min_dec)
    body = f"{abs(value):,.{dec}f}" if "," in s else f"{abs(value):.{dec}f}"
    prefix = "".join(re.findall(r"^[^\d\-(.]+", s))
    if s.startswith("(") and s.endswith(")"):
        return f"({prefix}{body})"
    return f"{prefix}{'-' if neg else ''}{body}"


def sleeve_total(files):
    """Total market value across every export, so one factor covers all sleeves.

    A per-file factor would preserve each file's internal weights while silently
    distorting the weights *between* sleeves — and cross-sleeve weight is what the
    25% per-sector bloc ceiling is measured against.
    """
    total = 0.0
    for path in files:
        rows = read_csv_rows(path)
        if not rows:
            continue
        heads = list(rows[0].keys())
        valcol = pick_column(heads, ("market value", "value", "total value"),
                             exclude=("%", "book", "cost"))
        qtycol = pick_column(heads, ("qty", "quantity", "units", "shares"), exclude=("%",))
        pxcol = pick_column(heads, ("price", "share price"), exclude=("%", "average", "avg"))
        for row in rows:
            v = numeric(row.get(valcol)) if valcol else None
            if v is None and qtycol and pxcol:
                q, p = numeric(row.get(qtycol)), numeric(row.get(pxcol))
                v = q * p if (q is not None and p is not None) else None
            if v is not None:
                total += v
    return total


def scale_csv(path, factor, out_dir, suffix):
    rows = read_csv_rows(path)
    if not rows:
        print(f"  {os.path.basename(path)}: empty, skipped")
        return None
    heads = list(rows[0].keys())
    drop = [h for h in heads if is_account_col(h)]
    keep = [h for h in heads if h not in drop]
    scaled = [h for h in keep if is_scalable(h)]
    namecol = pick_column(keep, NAME_HEADERS)

    # Columns needed to keep the arithmetic self-consistent after rounding.
    qtycol = pick_column(keep, ("qty", "quantity", "units", "shares"), exclude=("%",))
    pxcol = pick_column(keep, ("price", "share price"), exclude=("%", "average", "avg", "+/-"))
    avgcol = pick_column(keep, ("average price", "avg price", "average cost"), exclude=("%",))
    valcol = pick_column(keep, ("market value", "total value", "value"), exclude=("%", "book", "cost"))
    costcol = pick_column(keep, ("book cost", "total cost", "cost"), exclude=("%",))

    out_rows = []
    redacted = 0
    for row in rows:
        r = {}
        for h in keep:
            val = row.get(h)
            if h in scaled:
                n = numeric(val)
                r[h] = (reformat(val, n * factor, min_dec=2 if h == qtycol else 0)
                        if n is not None else val)
            elif (val and ACCOUNT_VALUE.match(str(val).strip())
                    and not DATE_LIKE.match(str(val).strip())
                    and not is_screenable(str(val).strip(), row.get(namecol) or "")):
                r[h] = "REDACTED"
                redacted += 1
            else:
                r[h] = val

        # Reconcile. Scaling each money column independently leaves Qty × Price no
        # longer equal to Value once the quantity is rounded, and a published export
        # whose own arithmetic does not add up is both obviously doctored and useless
        # to anyone trying to follow the sizing worked examples. So the rounded
        # quantity is treated as truth and the cash columns are recomputed from it.
        q = numeric(r.get(qtycol)) if qtycol else None
        px = numeric(r.get(pxcol)) if pxcol else None
        if q is not None and px is not None:
            if valcol and numeric(row.get(valcol)) is not None:
                r[valcol] = reformat(row[valcol], q * px)
            avg = numeric(r.get(avgcol)) if avgcol else None
            if costcol and avg is not None and numeric(row.get(costcol)) is not None:
                r[costcol] = reformat(row[costcol], q * avg)
            # Absolute gain follows from value − cost, never from its own scaling.
            gcol = pick_column([h for h in keep if h not in (valcol, costcol)],
                               ("gain/loss", "gain", "change", "profit/loss"),
                               exclude=("%", "day", "today", "price"))
            nv, nc = numeric(r.get(valcol)) if valcol else None, \
                     numeric(r.get(costcol)) if costcol else None
            if gcol and nv is not None and nc is not None and numeric(row.get(gcol)) is not None:
                r[gcol] = reformat(row[gcol], nv - nc)
        out_rows.append(r)

    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"(?i)\.example$", "", stem)
    dest = os.path.join(out_dir, f"{stem}{suffix}")
    os.makedirs(out_dir, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keep)
        w.writeheader()
        w.writerows(out_rows)

    print(f"  {os.path.basename(path)} → {os.path.basename(dest)}")
    print(f"      scaled:   {', '.join(scaled) or '(none)'}")
    print(f"      unchanged:{' ' + ', '.join(h for h in keep if h not in scaled)}")
    if drop:
        print(f"      DROPPED:  {', '.join(drop)}")
    if redacted:
        print(f"      redacted: {redacted} identifier-shaped cell(s)")
    return dest


def scale_ledger(path, factor, out_dir, suffix):
    """The gate ledger carries Qty, which leaks sleeve size just as the exports do.

    Prices, gate results and notes are untouched — they are the entire point of the
    ledger and none of them disclose position size.
    """
    if not os.path.exists(path):
        print(f"  ledger not found: {path}")
        return None
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    heads = list(rows[0].keys())
    qcols = [h for h in heads if norm_header(h) in ("qty", "quantity", "units", "shares")]
    for row in rows:
        for h in qcols:
            n = numeric(row.get(h))
            if n is not None:
                row[h] = reformat(row[h], n * factor, min_dec=2)
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"(?i)\.example$", "", stem)
    dest = os.path.join(out_dir, f"{stem}{suffix}")
    os.makedirs(out_dir, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=heads)
        w.writeheader()
        w.writerows(rows)
    print(f"  {os.path.basename(path)} → {os.path.basename(dest)}  (scaled: "
          f"{', '.join(qcols) or 'nothing'})")
    return dest


def main():
    ap = argparse.ArgumentParser(
        description="Scale real broker exports to a nominal sleeve NAV for publication.")
    ap.add_argument("files", nargs="+", help="Real broker export CSV(s)")
    ap.add_argument("--target-nav", type=float, default=100_000.0,
                    help="Nominal sleeve total. Default 100000 — the figure the rules "
                         "files already use in their worked examples.")
    ap.add_argument("--ledger", default=None,
                    help="Also scale a gate ledger's Qty column by the same factor.")
    ap.add_argument("--out-dir", default=None,
                    help="Where to write. Default: input/ next to this repo.")
    ap.add_argument("--suffix", default=".public.csv",
                    help="Output suffix. Default .public.csv — committed by .gitignore "
                         "and treated by the radar as real holdings. Distinct from "
                         "*.example.csv, which means the bundled demo data and makes "
                         "the radar print a DEMO warning.")
    a = ap.parse_args()

    files = [f for f in a.files if os.path.exists(f)]
    if not files:
        print("no readable input files", file=sys.stderr)
        raise SystemExit(1)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = a.out_dir or os.path.join(root, "input")

    total = sleeve_total(files)
    if total <= 0:
        print("could not read a sleeve total — no value or qty×price columns found.",
              file=sys.stderr)
        raise SystemExit(1)
    factor = a.target_nav / total

    print(f"sleeve total read from {len(files)} file(s)")
    print(f"scaling to a nominal {a.target_nav:,.0f} — factor printed here and written "
          f"nowhere:\n    ×{factor:.6f}\n")

    for path in files:
        scale_csv(path, factor, out_dir, a.suffix)
    if a.ledger:
        scale_ledger(a.ledger, factor, os.path.dirname(a.ledger) or ".", a.suffix)

    print(f"\nDone. Before committing, check the output:")
    print(f"  · no absolute figure matches your real account")
    print(f"  · percentages are untouched (they should be — they are not scaled)")
    print(f"  · no column you recognise as identifying survived")
    print(f"\nThen regenerate output/ from the scaled files, or the reports will still")
    print(f"carry the real numbers:")
    print(f"  python3 engine/heartbeat_radar.py && python3 tools/facts.py \\")
    print(f"    && python3 tools/pnl.py")


if __name__ == "__main__":
    main()
