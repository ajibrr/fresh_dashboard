# RSI mode

RSI-based condition group, optimized one parameter set at a time.

This mode is for when momentum or exhaustion is the main idea:

- RSI staying in a band for a while
- RSI reaching an extreme level
- RSI producing a signal over a lookback window

It is a separate group from the SMA/ATR group, so it can be studied on its own first and then combined later.

## What this mode is for

Use this mode when momentum or exhaustion is the main idea:

- RSI staying in a band for a while
- RSI reaching an extreme level
- RSI producing a signal compared with a previous lookback

It is a separate group from the SMA/ATR group, so it can be studied on its own first and then combined later.

## Ultimate aim for this mode

The aim for this mode is to find the RSI setting that gives the best usable signal under the current trade model, not just the best-looking number on one sheet.

We want:

- the RSI variant with the strongest hit rate,
- enough setups to trust it,
- a result that stays credible when we look at the other sheets,
- a chosen RSI base that can be reused later.

So the goal is a defensible best candidate, not a flashy one.

## What "best candidate" means here

For this mode, the best candidate is the RSI parameter set that:

- has the best hit rate for the direction we care about,
- clears `analysis.min_setups_for_ranking`,
- does not look like a tiny-sample artifact,
- behaves consistently enough on the supporting sheets to keep around.

If two RSI variants are close, the better candidate is the one that is more stable, not necessarily the one with the slightly higher top-line rate.

## How we achieve it

We achieve it by testing RSI on its own first and then judging it from the full ranking picture:

1. Enable only the RSI condition group.
2. Keep the entry-candle rule fixed.
3. Sweep RSI period, bounds, extreme level, and/or lookback as needed.
4. Run on the available day files and timeframes.
5. Open the `RANKINGS` sheet for the day and for the combined workbook.
6. Filter out candidates that do not have enough setups.
7. Compare the remaining candidates on hit rate and on the other sheets.
8. Save the chosen RSI candidate clearly.

That is how we turn a broad RSI space into one chosen base.

## How we find the best possible candidate

We find the best possible candidate by reading the results in layers:

- **Hit rate** tells us which variants look strongest.
- **Setup count** tells us which of those are worth trusting.
- **NO_ENTRY_COUNTS** tells us whether a variant is simply filtering out a lot of triggers.
- **ALL_TRADES and ALL_TARGETS_HIT** tell us whether the result is driven by a few trades or by a broader pattern.
- **Direction behavior** tells us whether the candidate is better for LONG, SHORT, or both.

So the search is:

- rank by hit rate,
- remove weak-sample candidates,
- compare the rest for stability,
- choose the one that is strong and repeatable enough to keep.

## What to save from this mode

Before moving on, record the chosen RSI setting:

- RSI period,
- which RSI condition type won,
- the bound or extreme level used,
- the lookback, if any,
- whether it behaved better for LONG, SHORT, or both.

That becomes the RSI base for later combination.

## How this mode feeds the next mode

Once this mode has a chosen parameter set:

- keep that RSI setting active,
- layer the next mode on top of it,
- sweep the next mode's parameters while the chosen RSI setting stays fixed.

That keeps each round focused on one new group at a time.

## Stage 2 use

Later, you can combine this mode with others:

- RSI + SMA/ATR mode,
- RSI + another indicator mode,
- RSI + stage-2 variants of other modes.

Rank the combinations the same way as the individual modes.

## Practical notes

- RSI can look great on a small sample, so check setup counts before trusting a top-ranked variant.
- Range and extreme conditions can mean very different things, so test them separately first.
- If a variant only works in one direction, note that clearly before combining it with other modes.
