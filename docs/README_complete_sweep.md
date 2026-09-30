# Complete Sweep Mode

This is the single reference for a full cartesian sweep in the NIFTY directional strategy engine.

It replaces the old per-indicator README files. Instead of separate indicator READMEs, this document explains what a complete sweep is, what output it should produce, how to read that output, and how to reach a conclusion from it.

The goal of a complete sweep is not to print every possible combination. The goal is to produce one clean, comparable result that helps you pick the best usable candidate for one mode, then move on.

## What a complete sweep is

A complete sweep is a run where:

- one condition group is enabled at a time,
- the other groups are disabled,
- every parameter in that group is swept as a cartesian product,
- each combination is reported separately,
- the result is judged on more than hit rate alone.

This is the first discovery stage. One mode is discovered first, then combined with others later.

## What can be swept

A complete sweep may test any of the condition groups that exist in the project:

- SMA trend / SMA crossover with an ATR filter,
- RSI range, extreme, or signal lookback,
- price vs SMA(9) over a window,
- SMA(44)-based high/low band,
- cumulative CE/PE OI compare,
- Bollinger band pierces with `bb_period` and `bb_num_std`.

A complete sweep should test one group first. If you want to test multiple groups together, that is a later stage, not the first complete sweep.

## What a complete-sweep config should state

A complete-sweep config needs to be explicit. It should say:

- which condition group is being tested,
- which parameters are being swept,
- which values are being tested,
- the entry-candle rule,
- the RR multiples,
- the minimum setup threshold for ranking,
- the directions being tested,
- the timeframes being tested,
- whether only this condition group is enabled.

If any of those are vague, the output becomes hard to compare.

## What output a complete sweep needs

A complete sweep should produce output that lets you compare variants fairly.

The minimum useful output includes:

- one row per variant,
- variant parameters,
- direction,
- setups,
- entries,
- trades,
- no-entry count,
- hit rate,
- average RR achieved,
- stop rate,
- target hit rates by RR level,
- sample-size check,
- stability across days or timeframes if possible.

Hit rate by itself is not enough. A variant with a high hit rate and very few setups is not equivalent to a variant with a slightly lower hit rate and many more setups.

## Log structure for a complete sweep

The log for a complete sweep should be structured the same way every time.

That makes it possible to compare runs across modes and across rounds. A good complete-sweep log has these sections:

1. run header,
2. run settings,
3. sweep scope,
4. per-day top variants for each direction,
5. per-day no-entry and edge-case counts,
6. combined summary,
7. combined best variant for each direction,
8. near-best band around the best variant,
9. interpretation notes,
10. conclusion and next step.

The important part is consistency. If the tables change shape from run to run, the comparison gets messy.

## Log location in this repo

The sample complete-sweep log for this project is at:

- `sample.log`

That file is the shape every complete-sweep log should follow.

## How to read the log

Read it in this order:

- check the sweep scope first,
- check that only one condition group was enabled,
- check the per-day top variants,
- check whether the same variant looks good on both days,
- check the combined best variant,
- check the near-best band,
- check whether the top result depends on a few days or is spread out,
- check stop rate and target rates, not just hit rate,
- check sample size before trusting any top line.

If the same candidate keeps appearing across days and directions, that is usually a stronger signal than one high number in a single table.

## How to reach a conclusion

From a complete sweep, the conclusion should answer these questions:

- which variant is the best usable candidate,
- whether it is strong in one direction or both,
- whether it has enough setups to trust,
- whether its downside is acceptable,
- whether a near-best variant is worth keeping as a backup,
- whether the result is stable or fragile,
- what should be frozen for the next mode.

The conclusion should not be “highest hit rate wins.” It should be “best balance of hit rate, sample size, stability, and downside.”

## Primary and secondary candidates

A good complete-sweep conclusion usually names:

- a primary candidate,
- a secondary candidate,
- and the reason each was kept or rejected.

The primary candidate is the one you freeze first. The secondary candidate is the one to keep in mind if you care more about a different tradeoff, such as average RR versus hit rate.

## What to reject and why

Common reasons to reject a top-looking variant are:

- too few setups,
- result driven by only one or two days,
- much worse downside behavior,
- only works in one direction when you need both,
- looks good only because it has very few no-entry triggers but poor trade quality.

A variant can look tempting and still be the wrong pick if it fails the sample-versus-stability tradeoff.

## Near-best band

The near-best band matters because it shows whether the result is sensitive to small parameter changes.

If several nearby parameter sets perform almost as well, the result is more believable. If only one exact combination looks good, be more careful before freezing it.

## Conclusion example from the sample log

The sample log ends with a conclusion like this:

- primary candidate: `sma18_a14_m12_w3`,
- secondary candidate: `sma20_a14_m10_w3`,
- rejected: lower-hit-rate and higher-stop variants,
- next step: freeze the primary candidate and test the next mode on top of it.

The exact variant names do not matter as much as the reasoning pattern: pick the candidate that is strong, stable, and usable, not just the one with the highest number in one table.

## What this document replaces

This document replaces the old individual indicator README files.

Those files are no longer needed because this complete-sweep doc now covers:

- what gets swept,
- how output should look,
- how to read it,
- how to conclude from it,
- and how the result feeds the next mode.

If you want indicator-specific notes, they should live in the sweep config or in this doc, not in separate READMEs that repeat the same structure.

## How this fits the wider workflow

A complete sweep is one stage in the larger chain:

1. run a complete sweep for one mode,
2. reach a conclusion from the log and Excel sheets,
3. freeze the chosen candidate,
4. run the next mode on top of it,
5. repeat for each mode,
6. combine chosen modes in stage 2,
7. rank the combinations the same way.

The complete-sweep doc is the place that describes the first and most important stage: finding the best candidate for one mode from a full cartesian run.

## Clean log rules

To keep logs readable and comparable, follow these rules:

- use the same column order in every variant table,
- keep the same precision for rates,
- keep the same sweep-scope block in every run,
- keep a combined summary at the end,
- keep a near-best band,
- keep a conclusion block,
- keep a one-line conclusion at the very end.

If every run follows that pattern, the logs become easy to compare across modes and across rounds.

## End goal

The end goal of the complete sweep is to produce one chosen candidate per mode that is:

- strong enough,
- stable enough,
- believable enough,
- reusable as the base for the next mode.

If a sweep does not produce that, it has still done its job by showing which settings are not worth carrying forward.
