# price_vs_sma9 mode

Price-vs-SMA9 condition group, optimized one parameter set at a time.

This mode is for when the relationship between price and SMA(9) is the main trigger idea, either as a standalone signal or as a filter on top of another mode.

## What this mode is for

Use this mode when you want the trigger to depend on how price behaves relative to SMA(9) over a window:

- price staying on one side of SMA(9),
- price crossing SMA(9),
- price reacting to SMA(9) in a certain way before the entry candle.

It is a simple, readable condition group, so it is a good candidate for early testing and for later combination.

## Ultimate aim for this mode

The aim for this mode is to find the price-vs-SMA9 setting that gives the most trustworthy signal under the current trade model, not just the prettiest hit rate.

We want:

- the variant with the best hit rate,
- enough setups to believe it,
- a result that still looks reasonable on the supporting sheets,
- a chosen setting that can be reused as a base later.

So the goal is a usable best candidate, not just a top ranking.

## What "best candidate" means here

For this mode, the best candidate is the parameter set that:

- has the best hit rate for the direction we care about,
- clears `analysis.min_setups_for_ranking`,
- does not depend on a tiny sample,
- holds up when we check the other sheets.

If two variants are close, the better candidate is the one that is more stable and easier to reuse.

## How we achieve it

We achieve it by testing this group in isolation and then ranking it honestly:

1. Enable only the price-vs-SMA9 condition group.
2. Keep the entry-candle rule fixed.
3. Sweep the window, behavior type, and any other relevant parameter.
4. Run on the available day files and timeframes.
5. Open the `RANKINGS` sheet for the day and for the combined workbook.
6. Drop out candidates that do not have enough setups.
7. Compare the remaining candidates on hit rate and on the other sheets.
8. Save the chosen candidate clearly.

That is how we narrow a broad window-based condition into one chosen base.

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

- which price-vs-SMA9 behavior won,
- the window length used,
- the direction or crossing rule used,
- whether it worked better for LONG, SHORT, or both.

That becomes the base for later combination.

## How this mode feeds the next mode

Once this mode has a chosen parameter set:

- keep that price-vs-SMA9 setting active,
- layer the next mode on top of it,
- sweep the next mode's parameters while the chosen price-vs-SMA9 setting stays fixed.

That keeps each round focused on one new group at a time.

## Stage 2 use

Later, you can combine this mode with others:

- price_vs_sma9 + SMA/ATR mode,
- price_vs_sma9 + RSI mode,
- price_vs_sma9 + stage-2 variants of other modes.

Rank the combinations the same way as the individual modes.

## Practical notes

- SMA(9) is also part of the entry-candle rule in the current trade model, so be careful not to confuse the trigger condition with the entry rule when you read the results.
- A condition that only works in one direction should be noted as such before you combine it.
- If a variant looks strong but has very few setups, treat it as interesting, not final.
