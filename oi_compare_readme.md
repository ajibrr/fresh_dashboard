# oi_compare mode

Cumulative CE/PE open interest compare condition group, optimized one parameter set at a time.

This mode is for when the OI relationship between CE and PE is the main filter or trigger idea, especially on timeframes where the OI flow is carried forward from the 1-minute series.

## What this mode is for

Use this mode when you want the trigger to depend on OI imbalance:

- cumulative PE greater than cumulative CE for LONG,
- cumulative CE greater than cumulative PE for SHORT.

It is less about price shape and more about order-flow context, so it often works as a confirmation or filter on top of another mode.

## Ultimate aim for this mode

The aim for this mode is to find the OI setting that gives the best usable signal under the current trade model, not just the best hit rate on a small sample.

We want:

- the OI variant with the best hit rate,
- enough setups to trust it,
- a result that still looks credible on the supporting sheets,
- a chosen OI base that can be reused later.

So the goal is a defensible best candidate, not just a high number.

## What "best candidate" means here

For this mode, the best candidate is the parameter set that:

- has the best hit rate for the direction we care about,
- clears `analysis.min_setups_for_ranking`,
- does not look like it depends on very few setups,
- behaves consistently enough on the supporting sheets to keep.

If two OI variants are close, the better candidate is the one that is more stable and easier to reuse.

## How we achieve it

We achieve it by testing this group on its own first and then judging it from the full ranking picture:

1. Enable only the oi_compare condition group.
2. Keep the entry-candle rule fixed.
3. Sweep the OI side and any other relevant setting.
4. Run on the available day files and timeframes.
5. Open the `RANKINGS` sheet for the day and for the combined workbook.
6. Remove candidates that do not have enough setups.
7. Compare the remaining candidates on hit rate and on the other sheets.
8. Save the chosen candidate clearly.

That is how we turn a context indicator into one chosen base.

## How we find the best possible candidate

We find the best possible candidate by reading the results in layers:

- **Hit rate** gives us the first sort.
- **Setup count** tells us which top results are worth trusting.
- **NO_ENTRY_COUNTS** tells us whether a candidate is mainly working by filtering heavily.
- **ALL_TRADES and ALL_TARGETS_HIT** tell us whether the result is broad or lucky.
- **Direction behavior** tells us whether the candidate favors LONG, SHORT, or both.

So the process is:

- rank by hit rate,
- filter by setup count,
- compare the survivors for stability,
- choose the one that is strong enough and believable enough to keep.

## What to save from this mode

Before moving on, record the chosen setting:

- which OI side won for LONG,
- which OI side won for SHORT,
- whether it behaved better in one direction than the other,
- whether it worked better as a filter or as a trigger.

That becomes the base for later combination.

## How this mode feeds the next mode

Once this mode has a chosen parameter set:

- keep that OI setting active,
- layer the next mode on top of it,
- sweep the next mode's parameters while the chosen OI setting stays fixed.

That keeps each round focused on one new group at a time.

## Stage 2 use

Later, you can combine this mode with others:

- oi_compare + SMA/ATR mode,
- oi_compare + RSI mode,
- oi_compare + price_vs_sma9 mode,
- oi_compare + sma44_band mode,
- oi_compare + stage-2 variants of other modes.

Rank the combinations the same way as the individual modes.

## Practical notes

- OI is carried forward at sub-minute timeframes, so the condition can look available on more timeframes than the raw 1-minute series. Keep that in mind when comparing results across timeframes.
- Because OI is a context indicator, it may reduce setups more than it increases hit rate. That is not necessarily bad if it improves signal quality.
- If a variant only works in one direction, note that clearly before combining it with other modes.
