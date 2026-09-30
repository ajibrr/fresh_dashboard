# sma_rising_atr mode

First optimization mode. One condition group at a time, sweep its parameters, pick the best hit-rate combination from the Excel `RANKINGS` sheet, then freeze that finding for the next mode.

This mode is the starting point for the whole pipeline. The idea is not to test everything at once — it is to find the best parameter set for this one group first.

## What this mode is for

`sma_rising_atr` is the SMA-trend / SMA-crossover condition group with an ATR filter on top.

In plain terms:

- The market should be in a rising SMA regime, or
- Price should cross the SMA in the desired direction,

and optionally the move should also have enough range (ATR) so the signal is not just noise.

This is the simplest directional group to start with because the logic is easy to read and easy to sweep.

## Ultimate aim for this mode

The aim for this mode is not to prove that SMA plus ATR is the best strategy overall. The aim is narrower:

- find the single best parameter set for this condition group, on the current data and under the current trade model,
- in a way that can be trusted enough to become the base for later modes.

So the goal is a repeatable best candidate, not a final verdict on the indicator itself.

## What "best candidate" means here

For this mode, the best candidate is the parameter set that:

- has the highest hit rate for the direction(s) we care about,
- clears `analysis.min_setups_for_ranking`, so it is not just a small-sample lucky result,
- looks reasonable on the supporting sheets, not only on the top line,
- is simple enough to keep using as a base in later rounds.

If two parameter sets have the same hit rate, the better candidate is the one with more setups, cleaner behavior on `NO_ENTRY_COUNTS`, and less fragile-looking results on `ALL_TRADES` and `ALL_TARGETS_HIT`.

## How we achieve it

We achieve it by isolating this mode first and then ranking it honestly:

1. Enable only this mode's condition group.
2. Keep the entry-candle rule fixed.
3. Sweep the SMA/ATR parameters as a cartesian product.
4. Run on the available day files and timeframes.
5. Open the `RANKINGS` sheet for the day and for the combined workbook.
6. Pick the top candidate that also has enough setups to matter.
7. Save that candidate clearly before moving on.

That sequence is what turns a big parameter space into one chosen base setting.

## How we find the best possible candidate

We find the best possible candidate by comparing variants on more than one signal:

- **Hit rate** is the main filter.
- **Setup count** is the trust filter.
- **NO_ENTRY behavior** tells us whether the candidate is just producing fewer triggers in a meaningful way.
- **ALL_TRADES / ALL_TARGETS_HIT** tell us whether the top hit rate is coming from a few lucky trades or from a stable pattern.
- **Direction split** tells us whether the candidate is strong for LONG, SHORT, or both.

So the process is:

- rank by hit rate first,
- then remove candidates that do not have enough setups,
- then compare the remaining candidates on the other sheets,
- then choose the one that is both strong and believable.

If several candidates look close, we prefer the one that is easier to explain and easier to reuse.

## What to save from this mode

Before moving on, write down the chosen parameter set for this mode:

- which SMA-based condition won,
- which SMA period,
- which ATR period,
- which ATR threshold or multiplier,
- which lookback,
- whether it worked better for LONG, SHORT, or both.

That saved finding becomes the base for the next mode.

## How this mode feeds the next mode

Once `sma_rising_atr` has a chosen parameter set:

- keep that set active as the base condition,
- add the next mode's condition group on top of it,
- sweep the new mode's parameters while the chosen `sma_rising_atr` setting stays frozen.

That way each new mode is evaluated on top of a chosen base instead of starting from scratch every time.

## Stage 2 use

After you have a few individual modes nailed down, you can combine them:

- `sma_rising_atr` + another mode,
- `sma_rising_atr` + stage-2 variant of another mode.

Rank those combinations the same way as the single modes. The `RANKINGS` sheet is the same handoff point.

## Practical notes

- Start with one direction if that is easier, then repeat for the other.
- If multiple parameter sets show 100% hit rate, compare them on sample size and on the other sheets before deciding.
- Do not jump to stage 2 until this mode has a clear best setting.
- The entry-candle rule stays the same across all of this unless you deliberately decide to test a different entry rule later.
