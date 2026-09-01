# Disclaimer

**This repository is a personal process framework published for educational purposes. It is not financial advice, and nothing in it is a recommendation to buy or sell any security.**

## Specifically

- **No ticker in this repository is a recommendation.** This includes the real positions published under `input/` and `output/`. They are here so the process can be audited against something that actually happened — a rule you can watch fail is worth more than a worked example that always succeeds. **A position being held is not an argument that it should be.** Several of them will turn out badly, and the ledger will say so.
- **The published portfolio is scaled, not fictional.** Quantities and cash figures are multiplied by a single factor so the sleeve totals a nominal £100,000. Tickers, prices, entry levels, percentage gains and relative weights are real and unaltered; absolute position sizes are not. Do not read any figure here as a statement of the author's means, and do not infer position size from it.
- **The published history is not a track record.** It is a partial record of one person's decisions over a short period, with no benchmark, no risk adjustment and obvious survivorship in what got written down. It cannot support a claim that the method works.
- **Not validated on this book.** Whatever evidence stands behind the underlying techniques, this particular implementation — these constants, this universe, this sizing — has not been tested against it. The rules may be wrong. The gate ledger exists to find out: it is the mechanism, not evidence that the question is settled.
- **The author is not a financial adviser**, and this repository is not a regulated service. If you need advice, get it from someone authorised in your jurisdiction.
- **No tax or jurisdiction awareness.** Currency handling assumes a sterling base with USD positions. Tax treatment, account wrappers, reporting-fund status and stamp duty are entirely out of scope.
- **Data sources may be wrong, stale or unavailable.** The tooling reports failures rather than hiding them, but reported data can still be incorrect. **Verify anything before acting on it.**
- **Past performance is not indicative of future results.** Momentum strategies in particular are prone to sharp drawdowns and long periods of underperformance.

## Use at your own risk

The software is provided "as is", without warranty of any kind. Trading involves risk of loss, including total loss of capital. **You are solely responsible for your own decisions.**

## Attribution

The method described in `rules/01_METHOD.md` is an original restatement of widely-taught momentum and breakout concepts — trend filtering, volume confirmation, consolidation bases, earnings acceleration. It reproduces no proprietary course material and deliberately names no vendor's methodology. Where the rules reference a data source, they specify **what the source must supply**, never which product you should buy.
