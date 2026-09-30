# sma44_band mode

SMA(44)-based high/low band condition group, optimized one parameter set at a time.

This mode is for when a higher-timeframe-style band around SMA(44) is the main trigger idea, either as a breakout-style filter or as a regime check.

## What this mode is for

Use this mode when you want the trigger to depend on price relative to an SMA(44)-based band:

- price breaking above or below the band in the trade direction,
- price holding relative to the band for a window,
- the band acting as a context filter on top of another mode.

It is a slower, broader condition group than SMA(9), so it often behaves more like a regime or structure filter.

## Ultimate aim for this mode

The aim for this mode is to find the SMA(44) band setting that gives the best credible signal under the current trade model, not just the best-looking hit rate in isolation.

We want:

- the variant with the best hit rate,
- enough setups to trust it,
- a result that still looks sensible on the supporting sheets,
- a chosen band setting that can be reused as a base later.

So the goal is a defensible best candidate, not a dramatic one.

## What "best candidate" means here

For this mode, the best candidate is the parameter set that:

- has the best hit rate for the direction we care about,
- clears `analysis.min_setups_for_ranking`,
- does not look like it only works because of a small sample,
- behaves consistently enough on the supporting sheets to keep.

If two band variants are close, the better candidate is the one that is more stable and easier to explain.

## How we achieve it

We achieve it by testing this group on its own first and then judging it from the full ranking picture:

1. Enable only the sma44_band condition group.
2. Keep the entry-candle rule fixed.
3. Sweep the band definition, behavior type, and direction as needed.
4. Run on the available day files and timeframes.
5. Open the `RANKINGS` sheet for the day and for the combined workbook.
6. Remove candidates that do not have enough setups.
7. Compare the remaining candidates on hit rate and on the other sheets.
8. Save the chosen candidate clearly.

That is how we turn a broad band-based condition into one chosen base.

## How we find the best possible candidate

We find the best possible candidate by reading the results in layers:

- **Hit rate** gives us the first sorting.
- **Setup count** tells us which top results are worth trusting.
- **NO_ENTRY_COUNTS** tells us whether a candidate is mainly working by cutting triggers aggressively.
- **ALL_TRADES and ALL_TARGETS_HIT** tell us whether the result is broad or concentrated.
- **Direction behavior** tells us whether the candidate favors LONG, SHORT, or both.

So the search is:

- rank by hit rate,
- filter by setup count,
- compare the survivors for stability,
- choose the one that is strong enough and believable enough to keep.

## What to save from this mode

Before moving on, record the chosen setting:

- which sma44_band behavior won,
- how the band was defined or used,
- the direction or side preference,
- whether it worked better for LONG, SHORT, or both.

That becomes the base for later combination.

## How this mode feeds the next mode

Once this mode has a chosen parameter set:

- keep that sma44_band setting active,
- layer the next mode on top of it,
- sweep the next mode's parameters while the chosen sma44_band setting stays fixed.

That keeps each round focused on one new group at a time.

## Stage 2 use

Later, you can combine this mode with others:

- sma44_band + SMA/ATR mode,
- sma44_band + RSI mode,
- sma44_band + price_vs_sma9 mode,
- sma44_band + stage-2 variants of other modes.

Rank the combinations the same way as the individual modes.

## Practical notes

- Because this is a slower band, it may screen out more triggers than a faster condition. That can be good or bad depending on what you want from the signal.
- If a variant only works in one direction, note that clearly before combining it with other modes.
- Compare the best band-based variants against the other modes on the same `RANKINGS` basis before deciding which one gets used as a base.
