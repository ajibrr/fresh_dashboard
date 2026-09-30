# stage2_combos mode

Stage-2 combination modes. After individual modes have a chosen best parameter set, combine them and rank the combinations the same way as the single modes.

This is where the pipeline moves from single-indicator discovery to combined-signal discovery.

## What this mode is for

Use stage-2 combinations when you want to know whether two or more chosen modes improve signal quality together:

- mode 1 + mode 2,
- mode 2 + mode 4,
- mode 1 + stage-2 mode 1,
- mode 1 + stage-2 mode 2,
- and so on.

The point is not to pile on every condition at once. The point is to combine the modes that already looked promising on their own, then see which combinations actually deserve more attention.

## Ultimate aim for this mode

The aim for stage-2 combinations is to find the combination that gives the best usable signal quality, not just the most conditions together.

We want:

- a combination that is better than its parts in a way we can see in the ranking sheets,
- enough setups to trust it,
- a combination that is not just shrinking the sample without improving the result,
- a chosen combination that can be reused as the next base.

So the goal is a stronger, still-credible signal, not a bigger checklist.

## What "best candidate" means here

For stage-2, the best candidate is the combination that:

- has the best hit rate for the direction we care about,
- clears `analysis.min_setups_for_ranking`,
- improves on the single modes in a way the other sheets support,
- is simple enough to keep extending or to stop at.

If two combinations are close, the better candidate is the one that gives the better balance of hit rate, sample size, and interpretability.

## How we achieve it

We achieve it by building combinations from already-chosen mode findings and then ranking them the same way:

1. Start from chosen best settings for the individual modes.
2. Combine two or more of them in one config.
3. Keep the entry-candle rule fixed unless you are deliberately testing a different one.
4. Sweep only the parts that still need tuning, if any.
5. Run on the available day files and timeframes.
6. Open the `RANKINGS` sheet for the day and for the combined workbook.
7. Compare the combination against its parts, not just against itself.
8. Save the chosen combination clearly.

That is how we turn individual mode findings into a combined candidate.

## How we find the best possible candidate

We find the best possible candidate by comparing combinations on more than one measure:

- **Hit rate** tells us which combinations look strongest.
- **Setup count** tells us which of those are still trustworthy.
- **Comparison with the parts** tells us whether the combination is actually adding value.
- **NO_ENTRY_COUNTS** tells us whether the combination is only working by cutting triggers hard.
- **ALL_TRADES and ALL_TARGETS_HIT** tell us whether the improvement is broad or concentrated.
- **Direction behavior** tells us whether the combination is better for LONG, SHORT, or both.

So the search is:

- rank by hit rate,
- filter by setup count,
- check whether the combination beats its components,
- compare the survivors for stability and simplicity,
- choose the one that is strong enough and believable enough to keep.

## What to save from this mode

Before moving to the next stage, record:

- which combination won,
- which parameter sets were used,
- which direction it worked best in,
- whether it was stronger as a combination than as separate modes.

That record is what you use to decide whether to keep combining or stop at this stage.

## How stage-2 feeds the next stage

Once a stage-2 combination has a chosen best setting:

- keep that combination as the new base,
- add another mode on top if needed,
- rank the larger combination the same way.

You can keep stacking stages until the signal quality is where you want it, or until adding more modes stops helping.

## Stage-2 combination examples

Examples of how the combinations can be structured:

- mode 1 + mode 2,
- mode 2 + mode 4,
- mode 1 + mode 2 + mode 3,
- stage-2 combination + another mode,
- stage-2 combination + stage-2 variant of another mode.

Each combination is still ranked through the same `RANKINGS` process.

## Practical notes

- If a combination only looks better because it has fewer setups, check whether that is actually an improvement.
- If two modes overlap a lot, the combination may not add much. That is useful information too.
- Keep the entry-candle rule the same unless you deliberately decide to test a different entry rule.
- The `RANKINGS` sheet remains the handoff point between stages, same as for individual modes.
