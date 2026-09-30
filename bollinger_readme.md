# bollinger mode

Bollinger band pierce condition group, optimized one parameter set at a time.

This mode is for when a Bollinger-band pierce is the main trigger or filter idea — for example, price piercing the lower band in the LONG direction, or the upper band in the SHORT direction.

## What this mode is for

Use this mode when mean-reversion or band-exursion is the main idea:

- low pierces below the Bollinger lower band for LONG,
- high pierces above the Bollinger upper band for SHORT.

It is a volatility-and-deviation-based condition, so it often behaves differently from trend or momentum groups and can be useful as either a trigger or a filter.

## Ultimate aim for this mode

The aim for this mode is to find the Bollinger setting that gives the best credible signal under the current trade model, not just the best hit rate in a small grid.

We want:

- the variant with the best hit rate,
- enough setups to trust it,
- a result that still looks reasonable on the supporting sheets,
- a chosen Bollinger base that can be reused later.

So the goal is a usable best candidate, not just a top-ranked one.

## What "best candidate" means here

For this mode, the best candidate is the parameter set that:

- has the best hit rate for the direction we care about,
- clears `analysis.min_setups_for_ranking`,
- does not rely on a tiny sample,
- holds up when we check the other sheets.

If two Bollinger variants are close, the better candidate is the one that is more stable and easier to reuse.

## How we achieve it

We achieve it by testing this group in isolation and then ranking it honestly:

1. Enable only the bollinger condition group.
2. Keep the entry-candle rule fixed.
3. Sweep `bb_period` and `bb_num_std` as needed.
4. Run on the available day files and timeframes.
5. Open the `RANKINGS` sheet for the day and for the combined workbook.
6. Drop out candidates that do not have enough setups.
7. Compare the remaining candidates on hit rate and on the other sheets.
8. Save the chosen candidate clearly.

That is how we narrow a broad band-pierce space into one chosen base.

## How we find the best possible candidate

We find the best possible candidate by reading the results in layers:

- **Hit rate** gives us the first cut.
- **Setup count** tells us which candidates are credible.
- **NO_ENTRY_COUNTS** tells us whether a variant is mainly working by rejecting a lot of triggers.
- **ALL_TRADES and ALL_TARGETS_HIT** tell us whether the result is broad or lucky.
- **Direction split** tells us whether the candidate favors LONG, SHORT, or both.

So the process is:

- rank by hit rate,
- filter by setup count,
- compare the survivors for stability,
- choose the one that is strong enough and believable enough to keep.

## What to save from this mode

Before moving on, record the chosen setting:

- which `bb_period` won,
- which `bb_num_std` won,
- whether it behaved better for LONG, SHORT, or both,
- whether it worked better as a trigger or as a filter.

That becomes the base for later combination.

## How this mode feeds the next mode

Once this mode has a chosen parameter set:

- keep that Bollinger setting active,
- layer the next mode on top of it,
- sweep the next mode's parameters while the chosen Bollinger setting stays fixed.

That keeps each round focused on one new group at a time.

## Stage 2 use

Later, you can combine this mode with others:

- bollinger + SMA/ATR mode,
- bollinger + RSI mode,
- bollinger + price_vs_sma9 mode,
- bollinger + sma44_band mode,
- bollinger + oi_compare mode,
- bollinger + stage-2 variants of other modes.

Rank the combinations the same way as the individual modes.

## Practical notes

- Because both `bb_period` and `bb_num_std` can be lists, this mode can produce a lot of combinations quickly. Start with a small grid before expanding.
- Bollinger pierces can be rare on some days or some timeframes, so pay attention to setup counts, not just hit rate.
- If a variant only works in one direction, note that clearly before combining it with other modes.
