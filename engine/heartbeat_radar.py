#!/usr/bin/env python3
"""
Heartbeat Radar v2 — momentum-style pattern screen over the portfolio universe.

CHANGES FROM v1 (26 Jul 2026)
  1. HEARTBEAT is now volatility-adjusted. v1 used a fixed "20-day range <= 7%",
     which structurally only ever fired on ETFs and defensive staples — a high-beta
     name cannot print a 7% 20-day range even when it is coiling tightly *by its own
     standards*. v2 ranks the current 20-day range against that name's own 1-year
     distribution of 20-day ranges and fires when it sits in the bottom quartile.
  2. Volume flags now carry DIRECTION and a 5-session window. v1 read a single bar
     and could not tell accumulation from distribution. v2 emits VOL-2X-UP /
     VOL-2X-DOWN, reports how many sessions ago, and adds a 20-day accumulation
     ratio (up-day volume / down-day volume).
  3. RELATIVE STRENGTH added. Every v1 metric was the stock against its own moving
     average; nothing measured it against the market. v2 computes a blended excess
     return vs a currency-matched benchmark (SPY for USD, ISF.L for GBp/GBP) over
     3/6/12 months and percentile-ranks it across the universe. RS-LEADER >= 80th.
  4. Recent listings are no longer silently discarded. v1 required 160 sessions and
     dumped everything shorter into the failure bucket — precisely where new movers
     live. v2 falls back to a 50-day primary line (marked "50d*") for names with
     60-159 sessions, and reports shorter ones as TOO-NEW rather than dropping them.
  5. Liquidity annotation (LOW-LIQ) instead of exclusion — a huge volume ratio on a
     near-zero base is a measurement artifact, not a signal.
  6. 52-week high proximity column + NEAR-52W-HIGH flag (feeds pre-entry validation).
  7. Holdings awareness — reads the holdings CSVs and annotates HELD + % vs cost.
  8. State file (radar_state.json) — flags new since the previous run natively, so
     "what changed today" no longer needs a manual file diff.
  9. Staleness check — reports each name's last bar date and warns when a name lags
     the rest of the universe.

CHANGES (26 Jul 2026)
  10. RRG-style sector rotation, gated behind --rrg. The 25 Jul "Rotation read" clusters
      flags (HEARTBEAT/breakout vs round-trip/below-line) — fast, but a flag count is a
      tactical readout that can flip within days. This adds a slower, strategic layer on
      top of the RS machinery already computed per ticker: each sector's avg RS percentile
      (level, vs the whole universe) and the change in avg raw RS score since the last
      --rrg snapshot (momentum), classified into Leading/Weakening/Improving/Lagging
      quadrants, with quadrant-shift flags vs the prior snapshot. State lives in its own
      file (sector_rrg_state.json) so it never touches the daily radar_state.json, and the
      section is only appended when --rrg is passed — the existing weekday schedule
      (heartbeat-radar, 15:30 Mon-Fri) is untouched. Intended cadence: weekly, run with
      --rrg on Sundays.

  11. Universe split (26 Jul 2026). radar_universe.md is now DISCOVERY ONLY — names
      surfaced by the fundamentals screener that are not held and not on a watchlist. Held
      positions are injected at runtime from the holdings CSVs via ROSTER, so a
      holding can never lose its 150-day exit line and ROUND-TRIP-RISK coverage because
      someone forgot to edit a text file (two live holdings had exactly that gap).
      Watchlist names are deliberately NOT screened: the sleeve evaluations already
      cover every watchlist name with the full fundamentals + chart stack under the
      roster contract, so duplicating them here bought nothing and inflated the file.
      This also matters for the RRG — a mutable membership list feeding a week-over-week
      differencing calculation makes composition drift indistinguishable from rotation.

  12. Inputs are markdown, not plain text (26 Jul 2026): radar_universe.md and
      sector_map.md are read as markdown tables via md_table_rows(), so they render
      readably in an editor and match the format the watchlists already use.

CHANGES (12 Aug 2026)
  13. Zero-config inputs. The script no longer has to be edited to run. HOLDINGS_SOURCES,
      WATCHLIST_SOURCES and ROSTER — three tables a new user had to fill in inside this
      file before the first run produced anything — are gone, replaced by runtime
      detection: holdings and watchlist files are globbed from input/, broker column
      names are matched against header candidates, and the Yahoo ticker is resolved from
      the exchange tag in the instrument name, then sector_map.md, then the trading
      currency. The setup was a programming task standing in front of a screening tool.

      Inference is constrained by three rules, none of which are optional:
        · every inference prints its basis on the run, so a wrong guess is visible;
        · sector_map.md overrides any of them — an input file, not code;
        · an inferred ticker that fails to fetch is retried in its other plausible
          form (bare <-> .L) before being written off, so a bad guess self-corrects
          against the price feed rather than becoming a holding with no exit line.
      The day-move column is explicitly excluded from gain-column matching: every
      broker ships one next to the total-gain column under a near-identical name, and
      picking it silently turns every gain figure in the report into a one-day move.

  14. First-run bootstrap. Missing folders, the gate ledger and an empty universe.md are
      created on the first run instead of being manual copy steps in the README. A setup
      step that can be automated and isn't is a step that gets skipped, and a missing
      ledger fails silently — the gates still run, the decisions just stop being recorded.

  15. universe.md is now optional. The radar screens holdings and watchlists without it.

CHANGES (15 Aug 2026)
  16. Rotation read hardening, three fixes:
      a. Conflicted names (arriving AND leaving, e.g. HEARTBEAT + BELOW-RISING-LINE) are
         counted in both In and Out and flagged as conflicted instead of being forced to
         one side. ROUND-TRIP-RISK still overrides the arrive side unchanged.
      b. Size-normalised thresholds. IN needs arriving >= max(2, 20% of the sector
         roster); OUT needs leaving >= max(3, 20%). Sectors of <=10 names behave exactly
         as before; bigger sectors need proportionally more names before the read calls
         it a rotation, so a 30-name sector with 3 arrivals is no longer equated with a
         2-name sector where both names are basing.
      c. Gauge confirmation column. Each tagged sector's bellwether ETF (from sector_map.md)
         votes on the tag: CONFIRMED when the ETF sits on the tag's side of its 150d,
         CONFLICT when it does not. A flags-only ROTATION-IN against a failing gauge is
         now surfaced as a contradiction rather than passing silently.

CHANGES (16 Aug 2026)
  17. Rotation read overhaul — twelve changes, integrated as one rewrite of the
      rotation read in main(). Documented together because they share state and a single
      field-extended history file (`rotation_history.json`).

      Tier 1 — close the blind spots:
      a. Phase split. Arrivals are now split into EARLY (HEARTBEAT) and LATE (AT-BREAKOUT);
         an IN tag carries STRONG-IN when early > late (rotation has further to run) or
         CHASING when late > early (rotation is mature). Same name column in the report,
         two columns in the read.
      b. MIXED / EXHAUSTED half-states. A sector with both arriving and leaving counts
         >= 2 (or >30% round-trips) reads MIXED instead of dropping into "-" — the most
         informative mid-state was previously invisible. MIXED is its own tag, not a label
         for an IN/OUT with caveats.
      c. Single-stock sectors. Sectors with 1-2 screened members now have an `in_min`
         floor of 1, with a CONFIRMING gauge required (sector_map.md bellwether above its
         rising 150-day). Healthcare and Rail were structurally unreachable before this.
      d. Speed. The trend column adds ACCELERATING / DECELERATING for IN tags (Δscore
         vs 3-run mean) and FADING-OUT / EXHAUSTED for OUT tags (leaving magnitude
         vs 3-run mean). STRENGTHENING/FADING retained as the in/out ratio of magnitudes.

      Tier 2 — gauge is load-bearing:
      e. Gauge verdict enforcement. Three consecutive CONFLICTING gauges auto-demote the
        current IN/OUT tag to MIXED until the gauge recovers. "CONFLICTING" is relative to
        the tag — for an OUT tag a FALLING bellwether agrees, and a rising one contradicts
        (fixed 2026-08-23; it was IN-relative for both, so an exit read was demoted for
        being corroborated). Conflict streak is persisted in the history file so re-runs do
        not reset it — also true only since 2026-08-23: the reader asked for a key named
        `gauge` and the writer stored `gauge_for_in`, so the streak silently reset every
        run and this demotion had never fired. The streak counts consecutive
        contradicting runs *ending today*: a gauge that agrees today returns 0
        whatever it did before, because Tier 2e demotes only until the gauge
        recovers (23.4), and today's own record is skipped when walking history
        because `rotation_persistence()` has already written it (23.5 — before
        that every streak read one high, so this fired on 2 runs, not 3).
        Reported in the Gauge column as `CONFLICT(3)` and metering.
      f. Gauge velocity. Added to the existing 20d momentum column: arrows now STRONG
        (>+5%), UP (+1% to +5%), FLAT (-1% to +1%), DOWN (-5% to -1%), WEAK (<-5%).

      Tier 3 — replace binary with intensity:
      g. Scoring rubric. IN/OUT are now scored: `score = in - 2*out + 0.5*(early-late) +
         0.3*gauge_momentum`. tag IN when score >= 1 AND arrivals >= floor. The old "more
        than 2x" ratio rule is preserved as a hard floor below the score. Same for OUT
        with signs flipped.
      h. OUT-tag intensity track. OUT-FADING vs OUT-EXHAUSTED — FADING-OUT when leaving
        magnitude is shrinking vs 3-run mean (the trade's winding down), EXHAUSTED when
        leaving magnitude has shrunk past a threshold (close to re-IN eligibility).
      i. Gap columns. Two new columns report `gap-to-IN` and `gap-to-OUT` (how many
        names away from the next tag in each direction), so a name one away from flipping
        is visible.

      Tier 4 — vocabulary:
      j. The Tag column emits one of **ROTATION-IN** / **STRONG-IN** / **CHASING** /
        **MIXED** / **ROTATION-OUT** / **FADING-OUT** / **EXHAUSTED** / **—**
        (**SUSTAINED** joined them on 22 Aug 2026 — see change 17). Impact
        on gates is taken forward into rules/02_SLEEVE_RULES.md (the ETF card gate 1
        accepts IN, STRONG-IN; demotes CHASING to a warning; rejects MIXED/FADING/EXHAUSTED
        outright).
      k. Conflicted names surface in the table itself (a ⚠ column), not just the footer —
        reading "this name is in both columns" used to require a footnote scan.
      l. Bellwether fetch failures get a sector-level ERROR verdict on the gauge column,
        not a missing column; missing gauges stop the tag (gauge-required).

CHANGES (13 Aug 2026)
  16. Currency is inferred from the line's OWN money columns, not from a scan of the
      whole row. row_currency() previously joined every cell in a holding's row and
      looked for a £ — but a UK broker ships a base-currency conversion NEXT TO the
      native column ("Market Value £" beside "Market Value"), populated on every row.
      So every holding in the file read as sterling, every US line got a .L suffix,
      and JCI.L / NTAP.L / TEVA.L 404'd against the price feed. The ALT_FORM retry
      caught them, so the report was right — at the cost of two fetches per name and
      a "priced in GBP" basis line that was false for 16 of 26 holdings.

      This is the same failure as the day-move column in GAIN_EXCLUDE, one column
      over: the wrong column is adjacent, plausible, and always populated. The fix is
      the same shape — an ordered candidate list (NATIVE_MONEY_HEADERS) with an
      exclusion list for headers that name a currency (CONVERTED_HEADER_MARKERS).

      `price` leads the candidate list because it alone separates GBp from GBP: a
      book cost is totalled in pounds even for a stock quoted in pence, so Chemring's
      "£4,994.64" says sterling without saying which sterling — while its "622.00p"
      price says LSE outright. cell_currency() therefore returns GBp, not GBP, for
      the pence form.

      A USD-priced LSE line (QQQ3.L, a leveraged ETP) is still unresolvable by any
      currency heuristic and self-corrects via ALT_FORM. sector_map.md is the fix for
      those, and the run log names them.

CHANGES (22 Aug 2026)
  17. SUSTAINED — the continuation state (backlog item 5, the gold/silver miss).
      The rotation read had exactly two verbs: arriving (HEARTBEAT / AT-BREAKOUT)
      and leaving (ROUND-TRIP-RISK / BELOW-RISING-LINE). A sector already moving
      was in neither column, and the renderer skipped any sector with no activity
      on either side — so it produced NO ROW AT ALL. On 20 Aug that silence was
      43% of a 114-name file, including the three highest-RS names on the board
      and four of the five gold names. Gold scored `in: 0` on 18 consecutive runs
      while its own gauge momentum column read +22%, and a maximum-score gate card
      on KNT.TO was held at WAIT citing "Gold not tagged".

      A name is SUSTAINED when the geometry is intact (above a rising primary
      line, past the breakout box or within 10% of the 52-week high) AND both
      continuous measures agree it is still being bought (`acc` and `rs_pctl` at
      or above the universe median). Two limbs, because geometry alone would
      re-describe the price — `EXTENDED>BREAK` fires on anything 3% past its box
      including a name rolling over.

      Ranked against the universe, never thresholded — the same decision item 3.3
      made and for the same reason. That is why membership is computed in the
      rotation section rather than in analyse(): the distribution does not exist
      until every name is fetched.

      CONTAINMENT, because this is live gate logic. SUSTAINED is applied LAST and
      only to a sector that would otherwise read `-`; arrivals, departures, MIXED
      and the sparse-cluster gauge fallback all outrank it. It needs 2+ names and
      at least half the sector. The scoring rubric stays FLAGS-ONLY — the first
      cut added the cohort to `score_in` as the diagnosis suggested, and a
      containment test showed it could flip an 8-leaving Defence cluster from
      EXHAUSTED to MIXED, so the cohort now reaches a tag through exactly one
      door and touches the reported score only for SUSTAINED sectors. No quantity of
      sustained names can manufacture a ROTATION-IN, nor weaken an exit tag. It
      does not lift the doubled ETF cap: a continuation is already extended, and
      passing a thesis gate is not the same as authorising double size.

Usage:  python3 heartbeat_radar.py [--universe tracking/universe.md] [--out radar.md]
                                    [--rrg] [--rrg-state sector_rrg_state.json]
Inputs:  input/*.csv                       broker exports — the only required input
         input/watchlist.md                optional candidate registry (or watchlist_*.md for splits)
         input/tracking/sector_map.md     optional ticker → sector, authoritative where present
         input/tracking/universe.md       optional discovery names | Ticker | Source | Notes |
"""

import json, sys, tempfile, time, urllib.request, datetime, argparse, os, csv, re, glob, shutil
from concurrent.futures import ThreadPoolExecutor

MIN_FULL   = 160        # sessions needed for a 150-day line
MIN_SHORT  = 60         # sessions needed for a reduced (50-day) read
LOWLIQ_USD = 3_000_000  # 60-day avg dollar volume below this => LOW-LIQ
COIL_PCTL  = 25.0       # 20-day range must sit in bottom quartile of its own year
COIL_ABS   = 25.0       # ...and still be under this in absolute terms
RS_LEADER  = 80.0       # RS percentile at/above which we tag RS-LEADER

# ---- SUSTAINED: the continuation state (backlog item 5) --------------------
# The rotation read could see a sector ARRIVING (HEARTBEAT / AT-BREAKOUT) and a
# sector LEAVING (ROUND-TRIP-RISK / BELOW-RISING-LINE) and had no vocabulary at
# all for one already moving. On 20 Aug 2026 that was 43% of a 114-name file,
# including four of the five gold names, and the Gold cluster scored `in: 0` on
# 18 consecutive runs while its own gauge momentum read +22%.
#
# A name is SUSTAINED when the geometry says the move is intact AND the two
# continuous measures this file already computes agree that it is still being
# bought. Both limbs are required: geometry alone re-describes the price, and
# `EXTENDED>BREAK` fires on any name 3% past its box including one rolling over.
SUS_ACC_PCTL = 50.0     # accumulation must be at/above the universe median
SUS_RS_PCTL  = 50.0     # ...and so must relative strength
SUS_WEIGHT   = 0.35     # per-name contribution to score_in. TIEBREAK ONLY:
                        # `in_floor_passes`/`in_ratio_passes` still count real
                        # arrivals, so no quantity of sustained names can
                        # manufacture a ROTATION-IN. See classify().
VOL_WINDOW = 5          # sessions to scan for a volume spike
FX_FALLBACK = 1.34      # GBP->USD if the FX fetch fails

# NO PER-SECTOR DISCOVERY CAP (retired 2026-08-23). `DISCOVERY_CAP = 8` lived here
# from 26 Jul 2026 and warned — never trimmed — when one sector held more than eight
# tracking names. Its job was to stop a sector sweep flooding the screen and corrupting
# the RS percentile scale, back when the rotation read was a COUNT of member flags and
# a lopsided pool really did move the answer. Bellwether ETFs supply sector direction
# now (docs/BACKLOG.md item 23), so pool size no longer steers the read and the cap was
# retired in the docs — CONFIG.md, input/README.md and input/tracking/universe.md all
# said so from 23 Aug while this constant went on firing, which is drift, not policy.
# What remains is a FLOOR, not a cap, and it lives in input/tracking/sector-coverage.md:
# a sector with fewer than three screened members needs its bellwether to confirm before
# its own members can carry an exit read.
#
# NOTE on speculatives (26 Jul 2026, kept because it outlived the cap). An earlier version
# gave each sector two "speculative exemption slots" inside the cap. That was incoherent:
# sector rotation is about the large movement of funds, whereas a speculative is
# idiosyncratic and can come from anywhere, so per-sector slots either arbitrarily cap it
# or arbitrarily license it. It was also unnecessary — the sleeve rules route speculative
# names into the watchlist tagged SPECULATIVE, and watchlist names are auto-derived. What
# a speculative does need is separation from the RS percentile ranking, handled where
# rs_pctl is computed.

# Holdings roster: broker CSV symbol -> (Yahoo ticker, @Sector).
#
# Why this lives in code rather than in radar_universe.md (26 Jul 2026): the universe
# file is now *discovery only* — sweep-sourced names that are not yet on a watchlist.
# Holdings must still be screened every run, because the 150-day exit line and
# ROUND-TRIP-RISK are computed from price history and are the sleeve's actual exit
# mechanism; they cannot be eyeballed off a chart at equivalent precision. Injecting
# them from the CSVs removes the hand-sync that had already lost two live holdings
# (~a material sum held with zero radar coverage until this change).
#
# Broker symbols don't map cleanly to Yahoo (some ETFs quote in USD but are LSE
# lines, so a currency heuristic misfires) and the roster is a few dozen stable names, so an
# explicit table is more reliable than inference. Add a line when you open a position.
# ---------------------------------------------------------------------------
# PATHS
#
# Everything you edit lives under input/. Everything generated lives under output/.
# Both can be overridden with --input-dir / --output-dir, or the TP_INPUT / TP_OUTPUT
# environment variables, so the same script serves several sleeves.
ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR  = os.environ.get("TP_INPUT",  os.path.join(ROOT, "input"))
OUTPUT_DIR = os.environ.get("TP_OUTPUT", os.path.join(ROOT, "output"))

# ---------------------------------------------------------------------------
# INPUT AUTO-DETECTION (12 Aug 2026)
#
# Nothing in this file needs editing to run. Drop a broker CSV in input/,
# run the script, read output/radar/Heartbeat_Radar_<date>.md. Column names,
# Yahoo tickers and
# sectors are all worked out at runtime.
#
# WHY THIS REPLACED HAND-EDITED CONFIG. The previous version required a new user to
# edit three tables in this 1,100-line file — HOLDINGS_SOURCES, WATCHLIST_SOURCES and
# ROSTER — before the first run would produce anything. That is a programming task
# standing in front of a screening tool, and it is the single biggest reason the repo
# was unusable without hand-holding.
#
# THE RULE THAT KEEPS THIS HONEST: every inference is printed, with its basis, on
# every run. Nothing is guessed silently. A wrong guess is visible in the run log and
# overridable by adding a row to input/sector_map.md — an input file, not code.
# Inference is never allowed to *drop* a name: an unresolvable symbol is reported.
#
# Header candidates. Matching is case- and punctuation-insensitive and substring-based.
TICKER_HEADERS = ("symbol", "ticker", "epic", "instrument code", "code")
NAME_HEADERS   = ("investment name", "instrument name", "security name", "name",
                  "investment", "description", "title", "security", "holding",
                  "instrument", "stock")
GAIN_HEADERS   = ("total gain/loss %", "gain/loss %", "gain %", "profit/loss %",
                  "return %", "change (%)", "change %", "% change", "% gain",
                  "unrealised %", "unrealized %", "gain/loss", "change")

# Headers containing any of these are NEVER the total-gain column. Brokers ship a
# day-move column with a near-identical name — "Day Gain/Loss %" sits next to
# "Gain/Loss %", "Price +/- today (%)" next to "Change (%)" — and silently picking it
# turns every gain figure in the report into a one-day move. Both example exports in
# input/ contain this trap, which is why it is an exclusion list and not a
# tiebreak.
GAIN_EXCLUDE   = ("day", "today", "1d", "daily", "24h")

CURRENCY_HEADERS = ("market currency", "trading currency", "currency", "ccy")

# Money columns quoted in the line's OWN currency, most trustworthy first. Where the
# export has no currency column, the symbol in these cells is the currency — "$6.20",
# "622.00p" and "£31.335" each say it outright, and the pence form says specifically
# that it is an LSE line.
#
# `price` leads because it alone distinguishes GBp from GBP: a book cost is totalled
# in pounds even for a stock quoted in pence, so £4,994.64 of Chemring says sterling
# without saying which sterling, and the .L suffix question needs the answer.
NATIVE_MONEY_HEADERS = ("price", "book cost", "average price", "market value",
                        "cost", "value")

# ...and the trap that makes the above an ordered list rather than a blob scan. Brokers
# ship a base-currency conversion NEXT TO the native column, distinguished only by a
# symbol or code in its own header: "Market Value £" beside "Market Value". Reading
# every cell in the row finds that £ on every line of the file and concludes the whole
# account is sterling — which appends .L to every US holding, and the resulting
# NTAP.L / JCI.L / TEVA.L 404 against the price feed. Same failure as the day-move
# column in GAIN_EXCLUDE: the wrong column is adjacent, plausible, and always populated.
CONVERTED_HEADER_MARKERS = ("£", "$", "€", "¥", "gbp", "usd", "eur", "jpy",
                            "sterling", "base", "converted", "local")

# Exchange tag → Yahoo suffix. Many brokers write the venue into the instrument name
# as "(LSE:VOD)" or "NASDAQ:NVDA", which is a far more reliable signal than any
# currency heuristic: an ETF can quote in USD while being an LSE line.
EXCHANGE_SUFFIX = {
    "LSE": ".L", "LON": ".L", "LSEAIM": ".L", "AIM": ".L",
    "TSX": ".TO", "TSE": ".TO", "TSXV": ".V", "CVE": ".V",
    "ASX": ".AX", "XETRA": ".DE", "ETR": ".DE", "FRA": ".F",
    "EPA": ".PA", "AMS": ".AS", "BME": ".MC", "BIT": ".MI", "SWX": ".SW", "VTX": ".SW",
    "TYO": ".T", "TSE-JP": ".T", "HKG": ".HK", "STO": ".ST", "CPH": ".CO", "OSL": ".OL",
    "NASDAQ": "", "NYSE": "", "NYSEARCA": "", "ARCA": "", "AMEX": "", "BATS": "", "OTC": "",
}

# Dollar symbols that are not the US dollar, longest-prefix first. A broker writes
# the disambiguating letters and nothing else — "CA$", "A$", "HK$" — so the letters
# are the entire signal.
DOLLAR_PREFIXES = (("CA$", "CAD"), ("AU$", "AUD"), ("HK$", "HKD"),
                   ("NZ$", "NZD"), ("SG$", "SGD"), ("A$", "AUD"), ("S$", "SGD"))

# Sterling markers. GBp (pence) is the LSE quoting convention; a holding priced in it
# is an LSE line whatever else the export says.
GBP_MARKERS = ("GBP", "GBX", "GBP.", "PENCE", "STERLING", "£")

# Rows with no fetchable price series. Skipped BY DESIGN, and counted in the run log
# so the skip is visible — OEICs, gilts, T-bills and cash have no daily bars to screen.
NON_SCREENABLE = ("FUND:", "SEDOL:", "ISIN:", "CASH", "GILT", "TREASURY BILL", "T-BILL")

# Populated during resolution: inferred_ticker -> alternate form to retry if the
# inferred one fails to fetch. This is what makes auto-detection safe to rely on —
# a bad guess self-corrects against the price feed instead of vanishing into the
# failure bucket.
ALT_FORM = {}

# CURRENCY ASSERTION (19 Aug 2026). ALT_FORM only ever fired on a 404, which quietly
# assumes the wrong guess is an INVALID ticker. It is not always: bare GIGB is a live
# US investment-grade bond ETF ($45, NYSE Arca) and GIGB.L is the VanEck S&P Global
# Mining UCITS ETF (£50, LSE) that this account actually holds. Both fetch. So the
# radar screened a bond fund's price against a miner's exit line and printed a SELL,
# and nothing in the run failed — the report even said "45.07 USD" next to a holding
# whose broker row says £49.63, because no code compared the two.
#
# So the broker row's own currency is carried through resolution and asserted against
# what the feed returns. A currency disagreement is now treated exactly like a 404:
# retry the other form, adopt it only if IT agrees. Both are the same question — "is
# this the security the account holds?" — and a 404 is merely the loud version.
#
# Keyed by BOTH forms of a symbol, because the expectation belongs to the holding
# rather than to a spelling of its ticker, and the retry swaps the spelling.
EXPECTED_CUR = {}       # ticker -> "GBP" | "USD" | "EUR" | ... | ""
RESOLVED_FROM = {}      # ticker -> the broker symbol it came from


def cur_family(cur):
    """Normalise a currency to the unit a comparison can be made in.

    GBp and GBP are the same currency quoted differently — pence vs pounds — so they
    must compare EQUAL here even though `analyse` has to keep them distinct to scale
    the liquidity gate. Comparing the quote convention instead of the currency would
    make every pence-quoted LSE holding look like a mismatch.
    """
    c = str(cur or "").strip().upper()
    if not c:
        return ""
    if any(g in c for g in GBP_MARKERS):
        return "GBP"
    if "USD" in c or "$" in c:
        return "USD"
    if "EUR" in c or "€" in c:
        return "EUR"
    if "JPY" in c or "¥" in c:
        return "JPY"
    m = re.fullmatch(r"([A-Z]{3})", c)
    return m.group(1) if m else ""


def record_forms(primary, alternate, sym, currency):
    """Register both spellings of one holding: retry form, expected currency, origin.

    Called from every branch of resolve_ticker that commits to a ticker, so the feed
    check downstream never has to care which branch won or which spelling survived
    the retry.
    """
    fam = cur_family(currency)
    if alternate and alternate != primary:
        ALT_FORM[primary] = alternate
        ALT_FORM[alternate] = primary
    for t in (primary, alternate):
        if t:
            EXPECTED_CUR[t] = fam
            RESOLVED_FROM[t] = sym
    return primary


# ---------------------------------------------------------------- bar cache (item 16)
#
# WHY. Every run re-downloaded two years of daily bars for all ~135 tickers:
# 7.4 MB and 135 requests against an undocumented Yahoo endpoint, every day,
# forever. The bars for all but the last few sessions are identical each time.
#
# WHAT THIS IS NOT. It is not a speed optimisation and must not be sold as one.
# Pure compute over the full series is ~232 us/ticker (~31 ms for the whole
# universe, 0.8% of a run) and a request costs ~0.16 s whether it carries 501
# bars or 5. This buys bandwidth and API surface, not wall time. If wall time is
# the goal, raise the worker count.
#
# WHY NOT CHAIN THE RADAR SNAPSHOTS INSTEAD. That was the obvious idea and it
# fails: the snapshot stores derived scalars, so there is no raw daily volume to
# rebuild `acc` from and no high/low at all; and warm-up (~272 bars, ~13 months)
# would recur for every newly added name, permanently splitting the universe
# into readable and unreadable halves. Caching raw bars keeps the property that
# matters — a brand-new ticker is fully readable on its FIRST run, because a
# cache miss is just a normal full fetch.
#
# THE SPLIT CHECK IS THE LOAD-BEARING PART. Yahoo's `quote.close` is
# split-adjusted, so a split retroactively rewrites a name's entire history. An
# append-only cache would silently keep the pre-split prices, and `acc`,
# `rng_pctl` and `rs` would inherit the corruption with no visible error. Every
# incremental fetch therefore re-verifies the bars that overlap the cache; any
# disagreement discards the cache and refetches in full. Cheap, and it cannot be
# bolted on after the first bad day.

BARS_SCHEMA = "radar_bars/1"
BARS_KEEP = 600          # bars retained per ticker (~2.4y). Every window the
                         # radar uses is tail-anchored and <= 272 bars, so this
                         # is comfortably deep; capping it bounds the store.
BARS_DRIFT_TOL = 0.002   # 0.2% — a split is >= 2x, so this is not a close call.
BARS_DIR = None          # set by main(); None disables the cache entirely.
BARS_REFRESH = False     # --refresh-bars: ignore what is cached, refetch in full.

# Counters for the one-line run summary. Each ticker is touched by exactly one
# worker thread, and every mutation below is a `+=` on an int under the GIL from
# a distinct key's code path; the totals are for reporting only.
BARS_STAT = {"hit": 0, "full": 0, "incr": 0, "repair": 0, "bytes": 0, "corrupt": 0}
_BARS_NOTE = []          # (ticker, message) — printed after the fetch pass


def _bars_path(ticker):
    """Cache file for `ticker`, or None if the cache is off.

    The filename is sanitised (`GBPUSD=X`, `BRK-B`, `KNT.TO` are all legal
    tickers, `=` and `^` are not portable in filenames), so two tickers could in
    principle collide on one path. The payload therefore carries its own
    `ticker` and a mismatch is treated as a miss — a collision costs a refetch,
    never a wrong price series.
    """
    if not BARS_DIR:
        return None
    safe = re.sub(r"[^A-Za-z0-9.\-]", "_", ticker)
    return os.path.join(BARS_DIR, f"{safe}.json")


def _bars_load(ticker):
    path = _bars_path(ticker)
    if not path or BARS_REFRESH:
        return None
    try:
        with open(path) as f:
            d = json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        BARS_STAT["corrupt"] += 1
        _BARS_NOTE.append((ticker, "cache unreadable — refetched in full"))
        return None
    if d.get("schema") != BARS_SCHEMA:
        return None                     # routine migration, not worth a line
    if d.get("ticker") != ticker:
        # Two tickers sanitising to one filename. Refetching is correct and safe,
        # but it would recur every run forever, so say so rather than absorbing
        # the cost silently.
        _BARS_NOTE.append((ticker, f"cache file holds {d.get('ticker')!r} — filename "
                                   f"collision; refetched in full"))
        return None
    n = len(d.get("ts") or [])
    if n < 2 or any(len(d.get(k) or []) != n for k in ("o", "h", "l", "c", "v")):
        BARS_STAT["corrupt"] += 1
        _BARS_NOTE.append((ticker, "cache arrays disagree on length — refetched in full"))
        return None
    return d


def _bars_store(ticker, bars):
    path = _bars_path(ticker)
    if not path:
        return
    keep = BARS_KEEP
    try:
        _atomic_write_json(path, {
            "schema": BARS_SCHEMA, "ticker": ticker, "cur": bars["cur"],
            "fetched": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "n": len(bars["ts"][-keep:]),
            "ts": bars["ts"][-keep:], "o": bars["o"][-keep:],
            "h": bars["h"][-keep:], "l": bars["l"][-keep:],
            "c": bars["c"][-keep:], "v": bars["v"][-keep:],
        }, indent=None)
    except Exception:
        # A cache that cannot be written must not fail the run: the series in
        # hand is correct and complete, it simply will not be reused tomorrow.
        _BARS_NOTE.append((ticker, "cache not written"))


def _yahoo(ticker, rng, retries=2):
    """One chart request. Returns (bars, None) or (None, error-string).

    `bars` is parallel arrays plus the currency the FEED reports — never the
    cached currency. A symbol silently changing currency is a different
    security (the GIGB case), and that check has to see live data to work.
    """
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={rng}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for i in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
            BARS_STAT["bytes"] += len(raw)
            d = json.loads(raw)
            res = d["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            b = {"ts": [], "o": [], "h": [], "l": [], "c": [], "v": [],
                 "cur": res["meta"].get("currency", "")}
            for k, t in enumerate(res["timestamp"]):
                c = q["close"][k]
                if c is None:
                    continue
                b["ts"].append(t)
                b["c"].append(c)
                b["v"].append(q["volume"][k] if q["volume"][k] is not None else 0)
                # high/low/open are carried for consumers that want true range;
                # they fall back to the close so downstream code never sees None.
                b["o"].append(q.get("open", [None] * (k + 1))[k] if q.get("open") else c)
                b["h"].append(q.get("high", [None] * (k + 1))[k] if q.get("high") else c)
                b["l"].append(q.get("low", [None] * (k + 1))[k] if q.get("low") else c)
            for k in ("o", "h", "l"):
                b[k] = [x if x is not None else b["c"][j] for j, x in enumerate(b[k])]
            if not b["ts"]:
                return None, "no bars in response"
            return b, None
        except Exception as e:
            if i == retries:
                return None, str(e)
            time.sleep(1.5)


def _bars_window(last_ts):
    """How far back to ask, given the newest cached bar.

    Deliberately generous: the incremental window must comfortably straddle the
    gap so that overlapping bars exist to verify against. No overlap means no
    split check, and the merge below refuses to run without one.
    """
    gap = (time.time() - last_ts) / 86400.0
    if gap <= 4:    return "5d"
    if gap <= 20:   return "1mo"
    if gap <= 80:   return "3mo"
    if gap <= 340:  return "1y"
    return None     # too far behind to trust an increment — refetch in full


def _bars_merge(ticker, old, fresh):
    """Splice `fresh` onto `old`, or return None if the cache cannot be trusted.

    Returns the merged bars, or None meaning 'discard the cache and refetch'.
    Two conditions force a refetch, and both are silent-corruption cases rather
    than errors:

      no overlap  — the windows do not touch, so there is nothing to verify and
                    splicing would leave a hole in the series.
      price drift — an overlapping bar disagrees, which means the history was
                    rewritten (a split, or a data correction upstream).

    The newest cached bar is excluded from the comparison on purpose: a run
    during market hours caches a provisional close that legitimately changes by
    the final print. It is overwritten, not audited.
    """
    old_ts = {t: i for i, t in enumerate(old["ts"])}
    overlap = [t for t in fresh["ts"] if t in old_ts]
    if not overlap:
        _BARS_NOTE.append((ticker, "no overlap with cached bars — refetched in full"))
        return None
    newest_cached = old["ts"][-1]
    for t in overlap:
        if t == newest_cached:
            continue          # provisional close; fresh data wins, no audit
        a = old["c"][old_ts[t]]
        b = fresh["c"][fresh["ts"].index(t)]
        if a and abs(b - a) / abs(a) > BARS_DRIFT_TOL:
            BARS_STAT["repair"] += 1
            _BARS_NOTE.append((ticker,
                f"price history rewritten (bar {datetime.date.fromtimestamp(t)}: "
                f"{a:.4f} -> {b:.4f}) — very likely a split; refetched in full"))
            return None
    keep_to = fresh["ts"][0]
    merged = {"cur": fresh["cur"]}
    cut = next(i for i, t in enumerate(old["ts"]) if t >= keep_to)
    for k in ("ts", "o", "h", "l", "c", "v"):
        merged[k] = old[k][:cut] + fresh[k]
    return merged


def fetch_bars(ticker, retries=2):
    """Full OHLCV for `ticker`: (bars, None) or (None, error-string).

    Cache-aware. A miss, a stale-beyond-window entry, or any sign the cached
    history no longer matches the feed all collapse to the same safe fallback:
    a full 2y fetch, which is exactly what this function did before the cache
    existed. A network failure is still a failure — stale bars are NEVER served
    as if they were today's, because a name missing from the report is meant to
    be a bug you investigate, not a stale row you act on.
    """
    old = _bars_load(ticker)
    if old:
        rng = _bars_window(old["ts"][-1])
        if rng:
            fresh, err = _yahoo(ticker, rng, retries)
            if fresh is None:
                return None, err
            merged = _bars_merge(ticker, old, fresh)
            if merged is not None:
                BARS_STAT["incr"] += 1
                if merged["ts"][-1] == old["ts"][-1] and len(merged["ts"]) == len(old["ts"]):
                    BARS_STAT["hit"] += 1
                _bars_store(ticker, merged)
                return merged, None
        else:
            _BARS_NOTE.append((ticker, "cache too far behind — refetched in full"))
    bars, err = _yahoo(ticker, "2y", retries)
    if bars is None:
        return None, err
    BARS_STAT["full"] += 1
    _bars_store(ticker, bars)
    return bars, None


def bars_summary():
    """One line for the run log, plus any per-ticker notes."""
    s = BARS_STAT
    mb = s["bytes"] / 1e6
    return (f"[bars] {s['full']} full fetch · {s['incr']} incremental · "
            f"{s['repair']} history-rewrite repair · {s['corrupt']} unusable cache · "
            f"{mb:.2f} MB over the wire")


# ---------------------------------------------------------------- data fetch

def fetch(ticker, retries=2):
    """Return (closes, vols, currency, timestamps) or (None, None, err, None).

    The close/volume view of `fetch_bars`, kept because most callers (the
    benchmarks, the FX rate, the gauges) want nothing else. Anything needing
    high/low — item 16 makes them available for the first time — calls
    `fetch_bars` directly.
    """
    b, err = fetch_bars(ticker, retries)
    if b is None:
        return None, None, err, None
    return b["c"], b["v"], b["cur"], b["ts"]


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def ret(cl, n):
    return cl[-1] / cl[-1 - n] - 1 if len(cl) > n else None


# ---------------------------------------------------------------- mechanics

def range_percentile(closes, n=20, lookback=252):
    """Current 20-day close range, and where it sits in this name's own history.

    Returns (current_range_pct, percentile, sample_size). A low percentile means
    the name is quiet relative to how it normally behaves — which is the point:
    'tight' is not the same number for a high-beta name as it is for a broad index ETF.
    """
    seg = closes[-(lookback + n):] if len(closes) >= lookback + n else closes
    if len(seg) < n:
        return None, None, 0
    hist = [(max(seg[i - n:i]) / min(seg[i - n:i]) - 1) * 100
            for i in range(n, len(seg) + 1)]
    cur = hist[-1]
    pctl = 100.0 * sum(1 for h in hist if h <= cur) / len(hist)
    return cur, pctl, len(hist)


def volume_signal(closes, vols, v60):
    """Largest volume ratio in the last VOL_WINDOW sessions, plus its direction."""
    best_r, best_dir, best_ago = 0.0, None, None
    for k in range(1, min(VOL_WINDOW, len(vols) - 1) + 1):
        r = vols[-k] / v60 if v60 else 0.0
        if r > best_r:
            chg = closes[-k] / closes[-k - 1] - 1
            best_r, best_dir, best_ago = r, ("UP" if chg >= 0 else "DOWN"), k
    return best_r, best_dir, best_ago


def accumulation_ratio(closes, vols, n=20):
    """Up-day volume vs down-day volume over n sessions. >1 = net accumulation."""
    up = dn = 0.0
    for i in range(max(1, len(closes) - n), len(closes)):
        if closes[i] >= closes[i - 1]:
            up += vols[i]
        else:
            dn += vols[i]
    return (up / dn) if dn else None


def rs_score(cl, bench):
    """Blended excess return vs benchmark: 3m/6m/12m, recency-weighted."""
    tot = wsum = 0.0
    for n, w in ((63, 0.4), (126, 0.3), (252, 0.3)):
        a, b = ret(cl, n), ret(bench, n)
        if a is None or b is None:
            continue
        tot += w * (a - b) * 100
        wsum += w
    return (tot / wsum) if wsum else None


def gauge_analyse(closes, vols):
    # Compute the same flag vocabulary as analyse() for a bellwether gauge.
    # Skips RS percentile ranking (gauges cross-comparisons aren't meaningful),
    # LOW-LIQ (gauges are always liquid), held annotation, and currency conversion.
    if not closes or len(closes) < MIN_FULL:
        return None
    px = closes[-1]
    ma = sma(closes, 150)
    ma_prev = sma(closes[:-10], 150)
    ma50 = sma(closes, 50)
    ma50_prev = sma(closes[:-10], 50)

    def trend(now, prev):
        if now is None or prev is None:
            return "n/a"
        return "Rising" if now > prev * 1.001 else ("Falling" if now < prev * 0.999 else "Flat")

    trend_main = trend(ma, ma_prev)
    trend50 = trend(ma50, ma50_prev)
    above = px >= ma
    pct_to_line = (px / ma - 1) * 100

    lb = closes[-200:-10] if len(closes) >= 210 else closes[:-10]
    breakout = max(lb) if lb else px
    pct_to_break = (px / breakout - 1) * 100

    hi52 = max(closes[-252:]) if len(closes) >= 252 else max(closes)
    pct_from_hi = (px / hi52 - 1) * 100

    v60 = sum(vols[-60:]) / min(60, len(vols)) if vols else 0
    v20 = sum(vols[-20:]) / min(20, len(vols)) if vols else 0
    vratio, vdir, vago = volume_signal(closes, vols, v60)
    acc = accumulation_ratio(closes, vols)

    rng20, rng_pctl, _ = range_percentile(closes)

    coiled = (rng_pctl is not None and rng_pctl <= COIL_PCTL
              and rng20 is not None and rng20 <= COIL_ABS)
    heartbeat = coiled and v20 < v60 and above and trend_main == "Rising"

    flags = []
    if heartbeat:
        flags.append("HEARTBEAT")
    if -3.0 <= pct_to_break <= 3.0:
        flags.append("AT-BREAKOUT")
    if pct_to_break > 3.0:
        flags.append("EXTENDED>BREAK")
    if vratio >= 2.0:
        flags.append(f"VOL-2X-{vdir}")
    if not above and trend_main in ("Flat", "Falling"):
        flags.append("ROUND-TRIP-RISK")
    if not above and trend_main == "Rising":
        flags.append("BELOW-RISING-LINE")
    if pct_from_hi >= -10.0:
        flags.append("NEAR-52W-HIGH")

    return {"px": px, "ma": ma, "trend_main": trend_main, "trend50": trend50,
            "above": above, "pct_to_line": pct_to_line,
            "breakout": breakout, "pct_to_break": pct_to_break,
            "hi52": hi52, "pct_from_hi": pct_from_hi,
            "vratio": vratio, "vdir": vdir, "vago": vago, "acc": acc,
            "rng20": rng20, "rng_pctl": rng_pctl,
            "flags": flags}


def analyse(t, closes, vols, cur, ts, benches, fx):
    if not closes:
        return {"ticker": t, "error": "no data"}
    n = len(closes)
    if n < MIN_SHORT:
        return {"ticker": t, "error": f"too new ({n}d history)", "too_new": True,
                "px": closes[-1], "cur": cur, "n": n}

    px = closes[-1]
    full = n >= MIN_FULL
    ma_len = 150 if full else 50
    line_label = "150d" if full else "50d*"

    ma = sma(closes, ma_len)
    ma_prev = sma(closes[:-10], ma_len)
    ma50 = sma(closes, 50)
    ma50_prev = sma(closes[:-10], 50)

    def trend(now, prev):
        if now is None or prev is None:
            return "n/a"
        return "Rising" if now > prev * 1.001 else ("Falling" if now < prev * 0.999 else "Flat")

    trend_main = trend(ma, ma_prev)
    trend50 = trend(ma50, ma50_prev)
    above = px >= ma
    pct_to_line = (px / ma - 1) * 100

    lb = closes[-200:-10] if n >= 210 else closes[:-10]
    breakout = max(lb) if lb else px
    pct_to_break = (px / breakout - 1) * 100

    hi52 = max(closes[-252:]) if n >= 252 else max(closes)
    pct_from_hi = (px / hi52 - 1) * 100

    v60 = sum(vols[-60:]) / min(60, len(vols)) if vols else 0
    v20 = sum(vols[-20:]) / min(20, len(vols)) if vols else 0
    vratio, vdir, vago = volume_signal(closes, vols, v60)
    acc = accumulation_ratio(closes, vols)

    # approximate 60-day average dollar volume, for the liquidity gate only
    px_usd = px * fx / 100 if cur == "GBp" else (px * fx if cur == "GBP" else px)
    dollar_vol = px_usd * v60
    low_liq = dollar_vol < LOWLIQ_USD

    rng20, rng_pctl, rng_n = range_percentile(closes)

    # Session returns (backlog item 3.3). `ret()` counts BARS, not calendar days,
    # so `r20` is "20 of this name's own sessions" — exact per name, but a US name
    # and a .L name can span slightly different calendar windows when holidays
    # differ. That is already the convention everywhere else in this file
    # (`rs_score` uses 63/126/252 bars, `hi52` is `max(closes[-252:])`), so
    # consistency wins; just never describe the output as "since last Friday".
    def pct(n):
        v = ret(closes, n)
        return None if v is None else v * 100
    r5, r20, r60 = pct(5), pct(20), pct(60)

    bench = benches.get("GBP" if cur in ("GBp", "GBP") else "USD")
    rs = rs_score(closes, bench) if bench else None

    coiled = (rng_pctl is not None and rng_pctl <= COIL_PCTL
              and rng20 is not None and rng20 <= COIL_ABS)
    heartbeat = coiled and v20 < v60 and above and trend_main == "Rising"

    flags = []
    if heartbeat:
        flags.append("HEARTBEAT")
    if -3.0 <= pct_to_break <= 3.0:
        flags.append("AT-BREAKOUT")
    if pct_to_break > 3.0:
        flags.append("EXTENDED>BREAK")
    if vratio >= 2.0:
        flags.append(f"VOL-2X-{vdir}")
    if not above and trend_main in ("Flat", "Falling"):
        flags.append("ROUND-TRIP-RISK")
    if not above and trend_main == "Rising":
        flags.append("BELOW-RISING-LINE")
    if pct_from_hi >= -10.0:
        flags.append("NEAR-52W-HIGH")
    if low_liq:
        flags.append("LOW-LIQ")
    if not full:
        flags.append("NEW-LISTING")

    return {"ticker": t, "px": px, "cur": cur, "n": n, "full": full,
            "line_label": line_label, "ma": ma, "trend_main": trend_main,
            "trend50": trend50, "above": above, "pct_to_line": pct_to_line,
            "breakout": breakout, "pct_to_break": pct_to_break,
            "hi52": hi52, "pct_from_hi": pct_from_hi,
            "vratio": vratio, "vdir": vdir, "vago": vago, "acc": acc,
            "dollar_vol": dollar_vol, "low_liq": low_liq,
            "rng20": rng20, "rng_pctl": rng_pctl,
            "r5": r5, "r20": r20, "r60": r60,
            "rs": rs, "flags": flags, "last_ts": ts[-1] if ts else None}


# ---------------------------------------------------------------- input discovery

def norm_header(h):
    """Lowercase, collapse punctuation. 'Gain/Loss %' and 'GAIN / LOSS (%)' converge."""
    s = (h or "").lower().replace("(", " ").replace(")", " ")
    s = re.sub(r"[^a-z0-9%/+ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pick_column(headers, candidates, exclude=()):
    """Best-matching header, or None.

    Candidates are tried in order, most specific first, so 'total gain/loss %' wins
    over the looser 'gain'. Within one candidate, an exact match beats a substring
    match and the shortest header wins the remaining ties — brokers pad qualifiers
    onto the front of the column they consider secondary.
    """
    norm = {h: norm_header(h) for h in headers if h}
    live = {h: n for h, n in norm.items()
            if not any(x in n for x in exclude)}
    for cand in candidates:
        c = norm_header(cand)
        exact = [h for h, n in live.items() if n == c]
        if exact:
            return sorted(exact, key=len)[0]
        part = [h for h, n in live.items() if c in n]
        if part:
            return sorted(part, key=lambda h: (len(norm[h]), h))[0]
    return None


def read_csv_rows(path):
    """CSV rows as dicts. Tolerant of stacked BOMs and of a preamble above the header.

    utf-8-sig strips exactly one BOM, and at least one broker emits a run of them,
    which leaves the first header mangled so every lookup against it silently misses.
    Some exports also open with title/date lines before the real header row, so the
    header is located as the first line whose cells look like column names.
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        txt = f.read().replace("﻿", "")
    lines = txt.splitlines()
    start = 0
    for i, line in enumerate(lines[:15]):
        cells = next(csv.reader([line]), [])
        named = [c for c in cells if c.strip()]
        if len(named) >= 3 and pick_column(named, TICKER_HEADERS):
            start = i
            break
    return list(csv.DictReader(lines[start:]))


def account_label(path):
    """Short sleeve tag from the filename: holdings_a.csv -> A, ii-export.csv -> II."""
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"(?i)\.(example|public)$", "", stem)
    s = re.sub(r"(?i)^(holdings?|portfolio|positions?|export|account)[-_ ]*", "", stem)
    s = re.sub(r"[-_]+", " ", s or stem).strip()
    return (s[:8].upper() or "MAIN")


def discover_holdings_files():
    """Every CSV in input/. Falls back to the bundled examples.

    The example fallback is deliberate: a first run with an empty input folder
    that printed 'no holdings' and exited would leave a new user with no idea whether
    the tool works. Running the examples produces a real report they can read, and the
    run log says loudly that it is demo data.

    SUFFIX MEANINGS — the distinction matters, because one of them prints a warning
    that would be a lie about the other:
      *.example.csv  bundled demo data shipped with the repo. Used only when nothing
                     else is present, and flagged DEMO DATA on the run.
      *.public.csv   real positions scaled to a nominal NAV by tools/anonymise.py.
                     Real holdings — no warning. Committed.
      *.csv          your untouched broker export. Real, and gitignored.
    """
    d = INPUT_DIR
    if not os.path.isdir(d):
        return [], False
    allcsv = sorted(glob.glob(os.path.join(d, "*.csv")))
    real = [p for p in allcsv if not os.path.basename(p).lower().endswith(".example.csv")]
    if real:
        return real, False
    return allcsv, bool(allcsv)


def detect_holdings_schema(path):
    """(rows, ticker_col, name_col, gain_col, currency_col). Columns may be None."""
    rows = read_csv_rows(path)
    heads = list(rows[0].keys()) if rows else []
    tk = pick_column(heads, TICKER_HEADERS)
    # The ticker column is removed from contention for the others. "Instrument Code"
    # matches both the ticker and the name candidate lists, and letting one column win
    # twice costs the exchange tag in the real name field — which is the single most
    # reliable input to ticker resolution.
    rest = [h for h in heads if h != tk]
    return (rows, tk,
            pick_column(rest, NAME_HEADERS),
            pick_column(rest, GAIN_HEADERS, exclude=GAIN_EXCLUDE),
            pick_column(rest, CURRENCY_HEADERS))


def native_money_columns(headers):
    """Headers holding money in the line's own currency, best first.

    Any header naming a currency is dropped: that names a CONVERTED column, and it is
    populated on every row, so including it makes the whole file read as base currency.
    """
    scored = []
    for h in headers or []:
        n = norm_header(h)
        raw = (h or "").lower()
        if any(m in raw or m in n for m in CONVERTED_HEADER_MARKERS):
            continue
        # "Price +/- today (%)" matches the `price` candidate and holds no currency
        # symbol, so it would rank ahead of the real price column and contribute
        # nothing — the same day-move column GAIN_EXCLUDE already guards against.
        if "%" in raw or any(m in n for m in GAIN_EXCLUDE):
            continue
        for rank, cand in enumerate(NATIVE_MONEY_HEADERS):
            if cand in n:
                scored.append((rank, len(n), h))
                break
    return [h for _, _, h in sorted(scored)]


# Per-line market-value headers, most specific first. "market value" is ii's spelling;
# the bare "value" tier is AJ Bell's `Value (£)`. Both tiers are needed and the order
# matters: ii publishes BOTH `Market Value £` (converted) and `Market Value` (native),
# and only the specific tier distinguishes them.
VALUE_HEADER_RANK = ("market value", "value")

# Money columns that are not the line's market value. Excluded by NAME rather than by
# position, because brokers order them freely: AJ Bell's export carries `Cost (£)` and
# `Change (£)` immediately after `Value (£)`, and all three normalise to a bare word.
VALUE_HEADER_EXCLUDE = ("cost", "gain", "change", "profit", "loss", "%")


def find_sterling_column(headers):
    """(header, read_in_native_currency) for the broker's own per-line value column.

    Sterling first: the £ column is what makes per-line values comparable across a
    multi-currency book without this repo touching FX. Where the broker publishes both
    a converted and a native column under the same normalised name (ii: `Market Value £`
    beside `Market Value`), the £ one wins; where it publishes only a native one, it is
    returned with the flag set so the caller can say so.

    ONE READER, TWO CALLERS (2026-08-23). tools/xray.py and tools/checks.py both use
    this. They used to hold separate copies matching only "market value", which is ii's
    header — AJ Bell's is `Value (£)`, so an entire account was skipped by the x-ray
    AND by the check that exists to catch a wrong NAV, because the check mirrored the
    same blind reader and compared the number against itself. A guard derived from the
    thing it guards cannot fail. Keep this function the single implementation.
    """
    by_norm = {}
    for h in headers or []:
        n = norm_header(h)
        raw = (h or "").lower()
        if any(x in n for x in VALUE_HEADER_EXCLUDE):
            continue
        for rank, cand in enumerate(VALUE_HEADER_RANK):
            if cand in n:
                by_norm.setdefault((rank, n), []).append((h, raw))
                break
    if not by_norm:
        return None, False
    for key in sorted(by_norm):
        # Shortest header first: `Market Value £` beats a padded `Market Value £ GBP`.
        for h, raw in sorted(by_norm[key], key=lambda c: len(c[0])):
            if "£" in raw:
                return h, False
    key = sorted(by_norm)[0]
    h, _ = min(by_norm[key], key=lambda c: len(c[0]))
    return h, True


def parse_pounds(cell):
    """(value, already_sterling) for one market-value cell, or (None, False).

    A bare number is trusted as sterling: that is what a broker publishes in a column
    it has already labelled with the currency (AJ Bell's `Value (£)` holds `1,234.56`,
    not `£1,234.56`). An explicit £ is likewise sterling; $ and pence are not, and the
    caller is told so. Shared with find_sterling_column by tools/xray.py and
    tools/checks.py — see that function's note on why there is only one copy.
    """
    s = str(cell or "").strip().replace(",", "")
    if re.fullmatch(r"[\d.]+", s):
        return float(s), True
    if "£" in s:
        return float(s.replace("£", "").strip() or 0), True
    if "$" in s:
        return float(s.replace("$", "").strip() or 0), False
    if re.fullmatch(r"[\d.]+p", s, re.I):
        return float(s[:-1]) / 100, False
    return None, False


def cell_currency(val):
    """Currency of a single money cell, from its symbol. '' when it carries none.

    Pence is reported as GBp, not GBP. They are the same currency and a different
    quote, and only the pence form is proof of an LSE line — a UK broker will happily
    total a pence-quoted stock's book cost in pounds.
    """
    s = str(val or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"[\d,.\s]+p", s, re.I):
        return "GBp"
    if "£" in s:
        return "GBP"
    # PREFIXED DOLLARS BEFORE THE BARE ONE (2026-08-25). "CA$29.87" contains "$",
    # so the bare test below claimed it as USD and every Canadian line in the book
    # read as a US line. That is not a cosmetic mislabel: EXPECTED_CUR is built
    # from this, so the feed check — the one that prints "very likely a DIFFERENT
    # SECURITY" — compared a CAD holding's USD-quoting namesake against an expected
    # USD and reported VERIFIED. It is the reason a bare `NEO` row screened
    # NeoGenomics (US diagnostics, $16.41) under a rare-earth thesis for as long as
    # it existed, with no warning anywhere in the run.
    for pre, ccy in DOLLAR_PREFIXES:
        if pre in s.upper():
            return ccy
    if "$" in s:
        return "USD"
    if "€" in s:
        return "EUR"
    if "¥" in s:
        return "JPY"
    return ""


def row_currency(row, ccol, money_cols=None):
    """The line's trading currency: explicit column first, then its own money cells.

    Falls back to the old whole-row scan only when no native money column could be
    identified — better a rough guess than none, and `resolve_ticker`'s ALT_FORM retry
    still corrects a wrong suffix against the price feed.
    """
    if ccol and row.get(ccol):
        return row[ccol].strip().upper()

    for h in (money_cols if money_cols is not None else native_money_columns(row.keys())):
        cur = cell_currency(row.get(h))
        if cur:
            return cur

    blob = " ".join(str(v) for v in row.values() if v)
    if "£" in blob:
        return "GBP"
    if "$" in blob:
        return "USD"
    return ""


def map_form(sym, smap):
    """The suffixed spelling of `sym` that sector_map.md lists, if there is exactly one.

    input/README.md calls sector_map.md the override file for ticker resolution —
    "add a row with the exact ticker you want" — but until 2026-08-25 only the `.L`
    form was ever consulted, so that promise held for LSE lines and nothing else.
    Ten `.TO` rows in the shipped map were dead letters: `KNT.TO` was present and
    correct, and the holding still resolved to bare `KNT`, which is not a listed
    security, under the basis "assumed US line (unconfirmed)".

    Exactly one, or none. Two suffixed forms of one base are the same self-
    contradiction as a bare/.L pair and get the same treatment — the map settles
    nothing, so it is not consulted. `checks.py --pre` fails on it separately.
    """
    hits = [k for k in smap
            if k.startswith(sym + ".") and "." not in k[len(sym) + 1:]]
    return hits[0] if len(hits) == 1 else None


def map_sector(sym, smap):
    """sector_map.md's sector for a broker symbol, in whichever form the map lists it."""
    return smap.get(sym) or smap.get(map_form(sym, smap) or "")


def resolve_ticker(sym, name, currency, smap):
    """(yahoo_ticker, basis). Never returns None — resolution always yields a guess.

    Resolution order, most trustworthy first. The basis string is printed on every
    run so a wrong guess is visible rather than silent, and ALT_FORM records the
    other plausible form so a failed fetch can self-correct against the price feed.
    """
    sym = (sym or "").strip().upper()
    name = (name or "").strip()

    # 1. Already carries an exchange suffix — the broker has done the work.
    if re.fullmatch(r"[A-Z0-9\-]{1,8}\.[A-Z]{1,3}", sym):
        record_forms(sym, None, sym, currency)
        return sym, "as given"

    # 2. Venue written into the instrument name: "(LSE:VOD)", "NASDAQ:NVDA".
    m = re.search(r"\b([A-Z]{2,7})\s*:\s*([A-Z0-9\-]{1,8})\b", name.upper())
    if m and m.group(1) in EXCHANGE_SUFFIX:
        base, suf = m.group(2), EXCHANGE_SUFFIX[m.group(1)]
        record_forms(base + suf, base if suf else base + ".L", sym, currency)
        return base + suf, f"exchange tag {m.group(1)}: in name"

    # 3 & 4. sector_map.md is the authoritative ticker list, so a hit there settles the
    # suffix question. Checked in both forms because a user who lists LSE lines with the
    # .L suffix has already told us which of their holdings are LSE lines.
    #
    # UNLESS the map carries BOTH forms of the same symbol — in which case it settles
    # nothing and, read in the old bare-first order, actively lies. sector_map.md held
    # rows for both `GIGB` and `GIGB.L`; bare won, bare is a real US bond ETF, and the
    # mining holding was screened as a bond fund for as long as both rows existed
    # (fixed 19 Aug 2026). Six symbols in the shipped map had the same shape. Where the
    # map is ambiguous the currency is the tiebreak, `checks.py --pre` fails the run so
    # the ambiguity gets removed rather than tolerated, and the feed check downstream
    # is the backstop for whichever form is picked here.
    fam = cur_family(currency)
    bare_in, suf = sym in smap, map_form(sym, smap)
    if bare_in and suf:
        # The tiebreak was "GBP-priced picks .L, everything else picks bare". That
        # generalises without a suffix-to-currency table: a bare Yahoo ticker IS the
        # US listing, so a row priced in anything else is not the bare form. Same
        # answer as before for the GBP/.L case that prompted it.
        pick = suf if fam and fam != "USD" else sym
        other = sym if pick == suf else suf
        record_forms(pick, other, sym, currency)
        return pick, (f"sector_map.md AMBIGUOUS (lists {sym} and {suf}) — "
                      f"{fam or 'no'}-priced row picked {pick}")
    if bare_in:
        record_forms(sym, suf or sym + ".L", sym, currency)
        return sym, "sector_map.md"
    if suf:
        record_forms(suf, sym, sym, currency)
        return suf, f"sector_map.md ({suf[len(sym):]} form)"

    # 5. Priced in sterling => LSE line.
    if any(g in (currency or "").upper() for g in GBP_MARKERS):
        record_forms(sym + ".L", sym, sym, currency)
        return sym + ".L", f"priced in {currency or 'GBP'}"

    # 6. Nothing to go on. Bare symbol is right far more often than not, and the
    # ALT_FORM retry catches the LSE lines this misses.
    record_forms(sym, sym + ".L", sym, currency)
    return sym, "assumed US line (unconfirmed)"


def is_screenable(sym, name):
    """False for rows with no daily price series: OEICs, gilts, T-bills, cash, ISINs.

    Excluded by design, not a mapping gap — but counted and reported, because a
    holding disappearing from the screen must never be something you have to notice
    for yourself. Some brokers put the bare SEDOL in the ticker column and the FUND:
    marker only in the instrument name, so both fields are tested.
    """
    blob = f"{sym} {name}".upper()
    if not sym:
        return False
    if any(x in blob for x in NON_SCREENABLE):
        return False
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", sym):     # ISIN
        return False
    if re.fullmatch(r"[0-9]+", sym):
        return False
    return True


# ---------------------------------------------------------------- holdings

def load_holdings(here=None):
    """Map ticker -> (account, gain_pct). Degrades to {} rather than failing."""
    held = {}

    def pctf(s):
        try:
            return float(str(s).replace("%", "").replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    files, _demo = discover_holdings_files()
    for path in files:
        try:
            rows, tkcol, namecol, gaincol, _ = detect_holdings_schema(path)
            if not tkcol:
                continue
            label = account_label(path)
            for row in rows:
                sym = (row.get(tkcol) or "").strip().upper()
                if not is_screenable(sym, row.get(namecol) if namecol else ""):
                    continue
                gain = pctf(row.get(gaincol)) if gaincol else None
                # Registered in both forms: the resolver may land on either, and a
                # holding that fails to match its own row loses its HELD annotation.
                held.setdefault(sym, (label, gain))
                held.setdefault(sym + ".L", (label, gain))
        except Exception:
            continue

    return held


def load_roster(here=None, smap=None):
    """Held positions to screen: (found, skipped, detections, demo_mode).

    `found` is [(yahoo_ticker, sector, broker_symbol, basis)] — read from the broker
    CSVs so no text file has to carry holdings. Hand-syncing a holdings list is what
    once left two live positions with no 150-day exit line and no ROUND-TRIP-RISK
    coverage for weeks: the file looked complete, so nobody checked.

    `skipped` is [(symbol, reason)] for rows with no price series. Reported, never
    silently dropped. `detections` records how each file's columns were read, so the
    run log shows what the auto-detection actually did.
    """
    smap = smap or {}
    found, skipped, detections = [], [], []
    files, demo = discover_holdings_files()

    for path in files:
        base = os.path.basename(path)
        try:
            rows, tkcol, namecol, gaincol, ccol = detect_holdings_schema(path)
        except Exception as e:
            detections.append((base, f"unreadable — {e}"))
            continue
        if not tkcol:
            detections.append((base, "no ticker column found — expected one of: "
                                     + ", ".join(TICKER_HEADERS)))
            continue
        money = native_money_columns(rows[0].keys()) if rows else []
        detections.append((base, f"ticker={tkcol!r} name={namecol!r} "
                                 f"gain={gaincol!r} ccy={ccol!r}"
                                 + (f" ccy-from={money[0]!r}" if not ccol and money else "")
                                 + f" · {len(rows)} rows"))
        for row in rows:
            sym = (row.get(tkcol) or "").strip().upper()
            nm = (row.get(namecol) or "") if namecol else ""
            if not sym:
                continue
            if not is_screenable(sym, nm):
                skipped.append((sym, "no price series (fund/gilt/cash)"))
                continue
            tk, basis = resolve_ticker(sym, nm, row_currency(row, ccol, money), smap)
            found.append((tk, smap.get(tk) or smap.get(sym) or "Unclassified", sym, basis))

    # Dedupe: the same position can appear in two sleeve exports.
    seen, uniq = set(), []
    for tk, sec, sym, basis in found:
        if tk not in seen:
            seen.add(tk)
            uniq.append((tk, sec, sym, basis))
    return uniq, skipped, detections, demo


def discover_watchlist_files():
    """Watchlist files at the top level of input/ (17 Aug 2026 onwards).

    Matches:
    - `input/watchlist.md` — the canonical single watchlist
    - `input/watchlist_favorites.md` / `watchlist_smallcaps.md` etc. — opt-in splits

    Examples (`*.example.md`) are filtered out, falling back to real files only.
    """
    candidates = sorted(glob.glob(os.path.join(INPUT_DIR, "watchlist*.md")))
    real = [p for p in candidates if not os.path.basename(p).lower().endswith(".example.md")]
    return real or candidates


def discover_tracking_files(track_dir):
    """Tier-0 tracking files: every *.md in input/tracking/ that carries ticker rows.

    Same `.example.md` rule the watchlist and holdings paths use — a shipped starter
    list is a fallback, never an addition. Without it, `universe.example.md` would
    load ALONGSIDE a real universe.md and quietly pad the screened universe with
    names the user never chose.

    README.md is a workflow doc and sector_map.md is the classification dictionary;
    neither is a ticker pool, and reading sector_map.md as one would enter every
    mapping in the file as a tracking name.
    """
    cand = [p for p in sorted(glob.glob(os.path.join(track_dir, "*.md")))
            if os.path.basename(p) not in ("README.md", "sector_map.md")]
    real = [p for p in cand if not os.path.basename(p).lower().endswith(".example.md")]
    return real or cand


def load_watchlists(here=None, smap=None):
    """Watchlist candidates to screen: [(yahoo_ticker, source_file, is_speculative)].

    Both watchlists are stateless markdown registries whose candidate rows all take the
    form "| **TICKER** | ...". They are screened — despite the sleeve evaluations already
    covering them under the roster contract — because the radar is what computes their
    breakout levels, 150-day line and volume state exactly; the evaluations otherwise
    have to read those off a chart and state them as approximate. ESEA's entry condition
    ("daily close above $78.84 on >=2x volume") is a level of precision only this screen
    produces.

    Files are discovered by globbing `input/watchlist*.md` at the top
    level of `input/` — no subdirectory, no list to maintain in code.
    The suffix is decided per row rather than per file: a bare symbol whose suffixed
    form appears in sector_map.md takes that suffix (any suffix — this read `.L` only
    until 2026-08-25, which is why `NEO`, a TSX line the map already carried as
    `NEO.TO`, screened as US-listed NeoGenomics instead). Getting this wrong double-counts a name
    in the rotation read, once bare and once as the held .L line, which is why the
    per-file "this sleeve is LSE" flag was a poor instrument for the job — a mixed
    watchlist has no single answer.

    Speculative detection: `rules/02_SLEEVE_RULES.md` §80 routes speculative names here tagged SPECULATIVE
    regardless of fundamentals-screen score, either per-row or by section heading
    ("## Quantum — SPECULATIVE TIER ONLY"). Both forms are recognised. This is the documented
    entry path for speculative ideas, which is why the discovery universe needs no
    exemption mechanism — a speculative never competes for a sector slot.
    """
    smap = smap or {}
    out = []
    for path in discover_watchlist_files():
        fname = os.path.basename(path)
        try:
            section_moon = False
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.lstrip().startswith("#"):
                        section_moon = "SPECULATIVE" in line.upper()
                        continue
                    m = re.match(r"\s*\|\s*\*\*([A-Z0-9.\-]{1,8})\*\*\s*\|", line)
                    if not m:
                        continue
                    moon = section_moon or "SPECULATIVE" in line.upper()
                    tk = m.group(1)
                    if tk not in smap:
                        tk = map_form(tk, smap) or tk
                    out.append((tk, fname, moon))
        except (OSError, UnicodeDecodeError) as e:
            # DATA PATH — narrow, and say so. This used to be `except Exception:
            # pass`, which meant a malformed watchlist silently shrank the
            # screened universe: measured 2026-08-23, truncating the file took
            # the watchlist leg 87 -> 45 candidates and a garbage file took it
            # to 0, with nothing downstream noticing (docs/BACKLOG.md 21.1).
            # A file we cannot read is now named; a file we can read but that
            # contains no table still legitimately contributes nothing.
            print(f"[watchlist] ⚠️  {os.path.basename(fname)} could not be read "
                  f"({e.__class__.__name__}) — its candidates are NOT in this "
                  f"run's universe", file=sys.stderr)
    seen, uniq = set(), []
    for tk, src, moon in out:
        if tk not in seen:
            seen.add(tk)
            uniq.append((tk, src, moon))
    return uniq


def md_table_rows(path):
    """Yield [cell, ...] for each data row of any markdown table in a file.

    Header rows and |---|---| separators are skipped, as is prose. Cells are stripped of
    bold markers so "| **TICKER** |" and "| TICKER |" both parse. Used for the universe and
    sector map, which are markdown (rather than plain text) so they render as readable
    tables in an editor — the watchlists were already in this format.
    """
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("|"):
                    continue
                cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
                if not cells or not cells[0]:
                    continue
                if set(cells[0]) <= set("-: "):          # separator row
                    continue
                if cells[0].lower() in ("ticker", "symbol", "group"):   # header row
                    continue
                yield cells
    except (OSError, UnicodeDecodeError) as e:
        # DATA PATH. A bare `except Exception: return` here truncates the table
        # mid-parse and the caller cannot tell a short table from a broken one.
        print(f"[table] ⚠️  stopped reading {path!r} ({e.__class__.__name__}) — "
              f"rows after this point are missing from this run",
              file=sys.stderr)
        return


def load_sector_map(here=None):
    """ticker -> sector, from input/tracking/sector_map.md. Authoritative for all screened names."""
    m = {}
    path = os.path.join(INPUT_DIR, "tracking", "sector_map.md")
    for cells in md_table_rows(path):
        # Ticker rows are 2 cells (Ticker | Sector) or 3 with a trailing Held column.
        # The 4-cell bellwether table in the same file belongs to load_bellwethers().
        #
        # BUG FIXED 12 Aug 2026: this required exactly 3 cells, but the shipped
        # sector_map.md table is 2 columns — so the map parsed as EMPTY and every
        # single ticker in the file fell through to "Unclassified" on every run. It
        # went unnoticed because the failure is quiet: the radar still runs, the
        # rotation read just silently loses its classifications. It matters much more
        # now that ticker resolution consults this map to decide the .L suffix.
        if (len(cells) in (2, 3) and cells[1]
                and re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,9}", cells[0])):
            m[cells[0]] = cells[1].lstrip("@")
    return m


def load_bellwethers(here=None):
    """Sector -> gauge ETF tickers + investable roster line, from the 4-column
    bellwether table in sector_map.md (added 26 Jul 2026).

    Gauges are MEASUREMENT-ONLY: never added to the screening universe, no flags,
    no RS percentile, excluded from the rotation In/Out counts — an XLP breakout
    must not count as "Defensive arriving". The Investable line column is the
    bridge from a ROTATION-IN tag to a buyable roster ticker."""
    bells = {}
    path = os.path.join(INPUT_DIR, "tracking", "sector_map.md")
    for cells in md_table_rows(path):
        if len(cells) != 4 or cells[0].lower() == "sector":
            continue
        tks = [x for x in cells[1].replace("+", " ").split()
               if re.fullmatch(r"[A-Z]{2,5}", x)]
        bells[cells[0]] = {"tickers": tks, "investable": cells[2]}
    return bells


# ---------------------------------------------------------------- RRG (weekly)

def sector_rrg_section(rows, sectors, state_path, today):
    """Relative Rotation Graph-style sector read.

    Level = a sector's avg RS percentile across its tickers (standing vs the whole
    universe; RS itself is the recency-weighted 3/6/12-month excess return already
    computed per ticker). Momentum = change in that sector's avg *raw* RS score since
    the last --rrg snapshot — raw score is used for momentum (not percentile) because
    percentile is bounded 0-100 and compresses at the extremes.

    Quadrants (classic RRG):
      Leading    level >= 50, momentum > 0   — in favour, still gaining
      Weakening  level >= 50, momentum <= 0  — in favour, losing steam
      Improving  level <  50, momentum > 0   — early rotation in
      Lagging    level <  50, momentum <= 0  — out of favour, no turn yet

    This is a strategic/positioning read on a weekly cadence, not a trade trigger —
    pair a quadrant shift with your strategic-conviction source before acting on it. It is the slow
    companion to the flag-cluster 'Rotation read' above, which is fast/tactical.
    """
    agg = {}
    for r in rows:
        if r["rs"] is None or r["rs_pctl"] is None:
            continue
        sec = sectors.get(r["ticker"], "Unclassified")
        d = agg.setdefault(sec, {"rs": [], "pctl": [], "tickers": []})
        d["rs"].append(r["rs"])
        d["pctl"].append(r["rs_pctl"])
        d["tickers"].append(r["ticker"])

    cur = {sec: {"rs": sum(d["rs"]) / len(d["rs"]),
                 "pctl": sum(d["pctl"]) / len(d["pctl"]),
                 "n": len(d["tickers"]),
                 "tickers": d["tickers"]}
           for sec, d in agg.items()}

    prev, prev_date = {}, None
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                snap = json.load(f)
                prev_date, prev = snap.get("date"), snap.get("sectors", {})
        except (OSError, ValueError) as e:
            # "No prior snapshot" and "prior snapshot is corrupt" render the
            # same downstream ("this is the baseline week"), which makes a real
            # fault look like a first run. Say which one it was.
            print(f"[rrg] ⚠️  {os.path.basename(state_path)} exists but could "
                  f"not be read ({e.__class__.__name__}) — momentum is being "
                  f"reported as a baseline week, not as unchanged",
                  file=sys.stderr)

    out_rows = []
    for sec, d in sorted(cur.items(), key=lambda kv: -kv[1]["pctl"]):
        p = prev.get(sec)
        level = d["pctl"]
        if p:
            mom = d["rs"] - p["rs"]
            quad = ("Leading" if level >= 50 and mom > 0 else
                     "Weakening" if level >= 50 else
                     "Improving" if mom > 0 else "Lagging")
            prev_quad = p.get("quad")
            # "Baseline" isn't a real quadrant, so the week that first classifies a
            # sector shouldn't be reported as a shift — only genuine quadrant-to-
            # quadrant transitions from week 3 onward count.
            shift = (f"{prev_quad} → {quad}"
                     if prev_quad and prev_quad != "Baseline" and prev_quad != quad
                     else "—")
        else:
            mom, quad, shift = None, "Baseline", "—"
        d["quad"] = quad
        tks = sorted(d["tickers"])
        tks_s = ", ".join(tks[:6]) + ("…" if len(tks) > 6 else "")
        out_rows.append((sec, d["n"], level, mom, quad, shift, tks_s))

    L = ["", "## Sector Rotation Radar (RRG) — weekly", "",
         f"*Level = sector's avg RS percentile across its tickers (standing vs the whole "
         f"{sum(d['n'] for d in cur.values())}-ticker universe). Momentum = Δ avg raw RS "
         f"score vs the previous weekly snapshot"
         + (f" ({prev_date})" if prev_date else "")
         + ". Quadrant: **Leading** (level≥50, rising), **Weakening** (level≥50, "
           "falling), **Improving** (level<50, rising), **Lagging** (level<50, falling). "
           "Strategic positioning read on a weekly cadence — not a trade trigger on its "
           "own; pair a shift with strategic conviction. Faster/tactical companion is the "
           "flag-cluster 'Rotation read' above.*", "",
         "| Sector | N | Level (pctl) | Δ RS (mom.) | Quadrant | Shift vs last week | Tickers |",
         "|---|---|---|---|---|---|---|"]
    for sec, n, level, mom, quad, shift, tks_s in out_rows:
        mom_s = f"{mom:+.2f}" if mom is not None else "—"
        quad_s = f"**{quad}**" if quad in ("Leading", "Improving") else quad
        L.append(f"| {sec} | {n} | {level:.0f} | {mom_s} | {quad_s} | {shift} | {tks_s} |")

    shifts = [f"{sec}: {shift}" for sec, n, level, mom, quad, shift, tks_s in out_rows
              if shift != "—"]
    if shifts:
        L += ["", f"**Quadrant shifts vs last week:** {'; '.join(shifts)}."]
    if not prev:
        L += ["", "*No prior --rrg snapshot — this is the baseline week; momentum and "
                   "quadrant shifts populate from next Sunday's run.*"]

    try:
        with open(state_path, "w") as f:
            json.dump({"date": today,
                       "sectors": {sec: {"rs": d["rs"], "pctl": d["pctl"], "quad": d["quad"]}
                                   for sec, d in cur.items()}}, f, indent=1)
    except (OSError, TypeError, ValueError) as e:
        # WRITE-SIDE MIRROR of the read guard above. A silent failure here is
        # worse than a read failure, because the damage lands on the NEXT run:
        # it finds no snapshot and reports a baseline week, with nothing in
        # either run's output pointing back at this moment.
        print(f"[rrg] ⚠️  could not write {os.path.basename(state_path)} ({e}) "
              f"— NEXT run will report a baseline week rather than momentum",
              file=sys.stderr)

    return L


# ------------------------------------------- sector pressure (backlog item 3.3)

def universe_pctl(pop, x):
    """Where `x` sits in `pop`: the % of the population at or below it.

    Same convention as `range_percentile`, and deliberately not the one
    `rs_pctl` uses (rank/(n-1)), because `x` here is a sector MEDIAN and need
    not be a member of the population at all.
    """
    if x is None or not pop:
        return None
    return 100.0 * sum(1 for p in pop if p <= x) / len(pop)


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0


def sector_pressure(rows, sectors):
    """Per-sector aggregates of the CONTINUOUS measures, ranked against the universe.

    WHY THIS EXISTS — the gold miss, August 2026. The rotation read above
    aggregates FLAGS, and flags are thresholded. `VOL-2X-UP` needs a 2x volume
    spike inside 5 sessions; accumulation is a sustained 20-day measure; the two
    disagree constantly. On the day the gold cluster was missed, AEM carried the
    highest `acc` in the entire universe (5.09) and had never fired a volume flag
    at all, while its sector's median member sat above the universe's 90th
    percentile for ten consecutive sessions. The continuous measurement was
    screaming and the binary conversion threw it away — and only the binary was
    ever aggregated. This table aggregates the measurements themselves.

    MEDIAN, NOT MEAN. A mean lets one name that doubled paint its whole sector as
    a cluster, which is the opposite of what "cluster" means.

    RANKED, NOT THRESHOLDED. "`acc` 3.19" means nothing without knowing the
    universe median is 1.24. Every cell is therefore shown against the universe
    distribution rather than a hard-coded cut-off — the decision this file has
    already made twice, for `rng_pctl` (ranked against the name's own year) and
    `rs_pctl` (ranked across the universe). A fixed floor here would be a third
    magic number with no rulebook behind it.

    SPECULATIVES ARE EXCLUDED, exactly as they are from the RS percentile and for
    the same reason: a pre-revenue name's `acc` and 60-day return sit at an
    extreme by construction, and they distort both the distribution every sector
    is measured against and the median of any small sector holding one.

    MEASUREMENT ONLY. This produces no tag, no state and no flag. Making the
    system *act* on a sustained-accumulation cluster is backlog item 5, and it
    stays there — a tag growing quietly in here is how this table would end up
    with the same thresholding defect it was written to fix.
    """
    core = [r for r in rows if not r.get("speculative")]
    if not core:
        return []

    # Universe distributions — one per measure, built once and shared.
    pop = {k: [r.get(k) for r in core if r.get(k) is not None]
           for k in ("acc", "r5", "r20", "r60", "rng_pctl")}
    acc_p90 = None
    if pop["acc"]:
        srt = sorted(pop["acc"])
        acc_p90 = srt[min(len(srt) - 1, int(0.90 * len(srt)))]

    by_sec = {}
    for r in core:
        by_sec.setdefault(sectors.get(r["ticker"], "Unclassified"), []).append(r)

    out = []
    for sec, mem in by_sec.items():
        vdirs = [m["vdir"] for m in mem if m.get("vdir")]
        row = {
            "sector": sec, "n": len(mem),
            "n_up": sum(1 for v in vdirs if v == "UP"), "n_dir": len(vdirs),
            "near_hi": sum(1 for m in mem if "NEAR-52W-HIGH" in m["flags"]),
            # Breadth of accumulation: how many members individually clear the
            # universe's 90th percentile. This is the number that would have made
            # the gold cluster obvious without a single flag firing.
            "acc_hot": sum(1 for m in mem if m.get("acc") is not None
                           and acc_p90 is not None and m["acc"] >= acc_p90),
            # `rs_pctl` is already a universe percentile; ranking a percentile
            # against the universe again would be meaningless, so it is reported
            # as the plain median of an already-relative number.
            "rs_pctl": _median([m.get("rs_pctl") for m in mem]),
        }
        for k in ("acc", "r5", "r20", "r60", "rng_pctl"):
            med = _median([m.get(k) for m in mem])
            row[k] = med
            row[k + "_p"] = universe_pctl(pop[k], med)
        out.append(row)

    # Ranked by accumulation percentile — the measure the miss was about. A
    # sector with no computable accumulation sorts last rather than at zero,
    # since "unknown" and "no accumulation" are not the same reading.
    # Tiebreak on the raw median before momentum, so two sectors landing on the
    # same percentile still order by the quantity the column actually shows.
    out.sort(key=lambda d: (d["acc_p"] is None, -(d["acc_p"] or 0),
                            -(d["acc"] or 0), -(d["r20_p"] or 0)))
    return out, pop, acc_p90


def sector_pressure_section(rows, sectors):
    """Render the sector pressure table. Returns markdown lines (possibly empty)."""
    res = sector_pressure(rows, sectors)
    if not res:
        return []
    press, pop, acc_p90 = res
    if not press:
        return []

    uni_acc = _median(pop["acc"])
    uni_r20 = _median(pop["r20"])

    # Every number quoted in the prose below is a universe aggregate, and any of
    # them can be undefined — `acc` is None for a name with no down-day volume in
    # its last 20 sessions, so a small or unusual universe can leave the whole
    # distribution empty. The table is still worth printing in that case; what is
    # not acceptable is an f-string raising here, because this renders inside the
    # report build and would take the entire radar run down with it.
    uni_acc_s = f"{uni_acc:.2f}" if uni_acc is not None else "not computable today"
    p90_s = (f"`acc >= {acc_p90:.2f}` today" if acc_p90 is not None
             else "not computable today — the column reads 0/n")

    L = ["", "## Sector pressure — continuous measures by sector", "",
         "*The rotation read above counts **flags**. Flags are thresholded, and "
         "thresholding decorrelates a cluster: `VOL-2X-UP` needs a 2x spike inside "
         "5 sessions, while accumulation is a sustained 20-day measure, so five "
         "names accumulating together for a fortnight can light up as one or two "
         "names on scattered days — no cluster. This table aggregates the "
         "**measurements** instead, so a cluster that never trips a threshold is "
         "still visible.*", "",
         "*Every cell is a **median** across the sector's members (a mean lets one "
         "name that doubled paint its whole sector), shown with **its percentile "
         "against the whole universe** in brackets — `acc 3.19` is meaningless "
         "without knowing the universe median is "
         f"{uni_acc_s}" + ". Percentiles, not fixed cut-offs, because a hard-coded "
         "floor here would be a magic number with no rulebook behind it.*", "",
         "*`Acc>p90` is the one to read first: how many of the sector's own members "
         "individually clear the universe's 90th percentile for accumulation "
         f"({p90_s}). That is breadth of accumulation, and it "
         "is what the flag layer cannot see. **Speculatives are excluded** "
         "throughout, exactly as they are from the RS percentile. "
         "**Measurement only — this table produces no tag and no signal.***", "",
         "| Sector | n | Acc (pctl) | Acc>p90 | 5d | 20d (pctl) | 60d (pctl) | "
         "Vol UP | Rng pctl | RS pctl | ≥52wH |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]

    def cell(v, p, fmt="{:+.1f}%"):
        if v is None:
            return "—"
        return fmt.format(v) + (f" ({p:.0f})" if p is not None else "")

    for d in press:
        thin = " ·" if d["n"] < 3 else ""
        up = f"{d['n_up']}/{d['n_dir']}" if d["n_dir"] else "—"
        rs = f"{d['rs_pctl']:.0f}" if d["rs_pctl"] is not None else "—"
        rng = f"{d['rng_pctl']:.0f}" if d["rng_pctl"] is not None else "—"
        L.append(
            f"| {d['sector']}{thin} | {d['n']} | {cell(d['acc'], d['acc_p'], '{:.2f}')} | "
            f"{d['acc_hot']}/{d['n']} | {cell(d['r5'], None)} | "
            f"{cell(d['r20'], d['r20_p'])} | {cell(d['r60'], d['r60_p'])} | "
            f"{up} | {rng} | {rs} | {d['near_hi']}/{d['n']} |")

    L += ["", "*`·` marks a sector with under 3 members — its median is one or two "
              "names, so read it as an anecdote, not a cluster. Returns count "
              "**sessions, not calendar days** (`20d` = 20 of that name's own bars), "
              "so names on different exchanges can span slightly different windows.*"]

    # Factual lead, because a 20-row table buries what the reader came for. This
    # restates the top rows and draws no conclusion — deliberately: turning this
    # into a verdict is item 5's job, not this table's.
    lead = [d for d in press
            if d["n"] >= 3 and d["acc_p"] is not None and d["acc"] is not None][:3]
    if lead:
        bits = []
        for d in lead:
            b = (f"**{d['sector']}** (median acc {d['acc']:.2f}, p{d['acc_p']:.0f}; "
                 f"{d['acc_hot']}/{d['n']} members above universe p90")
            if d["r20"] is not None:
                b += f"; 20d {d['r20']:+.1f}%"
            bits.append(b + ")")
        tail = f"*Universe median `acc` {uni_acc_s}"
        tail += (f", median 20d {uni_r20:+.1f}%.*" if uni_r20 is not None else ".*")
        L += ["", "**Most accumulation (sectors of 3+):** " + "; ".join(bits) + ". " + tail]
    return L


# --------------------------------------------- SUSTAINED membership (item 5)

def mark_sustained(rows):
    """Set `r["sustained"]` on every row and return (count, acc_floor, notes).

    THE CONTINUATION STATE. `docs/ROTATION_DIAGNOSIS_2026-08-21.md` §1: the
    rotation read can see a sector arriving and a sector leaving, and a sector
    already moving is invisible to it — not in the numerator, not in the
    denominator, not in the report. Arrival needs `HEARTBEAT` (coiled) or
    `AT-BREAKOUT` (within 3% of the prior high); a name 15% above a rising line
    accumulating at 3.6x satisfies neither, because it is trending rather than
    coiling and its prior high was set in a different regime. This function names
    that state so the rotation read can score it.

    TWO LIMBS, BOTH REQUIRED.

    *Geometry* — above a **rising** primary line, and either already past the
    breakout box (`EXTENDED>BREAK`) or within 10% of the 52-week high
    (`NEAR-52W-HIGH`). Both of those flags are computed today and read by nothing;
    wiring them in is §8's change 1. `above` subsumes "not round-tripping":
    `ROUND-TRIP-RISK` and `BELOW-RISING-LINE` are both defined on `not above`, so
    a sustained name cannot carry either, and no separate exclusion is needed.

    *Pressure* — `acc` at or above the universe median AND `rs_pctl` at or above
    the universe median. This is §8's change 2, and it is what stops the state
    from being a re-description of the price. Geometry alone would tag every name
    drifting sideways 3% above its box; the question SUSTAINED has to answer is
    whether the sector is **still being bought**, and accumulation is the measure
    of that. Requiring both means "still bought AND still outperforming".

    RANKED, NOT THRESHOLDED — the same decision item 3.3 made, and for the same
    reason. `acc >= 1.8` would be a magic number; `acc >= the universe median`
    adapts to the regime and is the identical idiom `rs_pctl` and `rng_pctl`
    already use. It is also the reason this cannot run inside `analyse()`: the
    universe distribution does not exist until every name is fetched.

    EXCLUSIONS. Speculatives (no `rs_pctl` by construction — see the note at the
    RS ranking, and item 3.3's identical carve-out) and names without a full
    150-day line (`full` is False, so `trend_main` describes a 50-day proxy and
    "above a rising 150-day" is not a claim we can make). Both fall out of the
    None-checks below, but the intent is stated because a future reader would
    otherwise read it as an accident.
    """
    core = [r for r in rows if not r.get("speculative")]
    pop_acc = [r["acc"] for r in core if r.get("acc") is not None]
    acc_floor = None
    if pop_acc:
        # Same index convention as `acc_p90` in sector_pressure(), deliberately —
        # two different definitions of "the universe's Nth percentile of acc" in
        # one file is exactly the kind of drift that makes two tables disagree.
        srt = sorted(pop_acc)
        acc_floor = srt[min(len(srt) - 1, int(SUS_ACC_PCTL / 100.0 * len(srt)))]

    n = 0
    for r in rows:
        r["sustained"] = False
        if r.get("speculative") or not r.get("full"):
            continue
        if not r.get("above") or r.get("trend_main") != "Rising":
            continue
        fl = set(r.get("flags") or ())
        if not (fl & {"EXTENDED>BREAK", "NEAR-52W-HIGH"}):
            continue
        acc, rsp = r.get("acc"), r.get("rs_pctl")
        if acc is None or acc_floor is None or acc < acc_floor:
            continue
        if rsp is None or rsp < SUS_RS_PCTL:
            continue
        r["sustained"] = True
        n += 1
    return n, acc_floor


# ---------------------------------------------------------------- rotation persistence

def _rotation_backup_path(hist_path):
    """The most recent dated backup of this history file, or '' if none exists.

    Looks in the same directory for `rotation_history.backup-YYYY-MM-DD.json`
    patterns and returns the path with the largest date <= today. Used as the
    fallback when the primary history file is missing or corrupt.
    """
    dirname = os.path.dirname(hist_path) or "."
    base = os.path.basename(hist_path)              # e.g. rotation_history.json
    prefix = base[:-len(".json")] if base.endswith(".json") else base
    candidates = []
    for p in glob.glob(os.path.join(dirname, prefix + ".backup-*.json")):
        m = re.search(r"\.backup-(\d{4}-\d{2}-\d{2})\.json$", p)
        if m:
            try:
                d = datetime.date.fromisoformat(m.group(1))
                candidates.append((d, p))
            except ValueError:
                continue
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0])
    latest_date = max(d for d, _ in candidates)
    for d, p in candidates:
        if d == latest_date:
            return p
    return ""


def _atomic_write_json(path, payload, indent=1):
    """Write JSON to `path` atomically: temp file in the same directory,
    fsync, then atomic os.replace. On any failure, surface the error
    instead of returning with a partial file on disk.

    The previous behaviour was a plain `open(...,'w'); json.dump(...)` call,
    which on kill -9 / OOM / disk-full / Ctrl-C mid-write left the file
    truncated at whatever byte offset the process happened to flush. The
    live rotation_history.json lost 17 cumulative runs that way on the
    16-Aug → 20-Aug window.
    """
    payload = _json_safe(payload)
    dirname = os.path.dirname(path) or "."
    os.makedirs(dirname, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=dirname)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=indent,
                      separators=(",", ":") if indent is None else None)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync can fail on some filesystems (e.g. fuse mounts); the
                # os.replace below is still atomic w.r.t. crash, just not
                # against a kernel buffer loss.
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        print(f"[radar] FATAL: atomic write to {path} failed; "
              f"see traceback above. The primary history file is untouched.",
              file=sys.stderr)
        raise


def _json_safe(obj):
    """Recursively coerce values into JSON-serialisable forms.

    The rotation dict has historically hidden sets/tuples inside `gauge_flags`
    (membership-test optimisation). The original code's `except Exception:
    pass` swallowed the resulting TypeError and the bare json.dump was then
    killed mid-write, so the failure mode was 'silent TypeError → silent
    truncated file'. This pass makes the write tolerant: every set/tuple
    becomes a sorted list, every non-serialisable leaf is stringified.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, set):
        return [_json_safe(v) for v in sorted(obj)]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


# ------------------------------------------------------- numeric snapshot (item 4)

SNAPSHOT_KEEP = 30                      # dated snapshots retained, ~70KB each
# /2 adds `gauges[].px` (item 3). Item 4 stored the gauge's *momentum* but not
# its price, so a gauge move between two runs was not computable — only the
# change in a 20-day statistic, which is a second derivative and reads as
# noise. Readers must accept /1 and simply omit the gauge price column.
# /3 adds per-ticker `r5`/`r20`/`r60` (item 3.3) — session-indexed returns, the
# continuous measures the sector pressure table aggregates. Additive only: every
# /2 key is still present, so a /2 reader works unchanged against a /3 file.
# /4 adds per-ticker `sustained` (item 5) — the continuation state. It belongs in
# the snapshot for the same reason `rs_pctl` does and `acc` does not strictly
# need to: it is UNIVERSE-RELATIVE, so it cannot be recomputed from that name's
# bars alone. Who else was screened that day is part of the answer. Additive
# only; a /3 reader is unaffected.
SNAPSHOT_SCHEMA = "radar_snapshot/4"
_SNAP_RE = re.compile(r"^radar_snapshot_\d{4}-\d{2}-\d{2}\.json$")


def _r(x, n=2):
    """Round for storage. None stays None; a rounded float diffs stably."""
    return None if x is None else round(float(x), n)


def radar_snapshot(today, rows, sectors, provenance, bell_reads, fx, data_date):
    """The full per-ticker numeric read, as data (docs/BACKLOG.md item 4).

    WHY THIS EXISTS. Every number below was already computed each run and then
    persisted *only* as markdown prose in Heartbeat_Radar_<date>.md.
    `radar_state.json` kept the flag strings and nothing else. So anything
    wanting "what changed since yesterday" — which is the whole of item 3 —
    had to table-scrape two dated markdown files: the same brittleness class
    that produced item 1's false positives. This is retention, not
    measurement: not one value here is newly calculated.

    DATED ON PURPOSE. A delta needs two runs. `radar_state.json` is overwritten
    every run by design (it means "flags as of the previous run"), so it can
    never be the second half of a comparison. One file per date, pruned to the
    last SNAPSHOT_KEEP, lets a reader load two dicts and subtract.

    GAUGES ARE INCLUDED, and that is the point. On 20 Aug the Gold gauge's
    20-day momentum read +22% while its members scored `in: 0` and the sector
    rendered no row at all. The member flags were persisted; the +22% was not.
    Gauges stay measurement-only here exactly as they are everywhere else —
    stored under their own key, never mixed into `tickers`.
    """
    snap = {}
    for r in rows:
        h = r.get("held")
        acct, gain = (h if isinstance(h, (tuple, list)) and len(h) == 2
                      else (None, None))
        snap[r["ticker"]] = {
            "sector": sectors.get(r["ticker"], "Unclassified"),
            "provenance": provenance.get(r["ticker"]),
            "held": acct, "held_gain_pct": _r(gain, 1),
            "speculative": bool(r.get("speculative")),
            "px": _r(r["px"], 4), "cur": r["cur"],
            "sessions": r["n"], "full_history": bool(r["full"]),
            "line": _r(r["ma"], 4), "line_label": r["line_label"],
            "pct_to_line": _r(r["pct_to_line"]),
            "trend": r["trend_main"], "trend50": r["trend50"],
            "above_line": bool(r["above"]),
            "breakout": _r(r["breakout"], 4), "pct_to_break": _r(r["pct_to_break"]),
            "hi52": _r(r["hi52"], 4), "pct_from_hi": _r(r["pct_from_hi"]),
            "rs": _r(r["rs"], 4), "rs_pctl": _r(r.get("rs_pctl"), 1),
            "vratio": _r(r["vratio"]), "vdir": r["vdir"], "vago": r["vago"],
            "acc": _r(r["acc"]),
            "rng20": _r(r["rng20"]), "rng_pctl": _r(r["rng_pctl"], 1),
            "r5": _r(r.get("r5")), "r20": _r(r.get("r20")), "r60": _r(r.get("r60")),
            "sustained": bool(r.get("sustained")),
            "dollar_vol": _r(r["dollar_vol"], 0), "low_liq": bool(r["low_liq"]),
            "flags": list(r["flags"]), "new_flags": list(r.get("new_flags") or []),
            "last_ts": r.get("last_ts"),
        }

    gauges = {}
    for sec, parts in (bell_reads or {}).items():
        gauges[sec] = [
            {"ticker": bt,
             "trend": d["trend"], "pct_to_line": _r(d["pct"]),
             "px": _r(d.get("px"), 4),
             "r20": _r(d["r20"]), "pct_to_break": _r(d.get("pct_to_break")),
             "vratio": _r(d.get("vratio")), "vdir": d.get("vdir"),
             "flags": list(d.get("flags") or [])}
            for bt, d in parts if d is not None
        ]

    return {"schema": SNAPSHOT_SCHEMA, "date": today, "data_date": data_date,
            "fx_gbpusd": _r(fx, 4), "universe": len(snap),
            "tickers": snap, "gauges": gauges}


def prune_snapshots(directory, keep=SNAPSHOT_KEEP):
    """Keep the newest `keep` dated snapshots. Names are ISO-dated, so a plain
    sort is chronological. Only exact `radar_snapshot_YYYY-MM-DD.json` names
    are ever considered for deletion."""
    try:
        found = sorted(f for f in os.listdir(directory) if _SNAP_RE.match(f))
    except OSError:
        return 0
    dropped = 0
    for f in found[:-keep] if keep > 0 else []:
        try:
            os.remove(os.path.join(directory, f))
            dropped += 1
        except OSError:
            pass
    return dropped


OUT_LIKE_TAGS = ("OUT", "FADING-OUT", "EXHAUSTED")


def gauge_vs_tag(gauge_in_verdict, out_like):
    """The bellwether's vote ON THE TAG, derived from the IN-oriented verdict.

    The spec for the Gauge column (see the header notes, Tier 1c) is explicitly
    tag-relative: *"CONFIRMED when the ETF sits on the tag's side of its 150d"*.
    The implementation was IN-relative everywhere — the displayed verdict, the
    conflict streak, and the Tier 2e demotion that consumes it. For an OUT tag
    that inverts the meaning: `gauge_in == CONFLICT` says the bellwether is
    FALLING, which is what CORROBORATES a sector rotating out, and the code read
    it as a contradiction. A sector leaving for three runs with its gauge falling
    in step was demoted to MIXED for being consistently right — on the exit side,
    which this engine is otherwise careful never to weaken. (docs/BACKLOG.md 23.3)

    Derived rather than recomputed because `gauge_verdict_for` needs the live
    bellwether reads, and both the demotion and the history replay hold only the
    stored verdict. The two orientations are exact inverses, so flipping is
    lossless and the persisted `gauge` field keeps its existing IN-oriented form
    — no schema change, and old history stays readable.

    `-` (no bellwether configured) and `ERROR` mean the same thing on both sides
    and carry through untouched.
    """
    if not out_like or gauge_in_verdict in ("-", "ERROR"):
        return gauge_in_verdict
    return "CONFLICT" if gauge_in_verdict == "CONFIRMED" else "CONFIRMED"


def rotation_persistence(hist_path, today, cur):
    """Day-over-day memory for the flag-cluster rotation read (backlog #5, 27 Jul
    2026; extended 16 Aug 2026 for phase, score, gauge conflict, OUT-exhaustion).

    cur: {sector: {"in": n, "out": n, "sus": n,
                   "tag": "IN"|"STRONG-IN"|"CHASING"|"OUT"|"SUSTAINED"|
                   "FADING-OUT"|"EXHAUSTED"|"MIXED"|"-", "early": n, "late": n,
                   "score": float, "gauge": "CONFIRMED"|"CONFLICT"|"ERROR"|"-",
                   "gauge_mom": float|None}}
    — today's read. Stored verbatim; a re-run on the same date replaces that
    date's entry, so re-running cannot fake a 2-day streak.

    History is a rolling 30-run window in rotation_history.json. Only successful
    runs (those that reached the rotation read) ever append — fetch-failure days
    are absent, not zero, so a streak survives a missed run.

    Returns {sector: {streak, trend, speed, gauge_streak, detail}}.

    Streak — consecutive runs (ending today) carrying today's *base* tag
      (IN, OUT, SUSTAINED, MIXED). Phase suffixes (STRONG/CHASING/FADING/EXHAUSTED) ride on
      the same streak — a run that flipped STRONG-IN→CHASING is still streak=2
      IN, not streak=1 CHASING. This is what makes it answer "is this rotation
      still happening", not "is the exact tag identical every day".

    Trend — STRENGTHENING / FADING / STABLE, comparing today's signed intensity
      with the mean of up to the 5 prior runs. Intensity is in−out for an IN tag
      and out−in for an OUT tag, so STRENGTHENING always means the rotation is
      getting more emphatic in its own direction.

    Speed — ACCELERATING / DECELERATING / STABLE / NEW, score-based. Compares
      today's score with the 3-run mean score. A 3-run warmer-up is needed so a
      single huge day doesn't tag ACCELERATING and a single dud day doesn't tag
      DECELERATING.

    Gauge_streak — consecutive runs (ending today) where the gauge verdict was
      CONFLICT or ERROR. Drives the 3-CONFLICT auto-demotion rule (see Tier 2
      of the change log). Returns 0 for CONFIRMED/-.

    Detail — human-readable rendering for the report's trend/speed line.
    """
    runs = []
    backup_path = _rotation_backup_path(hist_path)
    # Read primary; if missing or corrupt, fall back to the nearest dated
    # backup and tell the user loudly (the old code silently treated
    # corrupt files as empty — that's how 17 runs of history were lost
    # on the 16-Aug → 20-Aug window; see bugnote in engine/heartbeat_radar.py
    # for the trace).
    for path, label in ((hist_path, "primary"), (backup_path, "backup")):
        try:
            with open(path) as f:
                payload = json.load(f)
            runs = payload.get("runs", [])
            if path != hist_path and runs:
                print(f"[radar] recovered {len(runs)} runs from {path} — "
                      f"{label} {hist_path} was unavailable", file=sys.stderr)
            break
        except FileNotFoundError:
            continue  # try backup
        except (ValueError, OSError) as e:
            if path == hist_path:
                print(f"[radar] WARNING: cannot read history {path}: "
                      f"{type(e).__name__}: {e} — trying backup",
                      file=sys.stderr)
                # Don't propagate: the backup fallback below is the recovery
            continue
    runs = [r for r in runs if r.get("date") != today]
    prior = runs[-29:]
    runs = prior + [{"date": today, "sectors": cur}]

    # Atomic write: temp file in the same directory, then os.replace over
    # the target. The old code did plain json.dump() to a path, which on
    # SIGKILL / disk-full / OOM mid-write left the file truncated at an
    # arbitrary byte (the live rotation_history.json lost 17 runs that way).
    _atomic_write_json(hist_path, {"runs": runs})

    # SUSTAINED is its own base, not a phase of IN. Collapsing it into IN would
    # make a sector that has merely kept trending inherit an arrival streak, and
    # the streak is precisely the number a reader uses to judge how fresh a
    # rotation is. A sector flipping SUSTAINED -> IN restarts at streak 1, which
    # is correct: the arrival IS new even though the trend is not.
    BASE_TAG = {"STRONG-IN": "IN", "CHASING": "IN",
                "FADING-OUT": "OUT", "EXHAUSTED": "OUT",
                "IN": "IN", "OUT": "OUT", "SUSTAINED": "SUSTAINED",
                "MIXED": "MIXED", "-": "-"}

    out = {}
    for sec, d in cur.items():
        base = BASE_TAG.get(d["tag"], "-")
        if base == "-":
            out[sec] = {"streak": 0, "trend": "—", "speed": "—",
                        "gauge_streak": 0, "detail": ""}
            continue

        # Streak: walk prior runs with the SAME base tag.
        streak = 1
        for r in reversed(prior):
            if BASE_TAG.get((r["sectors"].get(sec) or {}).get("tag", "-"), "-") == base:
                streak += 1
            else:
                break

        # Trend — magnitude of the rotation, in its own direction. For SUSTAINED
        # the magnitude is the size of the surviving cohort net of departures:
        # a sector holding 4 sustained names with 0 leaving is a stronger
        # continuation than one holding 4 with 2 leaving, and `in` is 0 for both.
        sign = 1 if base == "IN" else -1

        def inten(e):
            if base == "SUSTAINED":
                return e.get("sus", 0) - e.get("out", 0)
            return sign * (e.get("in", 0) - e.get("out", 0))
        cur_i = inten(d)
        prev_i = [inten(r["sectors"].get(sec) or {}) for r in prior[-5:]]
        if streak == 1:
            trend = "NEW"
            trend_detail = f"net {cur_i:+d}"
        else:
            avg = sum(prev_i) / len(prev_i)
            delta = cur_i - avg
            if base == "OUT" and delta > 0.5:
                trend = "EXHAUSTED"   # leaving magnitude is FALLING for an OUT — rotation ending
                trend_detail = f"leaving falling, magnitude Δ{delta:+.1f} vs 3-run avg"
            elif base == "OUT" and delta < -0.5:
                trend = "STRENGTHENING"
                trend_detail = f"leaving growing Δ{delta:+.1f} vs 3-run avg"
            elif base in ("IN", "SUSTAINED") and delta > 0.5:
                trend = "STRENGTHENING"
                word = "cohort" if base == "SUSTAINED" else "arrivals"
                trend_detail = f"{word} Δ{delta:+.1f} vs 3-run avg"
            elif base in ("IN", "SUSTAINED") and delta < -0.5:
                trend = "FADING"
                word = "cohort" if base == "SUSTAINED" else "arrivals"
                trend_detail = f"{word} Δ{delta:+.1f} vs 3-run avg"
            else:
                trend = "STABLE"
                trend_detail = f"net {cur_i:+d} vs {sum(prev_i)/len(prev_i):+.1f} avg"
        if base == "MIXED":
            trend = "—"
            trend_detail = ""

        # Speed — ACCEL/DECEL on score, regardless of base. NEW if streak==1.
        cur_s = d.get("score", 0.0)
        prev_s = [r["sectors"].get(sec, {}).get("score", 0.0) for r in prior[-3:]]
        if streak == 1:
            speed = "NEW"
            speed_detail = f"score {cur_s:+.2f}"
        elif not prev_s:
            speed = "STABLE"
            speed_detail = ""
        else:
            avg_s = sum(prev_s) / len(prev_s)
            d_s = cur_s - avg_s
            if d_s > 0.30:
                speed = "ACCELERATING"
            elif d_s < -0.30:
                speed = "DECELERATING"
            else:
                speed = "STABLE"
            speed_detail = f"score {cur_s:+.2f} vs {avg_s:+.2f} avg"

        # Gauge streak — consecutive CONFLICT/ERROR, IN-oriented.
        #
        # NOT THE ONE THAT MATTERS, and deliberately left alone. The streak the
        # Tier 2e demotion and the report both consume is the tag-relative one
        # computed by `gauge_conflict_streak()` at the call site; this field is
        # returned in the persistence dict and read by nothing. Made tag-relative
        # it would need the tag, which this function does not have. Kept as-is,
        # named for what it is, so the next reader does not mistake it for the
        # live value (docs/BACKLOG.md 23.3).
        gauge_streak = 0
        for r in reversed([{"sectors": cur}] + prior):
            rec = r["sectors"].get(sec) or {}
            g = rec.get("gauge_for_in", rec.get("gauge", "-"))
            if g in ("CONFLICT", "ERROR"):
                gauge_streak += 1
            else:
                break

        # Compose trend for the report. Combine into a single human-readable
        # field; avoid printing both for OUT base (its trend is already
        # strength/fade info).
        if base == "OUT":
            detail = trend_detail
        else:
            detail = trend_detail + (f"; {speed_detail}" if speed_detail else "")

        out[sec] = {"streak": streak, "trend": trend, "speed": speed,
                    "gauge_streak": gauge_streak, "detail": detail}
    return out


# ---------------------------------------------------------------- first-run bootstrap

TRACKING_README_STUB = """# Tracking — Tier 0 of the membership model

The radar reads every `*.md` in this directory (skips this README). Two swimlanes:

- `universe.md` — discovery names to track (promote-on-improvement)
- `sector-coverage.md` — sector-rotation quorum backing (intent-stated)

The daily evaluation does NOT evaluate names in this directory — it only
evaluates holdings + watchlist. The radar screens them so flags fire;
promote to a watchlist when the flag matches a thesis you actually support.
See `docs/SYSTEM_MAP.md` ("Ticker lifecycle") for the full workflow.
"""


TRACKING_UNIVERSE_STUB = """# Tracking — Universe (Discovery)

Output of a weekly fundamentals sweep, plus any idea from YouTube /
YouTube / screeners / sell-side desks / podcast notes / manual research.
Add a row per ticker; promote to a watchlist when the radar flag is
strong enough to bother with the gate card. Cap 8 per sector.

| Ticker | Source | Notes |
|---|---|---|
"""


TRACKING_SECTOR_STUB = """# Tracking — Sector-coverage backing

Deliberate, named names per thin sector so the cluster read has quorum.
Add 2–3 per sector that has too few of its own roster names to satisfy
the size-normalised floor. Cap 8 per sector.

| Ticker | Sector | Notes |
|---|---|---|
"""


def bootstrap(output_dir, input_dir):
    """Create anything missing so a first run works with no manual setup.

    Every step here replaced a line in the old six-step quickstart that asked the user
    to copy a template by hand. Copying a file is the script's job; a setup step that
    can be automated and isn't is a step that gets skipped, and a missing ledger is
    silent — the gates still run, the decisions just stop being recorded.

    Returns a list of human-readable notes about what it created.
    """
    made = []
    os.makedirs(input_dir, exist_ok=True)
    for sub in ("radar", "reports", "ledger", ".state"):
        os.makedirs(os.path.join(output_dir, sub), exist_ok=True)

    # The ledger is append-only and permanent — created once, never overwritten.
    ledger = os.path.join(output_dir, "ledger", "Gate_Ledger.csv")
    tmpl = os.path.join(ROOT, "templates", "gate_ledger.template.csv")
    if not os.path.exists(ledger) and os.path.exists(tmpl):
        shutil.copyfile(tmpl, ledger)
        made.append("output/ledger/Gate_Ledger.csv")

    # tracking/ is optional; a stub directory keeps the path discoverable without
    # making it a prerequisite for the first run. Two swimlanes: external + sector.
    track_dir = os.path.join(input_dir, "tracking")
    if not os.path.isdir(track_dir):
        try:
            os.makedirs(track_dir, exist_ok=True)
            for fname, content in (
                ("README.md", TRACKING_README_STUB),
                ("universe.md", TRACKING_UNIVERSE_STUB),
                ("sector-coverage.md", TRACKING_SECTOR_STUB),
            ):
                with open(os.path.join(track_dir, fname), "w", encoding="utf-8") as f:
                    f.write(content)
            made.append("input/tracking/ (created with README + 2 swimlanes)")
        except OSError as e:
            print(f"[scaffold] ⚠️  could not create input/tracking/ ({e}) — "
                  f"create it by hand", file=sys.stderr)
    elif not os.path.exists(os.path.join(track_dir, "README.md")):
        try:
            with open(os.path.join(track_dir, "README.md"), "w", encoding="utf-8") as f:
                f.write(TRACKING_README_STUB)
        except OSError as e:
            print(f"[scaffold] ⚠️  could not write input/tracking/README.md "
                  f"({e})", file=sys.stderr)

    return made


# ---------------------------------------------------------------- main

def main():
    global INPUT_DIR, OUTPUT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir",  default=INPUT_DIR,
                     help="Folder holding broker CSVs, watchlist.md and tracking/. "
                          "Default: <repo>/input")
    ap.add_argument("--output-dir", default=OUTPUT_DIR,
                     help="Folder receiving radar reports and state. Default: <repo>/output")
    ap.add_argument("--tracking-dir", default=None,
                     help="Directory holding Tier-0 tracking *.md files. "
                          "Default: <input-dir>/tracking/")
    ap.add_argument("--out", default=None,
                     help="Report path. Default: <output-dir>/radar/Heartbeat_Radar_<date>.md")
    ap.add_argument("--state", default=None,
                     help="Daily flag state. Default: <output-dir>/.state/radar_state.json")
    ap.add_argument("--snapshot", default=None,
                     help="Dated per-ticker numeric snapshot. Default: "
                          "<output-dir>/.state/radar_snapshot_<date>.json")
    ap.add_argument("--no-snapshot", action="store_true",
                     help="Skip the numeric snapshot. The markdown report is "
                          "unaffected either way.")
    ap.add_argument("--snapshot-keep", type=int, default=SNAPSHOT_KEEP,
                     help=f"Dated snapshots to retain (default {SNAPSHOT_KEEP}); "
                          "0 keeps all.")
    ap.add_argument("--bars-dir", default=None,
                     help="Per-ticker raw OHLCV cache (backlog item 16). Default: "
                          "<output-dir>/.state/bars/. The radar fetches the full "
                          "history once per ticker and thereafter asks only for the "
                          "few sessions it is missing.")
    ap.add_argument("--no-bar-cache", action="store_true",
                     help="Bypass the bar cache: full 2y fetch for every ticker, as "
                          "the radar behaved before item 16. Nothing is read or "
                          "written. Use this to reproduce a run independently of "
                          "cache state.")
    ap.add_argument("--refresh-bars", action="store_true",
                     help="Refetch every ticker's full history and overwrite the "
                          "cache. The repair lever — the run is self-healing for "
                          "splits and gaps, so this should rarely be needed.")
    ap.add_argument("--rrg", action="store_true",
                     help="Also compute the weekly RRG-style sector rotation section. "
                          "Intended cadence: pass this flag once a week (Sundays) — the "
                          "weekday runs should not use it.")
    ap.add_argument("--rrg-state", default=None)
    ap.add_argument("--rot-history", default=None,
                     help="Rolling per-run history of the flag-cluster rotation read; "
                          "drives the Streak/Trend columns (backlog #5).")
    a = ap.parse_args()

    # Resolve every path against the (possibly overridden) input/output dirs, then
    # create the output tree. Directories are made here rather than at import time so
    # that --help and a dry import never touch the filesystem.
    INPUT_DIR, OUTPUT_DIR = a.input_dir, a.output_dir
    here = INPUT_DIR
    state_dir = os.path.join(OUTPUT_DIR, ".state")
    created = bootstrap(OUTPUT_DIR, INPUT_DIR)
    if created:
        print("[setup] created: " + ", ".join(created))
    # tracking-dir is resolved implicitly below.
    if a.state       is None: a.state       = os.path.join(state_dir, "radar_state.json")
    if a.rrg_state   is None: a.rrg_state   = os.path.join(state_dir, "sector_rrg_state.json")
    if a.rot_history is None: a.rot_history = os.path.join(state_dir, "rotation_history.json")

    # Bar cache (item 16). --no-bar-cache leaves BARS_DIR at None, which makes
    # every fetch a full 2y request — the pre-cache behaviour, kept reachable so
    # a suspect run can always be reproduced without the cache in the picture.
    global BARS_DIR, BARS_REFRESH
    if not a.no_bar_cache:
        BARS_DIR = a.bars_dir or os.path.join(state_dir, "bars")
        os.makedirs(BARS_DIR, exist_ok=True)
    BARS_REFRESH = bool(a.refresh_bars)

    # Tracking pool — `input/tracking/*.md` (Tier 0) feeds the radar screen but
    # never the daily evaluation. Holdings are injected below from the broker CSVs;
    # watchlist names are deliberately not screened here because the sleeve
    # evaluations already cover every watchlist name with the full fundamentals +
    # chart stack under the roster contract.
    # Three sources, resolved in precedence order held > watchlist > tracking so a
    # name that is both held and on a watchlist reports as held. Sector comes from
    # sector_map.md first, then the tracking file's inline tag, then Unclassified.
    smap = load_sector_map(here)
    tickers, sectors, provenance = [], {}, {}
    inline = {}

    def add(tk, prov, sec_hint=None):
        rank = {"tracking": 0, "watchlist": 1, "held": 2}
        if tk not in sectors:
            tickers.append(tk)
            provenance[tk] = prov
        elif rank[prov] > rank[provenance[tk]]:
            provenance[tk] = prov
        sectors[tk] = smap.get(tk) or inline.get(tk) or sec_hint or "Unclassified"

    # Tracking pool — read every *.md in input/tracking/ (skip README.md). Two
    # swimlanes (17 Aug 2026):
    #   universe.md         — discovery names from a sweep / external research
    #   sector-coverage.md  — sector-rotation quorum backing (intent-stated)
    # Any extra tracking/*.md file gets the same treatment. The Sector column is
    # honoured as a fallback when sector_map.md doesn't carry the ticker.
    track_dir = a.tracking_dir or os.path.join(INPUT_DIR, "tracking")
    track_glob = discover_tracking_files(track_dir)
    if not track_glob:
        print("[tracking] WARN: input/tracking/ has no .md files. Tier 0 is empty.")
    for tf in track_glob:
        for cells in md_table_rows(tf):
            tk = cells[0]
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,9}", tk):
                continue
            # Same suffix rule the holdings and watchlist paths use: a bare row whose
            # suffixed form the map carries takes that suffix. Tracking rows had no
            # rule at all and were taken verbatim, so `| NEO |` screened US-listed
            # NeoGenomics ($16.41) while `NEO.TO`, the TSX rare-earth line the row is
            # actually about (CA$33.21), sat in the map unread.
            if tk not in smap:
                tk = map_form(tk, smap) or tk
            sec = cells[1].lstrip("@") if len(cells) >= 2 and cells[1] else None
            if sec:
                inline[tk] = sec
            add(tk, "tracking")

    # Held positions must be screened even if nobody remembered to list them — this is
    # what the 150-day exit line and ROUND-TRIP-RISK depend on.
    roster, skipped, detections, demo = load_roster(here, smap)
    for path, note in detections:
        print(f"[holdings] {path}: {note}")
    if demo:
        print("[holdings] ⚠️  DEMO DATA — no broker export found in input/. "
              "Running on the .example.csv file present in input/. Drop your own "
              "CSV in input/ and re-run; nothing else needs changing.")
    elif not detections:
        print("[holdings] ⚠️  input/ has no broker CSV — screening watchlist and "
              "tracking names only. Drop a broker CSV export in input/ to include "
              "your positions.")

    for tk, sec, sym, basis in roster:
        add(tk, "held", sec)

    speculatives = set()
    for tk, src, moon in load_watchlists(here, smap):
        add(tk, "watchlist")
        if moon:
            speculatives.add(tk)

    # Print every inference. Auto-detection is only safe if it is auditable, so the
    # basis for each resolved ticker goes to the run log — a wrong guess should be
    # something you can see, not something you have to discover from a strange chart.
    unconfirmed = [(sym, tk, b) for tk, sec, sym, b in roster if "sector_map" not in b
                   and b != "as given"]
    if unconfirmed:
        print(f"[resolve] {len(unconfirmed)} ticker(s) inferred — check these read right, "
              f"then add a row to input/tracking/sector_map.md to make any of them authoritative:")
        for sym, tk, b in unconfirmed:
            print(f"[resolve]   {sym:<10} → {tk:<12} ({b})")
    if skipped:
        agg = sorted(set(s for s, _ in skipped))
        print(f"[holdings] {len(agg)} row(s) skipped — no daily price series to screen "
              f"(funds, gilts, cash): {', '.join(agg)}")

    nosec = sorted(t for t in tickers if sectors[t] == "Unclassified")
    if nosec:
        print(f"[sector] {len(nosec)} untagged — they still screen, but take no sector "
              f"in the rotation read. Add to input/tracking/sector_map.md: {', '.join(nosec)}")
    print(f"[universe] {len(tickers)} to screen · "
          f"{sum(1 for v in provenance.values() if v == 'held')} held · "
          f"{sum(1 for v in provenance.values() if v == 'watchlist')} watchlist · "
          f"{sum(1 for v in provenance.values() if v == 'tracking')} tracking")

    # benchmarks + FX first: RS is meaningless without them
    benches = {}
    for key, sym in (("USD", "SPY"), ("GBP", "ISF.L")):
        c, _, _, _ = fetch(sym)
        if c:
            benches[key] = c
    fxc, _, _, _ = fetch("GBPUSD=X")
    fx = fxc[-1] if fxc else FX_FALLBACK

    # Bellwether gauges: one fetch per sector ETF, direction only. Kept entirely
    # outside `tickers`/`rows`, so by construction they cannot flag, cannot enter
    # the In/Out counts and take no RS percentile.
    bells = load_bellwethers(here)
    bell_reads = {}

    def bwork(item):
        sec, info = item
        parts = []
        for bt in info["tickers"]:
            c, _, _, v = fetch(bt)
            if not c or len(c) < 160:
                parts.append((bt, None))
                continue
            line, prev = sma(c, 150), sma(c[:-10], 150)
            tr = ("Rising" if line > prev * 1.001 else
                  "Falling" if line < prev * 0.999 else "Flat")
            flags = ""
            pct_break = None
            pct_line = (c[-1] / line - 1) * 100
            rnd_trip_flag = False
            below_rising = False
            near_52wh = False
            heartbeat_flag = False
            at_brkout_flag = False
            vol_2x_dir = None
            v60 = sum(v[-60:]) / min(60, len(v)) if v else 0
            v20 = sum(v[-20:]) / min(20, len(v)) if v else 0
            # Reuse gauge_analyse for the full flag set; cheaper than duplicating.
            ga = gauge_analyse(c, v) if v else None
            flags_list = ga["flags"] if ga else []
            parts.append((bt, {"trend": tr, "pct": pct_line, "px": c[-1],
                               "r20": (c[-1] / c[-21] - 1) * 100 if len(c) > 21 else None,
                               "flags": flags_list,
                               "pct_to_break": ga["pct_to_break"] if ga else None,
                               "vratio": ga["vratio"] if ga else None,
                               "vdir": ga["vdir"] if ga else None,
                               "vago": ga["vago"] if ga else None}))
        return sec, parts

    with ThreadPoolExecutor(max_workers=8) as ex:
        for sec, parts in ex.map(bwork, bells.items()):
            bell_reads[sec] = parts
    bell_errs = [bt for parts in bell_reads.values() for bt, d in parts if d is None]

    rows, errs, too_new = [], [], []
    corrected, mismatched, resolution = [], [], []

    def work(t):
        closes, vols, cur, ts = fetch(t)
        want = EXPECTED_CUR.get(t)
        alt = ALT_FORM.get(t)

        # Self-correcting resolution. An inferred ticker is retried in its other
        # plausible form (bare <-> .L) when the feed says it is wrong, and the feed
        # says so in TWO ways:
        #
        #   404          — the ticker does not exist. Loud, and the only case v1
        #                  handled.
        #   wrong money  — the ticker exists but quotes in a currency the broker row
        #                  does not, which means it is a DIFFERENT SECURITY. Silent,
        #                  and the one that shipped a SELL on a bond ETF standing in
        #                  for a mining ETF (GIGB, 16 Aug 2026).
        #
        # The alternate is adopted only if it agrees with the broker row. If neither
        # form agrees, the original is kept and recorded as MISMATCH — a name that
        # fails both tests is a mapping problem the run must surface, not paper over
        # by picking whichever wrong answer came second.
        mismatch = (closes is not None and want and cur_family(cur)
                    and cur_family(cur) != want)

        if alt and alt != t and (closes is None or mismatch):
            why = ("did not fetch" if closes is None
                   else f"quotes in {cur}, broker row is {want}")
            c2, v2, cur2, ts2 = fetch(alt)
            if c2 and (not want or not cur_family(cur2) or cur_family(cur2) == want):
                sectors[alt] = sectors.get(t, "Unclassified")
                provenance[alt] = provenance.get(t, "held")
                corrected.append((t, alt, why, cur2))
                t, closes, vols, cur, ts = alt, c2, v2, cur2, ts2
                mismatch = False
            elif mismatch:
                mismatched.append((t, want, cur, alt,
                                   cur2 if c2 else "no data"))
        elif mismatch:
            mismatched.append((t, want, cur, None, None))

        if closes is not None:
            resolution.append({
                "ticker": t,
                "broker_symbol": RESOLVED_FROM.get(t),
                "expected_currency": want or None,
                "fetched_currency": cur,
                "verdict": ("MISMATCH" if mismatch else
                            "VERIFIED" if want else "UNCHECKED"),
            })
        if closes is None:
            return ("err", t, cur)
        r = analyse(t, closes, vols, cur, ts, benches, fx)
        if r.get("too_new"):
            return ("new", t, r)
        return ("err", t, r["error"]) if "error" in r else ("ok", t, r)

    with ThreadPoolExecutor(max_workers=8) as ex:
        for kind, t, payload in ex.map(work, tickers):
            if kind == "ok":
                rows.append(payload)
            elif kind == "new":
                too_new.append(payload)
            else:
                errs.append((t, payload))

    # Bar-cache accounting. Every note here is a case where the cache was NOT
    # trusted — printed by name, because a silent refetch that keeps happening
    # every day is a bug wearing a working run as a disguise.
    if BARS_DIR:
        print(bars_summary())
        for tk, why in sorted(_BARS_NOTE):
            print(f"[bars]   {tk}: {why}")

    for bad, good, why, cur2 in corrected:
        print(f"[resolve] ✓ {bad} {why} — corrected to {good} ({cur2}) against the feed.")
    for t, want, got, alt, altcur in mismatched:
        alt_s = f"; {alt} quotes {altcur}" if alt else "; no alternate form to try"
        print(f"[resolve] ⛔ {t} ({RESOLVED_FROM.get(t) or '?'}) quotes in {got} but the "
              f"broker row is {want}{alt_s}. This is very likely a DIFFERENT SECURITY — "
              f"add the correct Yahoo ticker to input/tracking/sector_map.md. "
              f"Its line in this report is not your holding.")
    if not mismatched:
        n_ok = sum(1 for r in resolution if r["verdict"] == "VERIFIED")
        print(f"[resolve] ✓ currency verified against the broker row for {n_ok} name(s).")

    # RS percentile rank across everything we could score, EXCLUDING speculatives.
    #
    # A speculative is a pre-revenue, 100%+ volatility name held at a small fixed stake with no stop. Its raw
    # excess return is useful ("is it running?"), but ranking it against AVGO or Barrick is
    # not: it will sit at an extreme in one direction or the other, and it drags the
    # distribution that every core name's percentile is measured against. Speculatives keep a
    # raw RS score and are reported in their own section; they take no percentile, and they
    # cannot be tagged RS-LEADER — "strongest in the universe" is a claim about the core
    # book, and a speculative flyer topping that list would be a misleading readout.
    for r in rows:
        r["speculative"] = r["ticker"] in speculatives
    core = [r for r in rows if r["rs"] is not None and not r.get("speculative")]
    scored = sorted(core, key=lambda r: r["rs"])
    for i, r in enumerate(scored):
        r["rs_pctl"] = 100.0 * i / max(1, len(scored) - 1)
    for r in rows:
        r.setdefault("rs_pctl", None)
        if r["rs_pctl"] is not None and r["rs_pctl"] >= RS_LEADER:
            r["flags"].append("RS-LEADER")

    # staleness: compare each name's last bar against the universe's newest
    newest = max((r["last_ts"] for r in rows if r["last_ts"]), default=None)
    stale = []
    if newest:
        for r in rows:
            if r["last_ts"] and (newest - r["last_ts"]) > 86400 * 1.5:
                days = int((newest - r["last_ts"]) / 86400)
                stale.append(f"{r['ticker']} ({days}d)")

    # holdings + prior-run state
    #
    # THE SAME-DAY RE-RUN PROBLEM. `radar_state.json` is "flags as of the last
    # run" and drives the "New today" column — where *today* means "versus the
    # previous DAY". The day's first run overwrites yesterday's copy, so a
    # SECOND run on the same day would diff today against today and mark
    # nothing new: a freshly-fired AT-PEAK or ROUND-TRIP-RISK would vanish from
    # the column purely because you ran the pipeline twice. Running twice is
    # supported (decision 2026-08-23 — a re-run is permitted, so the collision
    # is fixed rather than blocked), which needs two files:
    #
    #   radar_state.json       flags as of the last run, whenever that was
    #   radar_state.prev.json  flags as of the last run on an EARLIER DAY
    #
    # The day's first run rotates the former into the latter before overwriting
    # (see the write site). Every run reads whichever file is genuinely from an
    # earlier day, so run 2 reports the same "new today" set as run 1.
    run_day = datetime.date.today().isoformat()
    baseline_path = (a.state[:-5] if a.state.endswith(".json") else a.state) + ".prev.json"

    def read_flag_state(path):
        """(flags, date) from a state file, or None if absent/unreadable."""
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                st = json.load(f)
            return (st.get("flags") or {}), st.get("date")
        except (OSError, ValueError) as e:
            # prev_state drives the "New today" comparison. Losing it silently
            # marks nothing as new and drops the footnote, so a newly-fired
            # AT-PEAK or ROUND-TRIP-RISK reads as pre-existing. Verified
            # 2026-08-23 by corrupting the file (docs/BACKLOG.md 21.3).
            print(f"[state] ⚠️  {os.path.basename(path)} exists but could not "
                  f"be read ({e.__class__.__name__}) — NOTHING is marked 'new "
                  f"today' this run; treat every flag as unchanged-unknown",
                  file=sys.stderr)
            return None

    held = load_holdings(here)
    prev_state = {}
    prev_date = None
    on_disk = read_flag_state(a.state)
    on_disk_date = on_disk[1] if on_disk else None
    if on_disk and on_disk_date == run_day:
        # Written by an earlier run TODAY — reach past it to the retained
        # previous-day baseline rather than diffing today against itself.
        base = read_flag_state(baseline_path)
        if base:
            prev_state, prev_date = base
            print(f"[state] ℹ️  second run today — 'new today' compares against "
                  f"{prev_date} via {os.path.basename(baseline_path)}",
                  file=sys.stderr)
        else:
            print(f"[state] ℹ️  second run today and no "
                  f"{os.path.basename(baseline_path)} to fall back on — nothing "
                  f"is marked 'new today' this run", file=sys.stderr)
    elif on_disk:
        prev_state, prev_date = on_disk

    for r in rows:
        h = held.get(r["ticker"])
        r["held"] = h
        old = set((prev_state.get(r["ticker"]) or "").split())
        r["new_flags"] = [f for f in r["flags"] if f not in old] if prev_state else []

    def key(r):
        return (0 if "HEARTBEAT" in r["flags"] else 1,
                0 if "AT-BREAKOUT" in r["flags"] else 1,
                -(r["rs_pctl"] if r["rs_pctl"] is not None else -1))
    rows.sort(key=key)

    today = datetime.date.today().isoformat()
    newest_str = (datetime.datetime.utcfromtimestamp(newest).strftime("%Y-%m-%d")
                  if newest else "n/a")

    L = [f"# Heartbeat Radar — {today}",
         "",
         f"*Universe: {len(tickers)} tickers — "
         f"{sum(1 for v in provenance.values() if v == 'held')} held and "
         f"{sum(1 for v in provenance.values() if v == 'watchlist')} watchlist "
         f"(auto-derived from the broker CSVs and watchlist files), "
         f"{sum(1 for v in provenance.values() if v == 'tracking')} tracking "
         f"`input/tracking/` (Tier 0 — radar-only, not evaluated) · {len(rows)} analysed · "
         f"{len(too_new)} too new · {len(errs)} failed. Newest bar in data: **{newest_str}**. "
         f"GBP/USD {fx:.4f}.*",
         "",
         "*Mechanics: 150-day exit line (50-day fallback, marked `50d*`, for names with "
         "under 160 sessions); prior-high breakout; 2x volume trigger with direction; "
         "heartbeat = 20-day range in the bottom quartile of the name's own 1-year range "
         "distribution + volume drying up above a rising line. RS = recency-weighted 3/6/12-month "
         "excess return vs SPY (USD) or ISF.L (GBP), percentile-ranked across the universe. "
         "Sector direction is read from bellwether ETF gauges (`sector_map.md`), not "
         "member averages. Data: Yahoo daily.*",
         "",
         "| Ticker | Held | Price | Line | %Line | Trend | 50d | Breakout | %Brk | %52wH | RS | Vol | Rng20 (pctl) | Acc | Flags | New today |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    for r in rows:
        h = r["held"]
        held_s = "—"
        if h:
            acct, gain = h
            held_s = f"{acct} {gain:+.1f}%" if gain is not None else acct
        rs_s = f"{r['rs_pctl']:.0f}" if r["rs_pctl"] is not None else "—"
        arrow = {"UP": "▲", "DOWN": "▼"}.get(r["vdir"] or "", "")
        vol_s = f"{r['vratio']:.1f}x" + (f" {arrow}{r['vago']}d" if arrow and r["vratio"] >= 1.5 else "")
        rng_s = (f"{r['rng20']:.1f}% ({r['rng_pctl']:.0f})"
                 if r["rng20"] is not None else "—")
        acc_s = f"{r['acc']:.2f}" if r["acc"] else "—"
        L.append(
            f"| **{r['ticker']}** | {held_s} | {r['px']:.2f} {r['cur']} | "
            f"{r['ma']:.2f} {r['line_label']} | {r['pct_to_line']:+.1f}% | {r['trend_main']} | "
            f"{r['trend50']} | {r['breakout']:.2f} | {r['pct_to_break']:+.1f}% | "
            f"{r['pct_from_hi']:+.1f}% | {rs_s} | {vol_s} | {rng_s} | {acc_s} | "
            f"{' '.join(r['flags']) or '—'} | {' '.join(r['new_flags']) or '—'} |")

    if prev_state:
        L += ["", f"*'New today' compares against the previous run ({prev_date}).*"]
    elif on_disk_date == run_day:
        L += ["", "*Second run today with no retained previous-day baseline — "
                  "nothing is marked new. This is a re-run artefact, not a "
                  "quiet tape.*"]
    else:
        L += ["", "*No prior state file — this is a baseline run, so nothing is marked new.*"]

    # ---- ROTATION READ ------------------------------------------------------
    # OVERHAUL (16 Aug 2026). Twelve changes shipped together — see CHANGES in the
    # header. Per-name flags are aggregated into sector clusters; the sector tag is
    # the result of a scoring rubric plus hard floor guards plus a gauge verdict.
    # Theme membership is a lens for interpreting a flag, never a gate for suppressing
    # one — a cluster of breakouts in an off-theme sector is the highest-value output.

    ARRIVE_EARLY = ("HEARTBEAT",)                       # pre-breakout coiling
    ARRIVE_LATE  = ("AT-BREAKOUT",)                     # already broke the box
    ARRIVE = ARRIVE_EARLY + ARRIVE_LATE
    LEAVE = ("ROUND-TRIP-RISK", "BELOW-RISING-LINE")

    # Sector -> {in:[], out:[], early:[], late:[], conflict:[], round_trip:[]}
    # Conflict tracks names counted in BOTH columns (arrive AND leave).
    # Round-trip overrides the arrive side (a name at a breakout that is also
    # round-trip is a trap, not an arrival).
    # SUSTAINED membership is computed here, not in analyse(), because it is
    # ranked against the universe and the universe does not exist until every
    # name is fetched and `rs_pctl` is assigned. See mark_sustained().
    n_sus, sus_acc_floor = mark_sustained(rows)

    agg = {}
    for r in rows:
        sec = sectors.get(r["ticker"], "Unclassified")
        d = agg.setdefault(
            sec, {"in": [], "out": [], "early": [], "late": [],
                  "conflict": [], "round_trip": [], "sustained": []})
        fl = set(r["flags"])
        is_early = "HEARTBEAT" in fl and "ROUND-TRIP-RISK" not in fl
        is_late  = "AT-BREAKOUT" in fl and "ROUND-TRIP-RISK" not in fl
        is_leave = bool(fl & set(LEAVE))
        is_rt    = "ROUND-TRIP-RISK" in fl
        if is_early: d["early"].append(r["ticker"])
        if is_late:  d["late"].append(r["ticker"])
        if is_early or is_late: d["in"].append(r["ticker"])
        if is_leave: d["out"].append(r["ticker"])
        if is_rt:    d["round_trip"].append(r["ticker"])
        if (is_early or is_late) and is_leave:
            d["conflict"].append(r["ticker"])
        # A name can be both arriving and sustained (AT-BREAKOUT on a name that
        # is also near its 52-week high). That is not double-counting: the two
        # columns answer different questions and only ONE tag is ever emitted,
        # with the arrival read taking precedence in classify().
        if r.get("sustained"):
            d["sustained"].append(r["ticker"])

    # Sector size (drives size-normalised floors).
    size_of = {}
    for r in rows:
        sec = sectors.get(r["ticker"], "Unclassified")
        size_of[sec] = size_of.get(sec, 0) + 1

    # Gauge verdict — bellwether ETF vs 150d direction, given proposed tag.
    def gauge_verdict_for(sec, proposed_tag):
        info = bell_reads.get(sec)
        if not info:
            return "-", None
        parts = [(bt, d) for bt, d in info if d is not None]
        if not parts:
            return "ERROR", None
        pcts = [d["pct"] for _, d in parts]
        moms = [d["r20"] for _, d in parts if d.get("r20") is not None]
        is_inlike = proposed_tag in ("IN", "STRONG-IN", "CHASING")
        is_outlike = proposed_tag in ("OUT", "FADING-OUT", "EXHAUSTED")
        up = sum(pcts) > 0
        if is_inlike:
            v = "CONFIRMED" if up else "CONFLICT"
        elif is_outlike:
            v = "CONFIRMED" if not up else "CONFLICT"
        else:
            v = "-"
        mom = sum(moms) / len(moms) if moms else None
        return v, mom

    # ---- SCORING RUBRIC + FLAGS-TO-TAG (Tier 1 #1, #2, #3; Tier 3 #7) ------
    # IN/OUT are scored:
    #   score_in  = in - 2*out + 0.5*(early-late) + 0.3*gauge_momentum
    #   score_out = out - 2*in + 0.5*(late-early) - 0.3*gauge_momentum
    # with size-normalised floors, the old > 2x ratio preserved, and a >= 1.0
    # score floor. MIXED is its own half-state. Thin sectors (n<=2) get a
    # 1-name floor and require gauge CONFIRMED — on BOTH sides since
    # 2026-08-23 (see the out_min note below).
    def classify(sec, d):
        ni, no = len(d["in"]), len(d["out"])
        nr = len(d["round_trip"])
        ns = len(d["sustained"])
        early, late = len(d["early"]), len(d["late"])
        conflict_ct = len(d["conflict"])
        n = size_of.get(sec, ni + no)
        in_min_base = max(2, (n + 4) // 5)
        out_min_base = max(3, (n + 4) // 5)
        is_small = n <= 2
        in_min = 1 if is_small else in_min_base
        # THE OUT FLOOR MIRRORS THE IN FLOOR (2026-08-23, docs/BACKLOG.md 23.1).
        #
        # It did not, and the asymmetry was invisible: `in_min` dropped to 1 for
        # a thin sector while `out_min_base = max(3, ...)` stayed at 3, so a
        # sector of one or two members could signal ARRIVAL from its own members
        # and could not signal DEPARTURE from them at any price. Both of
        # Shipping's two names going BELOW-RISING-LINE produced no tag at all,
        # while either one arriving produced STRONG-IN.
        #
        # The gauge fallback further down was already symmetric (it can reach
        # FADING-OUT), so this was never "a thin sector can never read as
        # leaving" — it is narrower and more awkward than that: the *members*
        # could not say it, only the bellwether could, and only while carrying a
        # ROUND-TRIP-RISK / BELOW-RISING-LINE flag of its own. A held single-name
        # sector (Japan/IJPN.L) whose own line broke down under a bellwether that
        # was merely flat said nothing.
        #
        # Mirrored exactly, including the guard that makes the IN side safe: the
        # relief applies only when the gauge CONFIRMS the direction. Never weaken
        # the exit side — this strengthens it, and the guard is what stops one
        # name in a one-name sector from being a rotation on its own.
        out_min = 1 if is_small else out_min_base

        gauge_in, gmom = gauge_verdict_for(sec, "IN")
        gauge_out, _gout_mom = gauge_verdict_for(sec, "OUT")
        # THE SCORES BELOW ARE FLAGS-ONLY AND STAY THAT WAY. `ns` is deliberately
        # absent from both.
        #
        # The diagnosis asked for SUSTAINED to be "scored on the arrival side at
        # reduced weight", and the first cut did exactly that — `score_in +=
        # SUS_WEIGHT * ns`. A containment test (SUS_WEIGHT cranked to 1000, which
        # must change no tag if the weight is really only a tiebreak) showed that
        # it leaks, in the one direction that matters most:
        #
        #   * `mixed_dominates` tests `score_out >= score_in + 1.0`. Inflating
        #     score_in makes that false, so a round-trip-heavy sector escapes into
        #     MIXED. Live: Defence, in 1 / out 8, flipped EXHAUSTED -> MIXED.
        #   * `elif out_pass and (not in_pass or score_out >= score_in)` is worse
        #     still — losing that comparison drops the sector through to `else`
        #     and DELETES the OUT tag outright.
        #
        # Both let a sector shedding names hide behind its survivors, which is
        # precisely what must never happen. The score therefore carries the
        # sustained term only in the *reported* value (`score_report` below), and
        # only for a sector whose tag actually is SUSTAINED. Every tag decision
        # in this function reads the flags-only scores, and `ns` reaches a tag
        # through exactly one door: the SUSTAINED block at the end.
        #
        # The narrower rule has a second benefit worth keeping: every non-
        # SUSTAINED sector's reported score is bit-identical to what it was
        # before item 5, so `Speed` — which compares today against a 3-run mean
        # drawn from history written by the old code — stays comparable across
        # the change instead of quietly drifting for one window.
        score_in  = ni - 2 * no + 0.5 * (early - late) + 0.3 * (gmom or 0)
        score_out = no - 2 * ni + 0.5 * (late - early) - 0.3 * (gmom or 0)

        big_both = (ni >= 2 and no >= 2) and (1/3 <= ni / max(1, no) <= 3)
        rt_heavy = (nr >= 3 and nr >= 0.30 * (ni + no + nr))
        mixed_first = big_both or rt_heavy
        mixed_dominates = mixed_first and not (
            (score_in >= score_out + 1.0 and ni >= in_min) or
            (score_out >= score_in + 1.0 and no >= out_min))

        # Hard gates: size-normalised floor AND ratio. Score is a tiebreaker,
        # not a hard gate — a 6-leaving, 2-arriving cluster with a rising
        # bellwether is exactly the divergence case score was meant to surface,
        # not one it should silently drop. (`score_out = -0.41` here, which
        # correctly fails a >= 1.0 floor — the gauge is contradicting the
        # cluster — so we want the cluster's read to stand and let MIXED/
        # FADING-OUT capture the contradiction.)
        in_floor_passes = ni >= in_min
        in_ratio_passes = (no == 0 and ni >= 1) or ni > 2 * no
        in_pass = in_floor_passes and in_ratio_passes
        if is_small:
            in_pass = in_pass and gauge_in == "CONFIRMED"

        out_floor_passes = no >= out_min
        out_ratio_passes = (ni == 0 and no >= 1) or no > 2 * ni
        out_pass = out_floor_passes and out_ratio_passes
        if is_small:
            out_pass = out_pass and gauge_out == "CONFIRMED"

        # Tag resolution: MIXED when both ratios are >1.5 (cluster genuinely
        # in motion both ways), OR the score lies decisively negative on the
        # side that wins on ratio. Otherwise the side whose ratio passes.
        if mixed_dominates:
            tag = "MIXED"
        elif in_pass and (not out_pass or score_in > score_out):
            # Phase suffix from early/late split.
            if late > early:
                tag = "CHASING"
            elif early > late:
                tag = "STRONG-IN"
            else:
                tag = "IN"
        elif out_pass and (not in_pass or score_out >= score_in):
            tag = "OUT"
        else:
            tag = "-"

        # ---- Change B: sparse-cluster gauge fallback (16 Aug 2026) ---------
        # When the cluster itself has too few flags to satisfy the 2x ratio,
        # the tag lands at "-" with no quorum. That is information-free — a
        # sector with one leaving name and 0 arriving today is the same
        # "no flag" reading as five sectors going through a quiet day.
        # The gauge, by contrast, is a single instrument on every session —
        # it always has a HEARTBEAT/AT-BREAKOUT/ROUND-TRIP-RISK read.
        # If the cluster activity is sparse (broad denom, low flag count)
        # the gauge can legitimately lead the read, *provided* the gauge
        # verdict confirms the direction. This is a rescue, not a
        # replacement: it kicks in only when the cluster tag above has
        # dropped to "-" AND the flag density is below 30% of the sector
        # roster (the dense-cluster reading takes precedence over a
        # thin-cluster gauge lead for any sector producing real activity).
        gauge_flags: list[str] = []
        gauges_for_sec = bell_reads.get(sec) or []
        for _, gd in gauges_for_sec:
            if gd and gd.get("flags"):
                gauge_flags.extend(gd["flags"])
        gauge_set = set(gauge_flags)        # local — membership tests only;
                                           # the JSON field below stays a list
                                           # (a set fails json.dump and was the
                                           # silent cause of mid-write corruption
                                           # for the live rotation_history.json).

        activity = ni + no
        sparse_floor = max(2, (n + 9) // 10)  # 30%-of-roster, min 2

        # `from_gauge` RECORDS THE PROVENANCE OF THE TAG, and is the only thing
        # that does (2026-08-23). It replaces `tag in ("STRONG-IN","FADING-OUT")`,
        # which inferred provenance from the tag's NAME and was wrong twice over:
        # it marked a member-derived STRONG-IN as a gauge read, and it silently
        # broke the moment the fallback stopped hard-coding "FADING-OUT" (see
        # just below). Provenance is a fact about how this function reached the
        # tag — it must be recorded where that happens, never re-derived after.
        from_gauge = False

        if tag == "-" and activity <= sparse_floor:
            # IN-shape fallback — gauge telling us the sector is basing/breaking.
            # Phase from gauge: HEARTBEAT (still coiling below 150d) → STRONG-IN;
            # AT-BREAKOUT (gauge already broke out above 150d) → CHASING.
            if gauge_in == "CONFIRMED":
                if "HEARTBEAT" in gauge_set:
                    tag, from_gauge = "STRONG-IN", True
                elif "AT-BREAKOUT" in gauge_set:
                    tag, from_gauge = "CHASING", True
            # OUT-shape fallback — gauge telling us distribution. `gauge_out`
            # is computed once beside `gauge_in` now that the OUT floor consults
            # it too; this block used to derive its own copy of the same value.
            #
            # EMITS THE BARE "OUT", NOT "FADING-OUT" (2026-08-23). Hard-coding
            # the intensity here skipped the Tier 3 #8 post-process that derives
            # EXHAUSTED / FADING-OUT from the persistence trend — so this branch
            # printed a *fading* intensity beside a trend column that said STABLE
            # or EXHAUSTED, on every run, disagreeing with the evidence next to
            # it. The intensity belongs to the layer that has the history; this
            # branch only knows the direction.
            if gauge_out == "CONFIRMED" and (
                    "ROUND-TRIP-RISK" in gauge_set
                    or "BELOW-RISING-LINE" in gauge_set):
                tag, from_gauge = "OUT", True

        # ---- SUSTAINED — the continuation tag (backlog item 5) ------------
        # Applied LAST, and only to a tag that is still "-". Every other read
        # outranks it, by design and in this order:
        #   * IN / STRONG-IN / CHASING — a fresh arrival is the more valuable
        #     and more time-sensitive signal, and it is what the sizing rule
        #     is written against.
        #   * OUT / FADING-OUT / EXHAUSTED — a cluster shedding names is not
        #     rescued by the ones still standing. Never weaken the exit side.
        #   * MIXED — two-way motion is a more honest description than
        #     continuation when both sides are live.
        #   * the sparse-cluster gauge fallback — one instrument with an actual
        #     arrival flag beats an inference from membership breadth.
        # SUSTAINED therefore occupies the SILENCE and nothing else. On the run
        # that motivated it, that silence was a Gold cluster with no row at all.
        #
        # QUORUM: at least 2 names AND at least half the sector. "Sector language
        # must not launder single-name facts" (docs/SMART_MONEY_BOARD.md) — one
        # trending name is a name, not a rotation. The majority test is what
        # makes this breadth rather than a maximum.
        sus_min = max(2, (n + 1) // 2)
        sus_quorum = ns >= sus_min and (no == 0 or ns > 2 * no)
        # The gauge may not CONTRADICT. Unlike the IN side, "-" (no bellwether
        # configured for this sector) is permitted — most sectors have no gauge,
        # and requiring one would silently restrict the fix to the sectors that
        # happen to be instrumented. A CONFLICT/ERROR gauge does block it, which
        # is why SUSTAINED needs no counterpart to the 3-run gauge demotion.
        sus_gauge_ok = (gauge_in == "CONFIRMED" if is_small
                        else gauge_in in ("CONFIRMED", "-"))
        if tag == "-" and sus_quorum and sus_gauge_ok:
            tag = "SUSTAINED"

        # Reported score. The sustained term is added here and only here, and
        # only for a SUSTAINED sector — see the long note above the scores. It
        # gives `Speed` something that moves with the cohort, which for a
        # continuation is the only quantity that is moving at all.
        score_report = score_in - score_out
        if tag == "SUSTAINED":
            score_report += SUS_WEIGHT * ns

        return {"in": ni, "out": no, "early": early, "late": late,
                "round_trip": nr, "conflict": conflict_ct,
                "sus": ns, "sus_min": sus_min,
                "size": n, "score": score_report,
                "in_score": score_in, "out_score": score_out,
                "gauge_for_in": gauge_in, "gauge_mom": gmom or 0,
                "gauge_flags": gauge_flags,
                # `out_min`, not `out_min_base`: the reported floor must be the
                # one actually applied, or the `gap_out` readout below tells a
                # thin sector it needs 3 more leavers when it needs 1.
                "tag": tag, "in_min": in_min, "out_min": out_min,
                "gauge_fallback": from_gauge}

    rot_cur = {}
    for sec, d in agg.items():
        rot_cur[sec] = classify(sec, d)

    # Persist verbatim tag (with phase suffix) BEFORE applying demotion, so
    # the audit trail records what the cluster said vs what finally stuck.
    persist = rotation_persistence(a.rot_history, today, rot_cur)

    # ---- Tier 2 #5: Gauge persistence demotion -----------------------------
    # 3+ consecutive CONFLICT/ERROR gauge runs auto-demote IN/OUT (with phase
    # suffixes) to MIXED. Counter is persisted across runs.
    def gauge_conflict_streak(sec, today_gauge, out_like):
        """Consecutive runs whose bellwether CONTRADICTS the tag, ending today.

        Zero when today's gauge agrees: the streak is a *live* run of
        contradiction, not a count of contradictions somewhere in the recent
        past.

        `out_like` flips the test for an OUT-family tag — see `gauge_vs_tag`.
        The stored history field is IN-oriented on every run, including runs
        written before 2026-08-23, so the flip is applied on read and the whole
        history replays correctly under the new orientation.
        """
        def contradicts(g):
            return gauge_vs_tag(g, out_like) in ("CONFLICT", "ERROR")

        # TODAY GATES THE WHOLE STREAK (docs/BACKLOG.md 23.4). Tier 2e demotes
        # "until the gauge recovers", and a gauge that agrees today HAS
        # recovered — whatever it did on the three runs before. The previous
        # form seeded `s = 0` on agreement but still walked history, so a
        # recovered sector kept a streak of 3 and stayed demoted, which is the
        # opposite of what the rule says. Recovery clears; it does not decay.
        if not contradicts(today_gauge):
            return 0
        s = 1
        try:
            with open(a.rot_history) as f:
                prior = json.load(f).get("runs", [])
        except Exception:
            prior = []
        for r in reversed(prior):
            # THE STORED KEY IS `gauge_for_in`, NOT `gauge`. Both readers of
            # this history asked for `"gauge"`, which classify() has never
            # written — so `.get("gauge", "-")` returned "-" on every prior run,
            # "-" is not a contradiction, and the loop broke on its first
            # iteration. The streak could therefore never exceed 1 and the
            # Tier 2e demotion (fires at 3) has never once run: verified against
            # all 21 stored runs on 2026-08-23, max recorded streak 1, no `gauge`
            # key present anywhere. The header note claiming the streak is
            # "persisted in the history file so re-runs do not reset it"
            # described an intent, not the code. `"gauge"` is kept as a fallback
            # in case any history was ever written under that name.
            # SKIP TODAY'S OWN RECORD. `rotation_persistence()` above has
            # already written today's read into this file, so the history the
            # loop walks starts with the run we have just counted as `s = 1`.
            # Counting it again made every streak one larger than the number of
            # runs it described — the "3 consecutive runs" demotion actually
            # fired on 2 (measured 2026-08-23: Semis reported 5 across 4 dated
            # runs). Found while fixing 23.4; the twin counter inside
            # `rotation_persistence` reads `prior`, which excludes today, and
            # was never affected.
            if r.get("date") == today:
                continue
            rec = r.get("sectors", {}).get(sec) or {}
            g = rec.get("gauge_for_in", rec.get("gauge", "-"))
            if contradicts(g):
                s += 1
            else:
                break
            if s > 99:
                break
        return s

    for sec, c in rot_cur.items():
        # Tag-relative from here down. At this point in the flow the only
        # OUT-family tag is the bare "OUT" — FADING-OUT / EXHAUSTED are applied
        # by the Tier 3 #8 pass BELOW this one — but the tuple is written out in
        # full so that reordering the passes cannot silently un-fix this.
        out_like = c["tag"] in OUT_LIKE_TAGS
        c["gauge_vs_tag"] = gauge_vs_tag(c["gauge_for_in"], out_like)
        c["gauge_streak"] = gauge_conflict_streak(sec, c["gauge_for_in"], out_like)
        if c["tag"] in ("IN", "STRONG-IN", "CHASING", "OUT") and c["gauge_streak"] >= 3:
            c["pre_demote_tag"] = c["tag"]
            c["tag"] = "MIXED"

    # ---- Tier 3 #8: OUT tag with FADING-OUT / EXHAUSTED ----------------------
    for sec, c in rot_cur.items():
        if c["tag"] == "OUT":
            t = persist[sec]["trend"]
            if t == "EXHAUSTED":
                c["tag"] = "EXHAUSTED"
            elif t == "FADING":
                c["tag"] = "FADING-OUT"

    persist = rotation_persistence(a.rot_history, today, rot_cur)

    # ---- RENDER --------------------------------------------------------------
    L += ["", "## Rotation read — flag clusters by sector", "",

          "*Aggregated member flag clusters with **phase-split arrivals**. "
          "**EARLY** = HEARTBEAT (pre-breakout coiling); **LATE** = AT-BREAKOUT "
          "(already past the box). A sector with **only LATE arrivals** has a "
          "**CHASING** tag — most participants already own; the early rotation "
          "shape has passed. **STRONG-IN** is the early-shape case — fresh "
          "rotation with follow-through still to come.*",

          "*A sector losing many names *and* gathering a few new ones reads "
          "**MIXED**, its own tag, not a quietly-coded \"-\" — the most "
          "informative mid-state is now visible. Round-trip fraction >= 30% "
          "with material activity on both sides is the other MIXED trigger.*",

          "*Tag rules: **IN** / **STRONG-IN** / **CHASING** need score_in = "
          "`arrivals - 2x leavings + 0.5x(early-late) + 0.3x gauge_20d` >= 1.0, "
          "plus the old > 2x ratio, plus the size-normalised floor. **OUT** "
          "and its phases mirror. Single-stock sectors (<= 2 names) get a "
          "1-name floor and require gauge **CONFIRMED**. **Gauge enforcement:** "
          "3 consecutive CONFLICT/ERROR runs auto-demote the tag to MIXED.*",

          "***SUSTAINED** is the continuation state — the sector is neither "
          "arriving nor leaving, it is *already moving*. A name counts toward it "
          "when it is above a **rising** primary line, past its breakout box or "
          "within 10% of its 52-week high, **and** its accumulation and relative "
          "strength both sit at or above the universe median. It needs 2+ names "
          "and at least half the sector, so it is breadth, not a maximum. It is "
          "applied **last and only to a sector that would otherwise read `-`** — "
          "every arrival, departure, MIXED and gauge-led read outranks it. The "
          "scoring rubric stays flags-only, so the sustained cohort can neither "
          "lift a sector to ROTATION-IN nor soften a ROTATION-OUT; it reaches the "
          "Tag column through this one door and no other. Before it existed, such "
          "a sector produced no row in this table at all.*",

          "*Streak counts runs of the same base tag (phase suffixes ride on "
          "the streak — STRONG-IN -> CHASING is still streak 2 IN). Trend "
          "compares today's signed intensity to the 5-run mean (and reads "
          "opposite-way for OUT: leaving-falling = EXHAUSTED, leaving-growing = "
          "STRENGTHENING). Speed (ACCEL/DECEL) compares today's score to the "
          "3-run mean so a sector turning over without changing tag still "
          "surfaces here.*",

          "",
          "| Sector | In | Out | Sus | Net | Tag | Streak | Trend | Speed | "
          "Gauge | G-streak | EARLY | LATE | ! | Gap-IN | Gap-OUT | Arriving | "
          "Leaving | Sustained |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sec, d in sorted(
            agg.items(),
            key=lambda kv: (len(kv[1]["out"]) - len(kv[1]["in"]),
                            -len(kv[1]["in"]),
                            -len(kv[1]["sustained"]))):
        # A sector with sustained members and no flags on either side used to be
        # skipped here — silently, with no row. That single `continue` is where
        # the Gold cluster disappeared for 18 consecutive runs (diagnosis §2).
        #
        # The `tag != "-"` limb closes the same hole one layer over, found while
        # fixing this one: the sparse-cluster gauge fallback can tag a sector
        # with in=0 and out=0, and such a sector was ALSO skipped — so the
        # headline and the persistence line both named it while the table showed
        # nothing. On this run that was Japan, tagged CHASING with no row, which
        # `agents/manager.md` rule 11 requires to land on a buyable ticker.
        # A tag that renders nothing is the exact defect item 5 is about.
        if (not d["in"] and not d["out"] and not d["sustained"]
                and rot_cur[sec]["tag"] == "-"):
            continue
        c = rot_cur[sec]
        ni, no = len(d["in"]), len(d["out"])
        tag = c["tag"]
        tag_s = {
            "IN":         "**ROTATION-IN**",
            "STRONG-IN":  "**STRONG-IN**",
            "CHASING":    "**CHASING**",
            "SUSTAINED":  "**SUSTAINED**",
            "OUT":        "**ROTATION-OUT**",
            "FADING-OUT": "**FADING-OUT**",
            "EXHAUSTED":  "**EXHAUSTED**",
            "MIXED":      "**MIXED**",
        }.get(tag, "—")
        p = persist[sec]
        streak_s = f"{p['streak']}" if p["streak"] else "—"
        gs = c.get("gauge_streak", 0)
        # The tag-relative verdict, which is what this column is specified to
        # show. `gauge_for_in` is retained in the record (and in history) as the
        # raw IN-oriented reading; displaying it against an OUT tag inverted the
        # column's meaning — Utility read CONFLICT beside ROTATION-OUT while its
        # bellwether was falling in agreement.
        gauge_s = c.get("gauge_vs_tag", c["gauge_for_in"])
        if gauge_s in ("CONFLICT", "ERROR") and gs > 0:
            gauge_s = f"{gauge_s}({gs})"
        elif gauge_s == "-":
            gauge_s = "—"

        gap_in = max(0, c["in_min"] - ni)
        gap_out = max(0, c["out_min"] - no)
        conflict_s = str(len(d["conflict"])) if d["conflict"] else "—"

        L.append(
            f"| {sec} | {ni} | {no} | {len(d['sustained'])} | {ni - no:+d} | "
            f"{tag_s} | {streak_s} | "
            f"{p['trend']} | {p['speed']} | {gauge_s} | "
            f"{gs if gs else '—'} | {len(d['early'])} | {len(d['late'])} | "
            f"{conflict_s} | {gap_in} | {gap_out} | "
            f"{', '.join(d['in']) or '—'} | {', '.join(d['out']) or '—'} | "
            f"{', '.join(d['sustained']) or '—'} |")

    # Headline + persistence block.
    rot_in   = [s for s, c in rot_cur.items()
                if c["tag"] in ("IN", "STRONG-IN", "CHASING")]
    rot_out  = [s for s, c in rot_cur.items()
                if c["tag"] in ("OUT", "FADING-OUT", "EXHAUSTED")]
    rot_mix  = [s for s, c in rot_cur.items() if c["tag"] == "MIXED"]
    rot_sus  = [s for s, c in rot_cur.items() if c["tag"] == "SUSTAINED"]
    if rot_in or rot_out or rot_mix or rot_sus:
        # "already moving in" is its own clause, deliberately not folded into
        # "arriving". A reader who skims only this line must not come away
        # thinking a two-week-old trend is today's rotation.
        L += ["",
              f"**Headline:** money arriving in {', '.join(rot_in) or '—'}; "
              f"already moving in {', '.join(rot_sus) or '—'}; "
              f"leaving {', '.join(rot_out) or '—'}; "
              f"MIXED in {', '.join(rot_mix) or '—'}."]

        persist_bits = []
        for sec, c in rot_cur.items():
            if c["tag"] not in ("IN", "STRONG-IN", "CHASING", "OUT",
                                "FADING-OUT", "EXHAUSTED", "MIXED",
                                "SUSTAINED"):
                continue
            p = persist[sec]
            tag_word = c["tag"]
            if tag_word == "IN":
                tag_word = "ROTATION-IN"
            elif tag_word == "OUT":
                tag_word = "ROTATION-OUT"
            streak = p["streak"] if p["streak"] else "—"
            bit = f"{sec} {tag_word} run {streak}, {p['trend']}"
            if p["speed"] not in ("—", "STABLE", "NEW"):
                bit += f" ({p['speed']})"
            elif tag_word in ("STRONG-IN", "CHASING", "FADING-OUT", "EXHAUSTED",
                              "SUSTAINED"):
                bit += f" ({p['speed']})"
            if p["detail"]:
                bit += f" — {p['detail']}"
            persist_bits.append(bit)
        if persist_bits:
            L += ["", "**Persistence:** " + "; ".join(persist_bits) + "."]

    # Gauge-demotion warnings.
    demoted = [(sec, c.get("pre_demote_tag"), c["gauge_streak"])
               for sec, c in rot_cur.items() if c.get("pre_demote_tag")]
    if demoted:
        L += ["",
              "*! Gauge-demoted — the cluster-only tag was IN/OUT but the gauge "
              "has been CONFLICT/ERROR for 3+ runs, so it now reads MIXED. The "
              "members-only tag is recorded in parentheses:*",
              *[f"  · {sec}: was **{pt}**, gauge streak {gs} -> **MIXED**"
                for sec, pt, gs in demoted]]

    # ---- SECTOR PRESSURE (item 3.3) ----------------------------------------
    # Sits directly under the flag-cluster read because it is the same question
    # asked of the continuous measures rather than of the thresholded flags. It
    # is placed BEFORE the gauges: gauges are one instrument per sector, this is
    # the sector's own membership, and the membership read should be seen first.
    L += sector_pressure_section(rows, sectors)

    # ---- SECTOR GAUGES (bellwether ETFs) -----------------------------------
    # Added 26 Jul 2026. The In/Out table above counts member flags, which makes a
    # 2-name sector and a 30-name sector incomparable. Each sector's own level and
    # direction is therefore read from its bellwether ETF — same instrument class
    # for every sector. Gauges are measurement-only (see load_bellwethers).
    if bells:
        def vel_arrow(m20):
            # Velocity arrow for the gauge column: STRONG/UP/FLAT/DOWN/WEAK.
            if m20 is None:
                return "—"
            if m20 > 5:   return "^STRONG"
            if m20 > 1:   return "^UP"
            if m20 > -1:  return "=FLAT"
            if m20 > -5:  return "vDOWN"
            return "vvWEAK"

        def bell_cell(sec):
            parts = bell_reads.get(sec)
            if not parts:
                return "—"
            out = []
            for bt, d in parts:
                if d is None:
                    out.append(f"{bt} ?")
                else:
                    ar = {"Rising": "▲", "Falling": "▼"}.get(d["trend"], "→")
                    fl = " ".join(d.get("flags") or []) or "—"
                    out.append(f"{bt} {ar} {d['pct']:+.1f}% vs 150d · {fl}")
            return " · ".join(out)

        def mom(sec):
            vals = [d["r20"] for _, d in (bell_reads.get(sec) or [])
                    if d and d["r20"] is not None]
            return sum(vals) / len(vals) if vals else None

        L += ["", "### Sector gauges — bellwether ETFs", "",
              "*One reference ETF per sector supplies the sector's own direction. "
              "**Gauge flags (HEARTBEAT/AT-BREAKOUT/VOL-2X/ROUND-TRIP-RISK/etc.) are "
              "computed on the bellwether itself** and shown in the `Flags` column — "
              "for sectors with few members this is the cluster's only quorum. Gauges "
              "still do not enter the In/Out counts above (which remain breadth on "
              "member flags) but a CONFIRMED gauge carrying HEARTBEAT or AT-BREAKOUT "
              "rescues a small sector from reading `-`/`MIXED` to STRONG-IN. The "
              "Investable line is the roster vehicle a ROTATION-IN tag lands on — "
              "\"none\" means finding one is the run's EXPANSION task.*", "",
              "| Sector | Gauge (vs 150d) | 20d | Vel | Investable line (roster) |",
              "|---|---|---|---|---|"]
        for sec in sorted(bells, key=lambda s: (mom(s) is None, -(mom(s) or 0))):
            m20 = mom(sec)
            m20_s = f"{m20:+.1f}%" if m20 is not None else "—"
            L.append(f"| {sec} | {bell_cell(sec)} | {m20_s} | {vel_arrow(m20)} | "
                     f"{bells[sec]['investable'] or '—'} |")
        # SUSTAINED sectors land on a vehicle too. Before item 5 they produced no
        # rotation row, so the Investable-line step (agents/trader.md §1) never reached them
        # and a +22% move had no buyable line named against it for 18 runs. They
        # carry their own qualifier: a continuation is by construction already
        # extended, so it is closer to CHASING than to a fresh arrival, and the
        # doubled ETF cap explicitly does NOT apply (rules/02_SLEEVE_RULES.md).
        acts = [s for s in rot_in + rot_sus if bells.get(s, {}).get("investable")]
        for sec in acts:
            inv = bells[sec]["investable"]
            todo = ("no roster vehicle — finding one is this run's EXPANSION task"
                    if inv.lower().startswith("none")
                    else "run it through the gate card")
            L.append("")
            tag_word = c["tag"] if (c := rot_cur.get(sec)) else "ROTATION-IN"
            if tag_word in ("IN",):
                tag_word = "ROTATION-IN"
            elif tag_word == "STRONG-IN":
                tag_word = "STRONG-IN"
            elif tag_word == "CHASING":
                tag_word = "CHASING"
            qualifier = ""
            if tag_word == "CHASING":
                qualifier = " (treat as late entry — wait for a pullback)"
            elif tag_word == "SUSTAINED":
                qualifier = (" (continuation, not a fresh arrival — size at the "
                             "single-line cap, no doubled ETF cap)")
            L.append(f"**Actionable vehicle — {sec} ({tag_word}):{qualifier}** {inv} — {todo}.")
    uncl = [t for t in sectors if sectors[t] == "Unclassified"]
    if uncl:
        L += ["", f"*⚠️ {len(uncl)} ticker(s) untagged — add `@Sector` in "
                  f"`input/tracking/sector_map.md` (and/or `@Sector` in `tracking/universe.md`) "
                  f"{', '.join(sorted(uncl))}.*"]

    if a.rrg:
        L += sector_rrg_section(rows, sectors, a.rrg_state, today)

    if too_new:
        L += ["", "**Too new to screen (<60 sessions) — watch manually:** "
              + ", ".join(f"{r['ticker']} ({r['n']}d)" for r in too_new)]
    if stale:
        L += ["", "**Stale data (lagging the newest bar):** " + ", ".join(stale)]
    if errs:
        L += ["", "**Fetch failures:** " + ", ".join(t for t, _ in errs)]
    if mismatched:
        L += ["", "**⛔ TICKER IDENTITY UNRESOLVED — these rows are probably not your "
                  "holding.** The fetched series quotes in a currency the broker row "
                  "does not, which means the feed returned a different security under "
                  "the same symbol. Do not act on their signals; fix the mapping in "
                  "`input/tracking/sector_map.md`."]
        L += [f"- **{t}** ({RESOLVED_FROM.get(t) or '?'}): feed says {got}, broker row "
              f"says {want}" + (f"; `{alt}` quotes {altcur}" if alt else "")
              for t, want, got, alt, altcur in mismatched]
    if bell_errs:
        L += ["", "**Bellwether fetch failures (sector gauge blind):** " + ", ".join(bell_errs)]

    L += ["", "*Screen output only — every candidate still needs the full stack: fundamentals-screen "
          "score/Record Quarter, chart confirmation, darkpool, and pre-entry validation "
          "(earnings 7d / 52-wk high / consensus / TRAP CHECK).*"]

    outfile = a.out or os.path.join(OUTPUT_DIR, "radar", f"Heartbeat_Radar_{today}.md")
    os.makedirs(os.path.dirname(os.path.abspath(outfile)), exist_ok=True)
    with open(outfile, "w") as f:
        f.write("\n".join(L))

    # Rotate before overwrite. A state file from an EARLIER day is the only
    # honest "previous day" baseline there is; once this run overwrites it, a
    # second run today has nothing to diff against. Keep a copy. Failure here is
    # reported, never fatal — it costs a re-run's "new today" column, not the
    # report. (See the prior-run state block above for the full rationale.)
    if on_disk_date and on_disk_date != today:
        try:
            shutil.copyfile(a.state, baseline_path)
        except OSError as e:
            print(f"[state] ⚠️  could not retain {os.path.basename(baseline_path)} "
                  f"({e}) — a SECOND run today would mark nothing 'new today'",
                  file=sys.stderr)

    try:
        with open(a.state, "w") as f:
            json.dump({"date": today,
                       "flags": {r["ticker"]: " ".join(r["flags"]) for r in rows}}, f, indent=1)
    except (OSError, TypeError, ValueError) as e:
        # WRITE-SIDE MIRROR of the prev_state guard. Silently losing this makes
        # the NEXT run mark nothing as "new today" — a freshly-fired AT-PEAK or
        # ROUND-TRIP-RISK reads as pre-existing, tomorrow, for no visible reason.
        print(f"[state] ⚠️  could not write {os.path.basename(a.state)} ({e}) — "
              f"NEXT run will mark nothing 'new today'", file=sys.stderr)

    # Dated numeric snapshot (backlog item 4). Written AFTER radar_state.json so
    # that `new_flags` — which is computed against the previous run's state — is
    # already on the rows and gets stored alongside the numbers.
    #
    # A snapshot failure must never fail the radar: the markdown report is the
    # deliverable, this file is retention for a consumer that does not exist yet.
    # It is reported, not raised.
    snap_note = ""
    if not a.no_snapshot:
        snap_path = a.snapshot or os.path.join(
            state_dir, f"radar_snapshot_{today}.json")
        try:
            _atomic_write_json(snap_path, radar_snapshot(
                today, rows, sectors, provenance, bell_reads, fx, newest_str))
            dropped = prune_snapshots(os.path.dirname(os.path.abspath(snap_path)),
                                      a.snapshot_keep)
            gauge_n = sum(1 for parts in bell_reads.values()
                          for _, d in parts if d is not None)
            snap_note = (f"  snapshot: {snap_path} ({len(rows)} tickers, "
                         f"{gauge_n} gauge reads"
                         + (f", pruned {dropped}" if dropped else "") + ")")
        except Exception as e:
            snap_note = f"  snapshot: NOT WRITTEN — {type(e).__name__}: {e}"

    # Resolution manifest. The currency assertion happens here, where the feed is, but
    # it has to be checkable from `tools/checks.py`, which is offline by design (every
    # other check in that file reads a file on disk). So the verdict per ticker is
    # written out and the post-run gate reads it — the network call is not repeated,
    # and a run whose radar never happened fails the gate for the absence rather than
    # passing it for lack of evidence.
    try:
        with open(os.path.join(OUTPUT_DIR, ".state", "ticker_resolution.json"), "w") as f:
            json.dump({"date": today,
                       "corrected": [{"from": b, "to": g, "why": w, "currency": c}
                                     for b, g, w, c in corrected],
                       "mismatched": [{"ticker": t, "expected_currency": want,
                                       "fetched_currency": got, "alternate": alt,
                                       "alternate_currency": altcur}
                                      for t, want, got, alt, altcur in mismatched],
                       "resolution": sorted(resolution, key=lambda r: r["ticker"])},
                      f, indent=1)
    except (OSError, TypeError, ValueError) as e:
        # ticker_resolution.json is the canonical broker-symbol -> Yahoo-ticker
        # map. `tools/eval_reviewer.py:canonical_forms` reads it for check 20
        # and falls back to a looser suffix guess when it is absent, so losing
        # it silently weakens a check rather than breaking it — the quietest
        # possible failure. Say it out loud.
        print(f"[resolve] ⚠️  could not write ticker_resolution.json ({e}) — "
              f"eval_reviewer check 20 will fall back to loose ticker matching",
              file=sys.stderr)

    hb = sum(1 for r in rows if "HEARTBEAT" in r["flags"])
    print(f"written: {outfile}")
    print(f"  {len(rows)} rows · {hb} heartbeat · {len(too_new)} too new · {len(errs)} errors")
    if snap_note:
        print(snap_note)
    if stale:
        print(f"  stale: {', '.join(stale)}")


if __name__ == "__main__":
    main()
