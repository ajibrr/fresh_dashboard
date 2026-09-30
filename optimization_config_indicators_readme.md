# optimization.json indicators

This is the indicator reference for the conditions you can put in `optimization.json`.

Each indicator below can be enabled or disabled, and any parameter set to a list is swept as part of the cartesian product. Each combination is reported separately in the optimizer output.

The indicator list is what the per-mode README files are built from.

## Indicator list

- **sma_rising_atr** — SMA trend / SMA crossover with an ATR filter.
- **rsi** — RSI range, extreme, or signal lookback conditions.
- **price_vs_sma9** — price relationship to SMA(9) over a window.
- **sma44_band** — SMA(44)-based high/low band condition.
- **oi_compare** — cumulative CE/PE OI compare condition.
- **bollinger** — Bollinger band pierce condition, with `bb_period` and `bb_num_std` sweepable.

## Ultimate aim for the indicator list

The aim of the indicator list is not to give every condition equal weight in one giant config. The aim is to give us a clean set of separate condition groups so we can:

- test one group at a time,
- find the best candidate in that group,
- then combine the best candidates later.

So the indicator list exists to support a stepwise search, not a one-shot sweep of everything.

## What "best candidate" means across indicators

Across indicators, the best candidate means the same thing in each mode:

- best hit rate for the direction we care about,
- enough setups to trust it,
- credible behavior on the supporting sheets,
- a result we can freeze and reuse in the next round.

The difference between indicators is only the condition logic, not the selection standard.

## How we achieve the aim with this list

We achieve the aim by using the same loop for every indicator:

1. pick one indicator group,
2. enable only that group,
3. sweep its parameters,
4. run on the available data,
5. read the `RANKINGS` sheet,
6. filter by setup count,
7. compare the survivors,
8. save the best candidate.

Then we repeat for the next indicator and combine later.

## How we find the best possible candidate from this list

We find the best possible candidate by treating each indicator as its own search first, then comparing combinations later.

For each indicator:

- rank by hit rate,
- filter by setup count,
- check the other sheets,
- choose the strongest believable candidate.

For combinations:

- compare the combination against its parts,
- keep only the ones that improve the picture,
- keep the process moving one stage at a time.

That is how the indicator list turns into a sequence of chosen candidates instead of one unreadable mega-config.

## Practical notes

- Start with one indicator at a time.
- Keep the entry-candle rule the same unless you are deliberately testing a different entry rule.
- If multiple parameter sets have the same hit rate, compare them on sample size and on the other sheets before choosing.
- If an indicator only works well in one direction, record that before combining it with others.
