# Blackjack Rescue

Finite-shoe Monte Carlo simulator for **Blackjack Rescue**, a proprietary
six-deck blackjack variant.  The simulator models a real shuffled shoe, actual
card removal, a discard tray, standard blackjack play under configurable rules,
and Rescue decisions made only after a player hit creates a busted hand.

## Default rules

Defaults are documented in `blackjack_rescue/config.py` and mirrored in
`config/default.json`.

- Six decks, 312 cards, consolidated 10-value rank with 16 ten-value cards per
  deck.
- Dealer stands on soft 17 and peeks for blackjack with ace or 10 upcard.
- Blackjack pays 3:2; natural blackjack applies only to the original unsplit
  two-card hand.
- Double on any initial two cards; double after split enabled.
- Split to four total hands; resplit aces disabled; split aces receive one card.
- No surrender and no insurance by default.
- Cut-card reshuffle at 75% penetration, only between rounds.
- Original wager is 1.0 unit.
- Rescue costs 0.5 units.
- Rescue is allowed on ordinary and split hands, not after doubled hands.
- One Rescue per hand by default.

## Rescue settlement assumption

The default commercial model treats the Rescue wager as a nonrefundable fee:

- The bust-causing card is discarded.
- The next physical card in the shoe replaces it.
- The 0.5-unit Rescue fee is never returned.
- The original wager resumes normal action after a successful replacement.
- Replacement bust: `-1.5` units.
- Rescued hand later loses: `-1.5` units.
- Rescued hand pushes: `-0.5` units.
- Rescued hand wins normally: `+0.5` units.
- A rescued 21 is not blackjack and pays as an ordinary win.

Alternative Rescue settlement is configurable with
`rescue_settlement_model = "live_side_wager"`.

## Installation

The simulator uses only the Python standard library by default.

```bash
python -m unittest
python simulation.py --hands 100000 --strategy all --seed 12345 --output-dir outputs/example_100k
```

Optional charts are written when `matplotlib` is installed:

```bash
python -m pip install '.[charts]'
```

## CLI

```bash
python simulation.py --hands 1000000 --strategy all --seed 12345
```

Important arguments:

- `--hands`: counted initial player hands.
- `--strategy`: `never`, `always`, `threshold-sweep`,
  `busted-total-dealer`, `empirical`, `composition`, or `all`.
- `--decks`: number of decks.
- `--penetration`: cut-card penetration, default `0.75`.
- `--h17`: dealer hits soft 17; default is S17.
- `--blackjack-payout`: default `1.5`.
- `--rescue-cost`: default `0.5`.
- `--rescue-settlement-model`: `nonrefundable_fee` or `live_side_wager`.
- `--rescue-on-splits` / `--no-rescue-on-splits`.
- `--rescue-after-doubles` / `--no-rescue-after-doubles`.
- `--max-rescues-per-hand`: default `1`.
- `--runs`: independent seeds to aggregate.
- `--workers`: multiprocessing workers for independent runs.
- `--output-dir`: output directory.

## Implemented Rescue policies

- **Never Rescue**: ordinary blackjack control case.
- **Always Rescue**: accepts every legal Rescue opportunity.
- **Busted-total threshold sweep**: evaluates rescue on 22, 22-23, ..., 22-30.
- **Busted total + dealer upcard**: table learned from Always-Rescue training
  data and evaluated on a different seed.
- **Pre-hit total + dealer upcard**: reported as a practical chart from training
  data.
- **Full visible state empirical policy**: uses player pre-hit cards, pre-hit
  total/softness, bust card, busted total, dealer upcard, split status, doubled
  status, and double availability.  Training and validation use different seeds.
- **Exact one-step composition analysis**: computes saving and busting ranks
  from current shoe composition; optional `composition` strategy uses an
  immediate-survival threshold.  This is intentionally separate from practical
  non-counting strategy.

## Output files

Each run writes:

- `config.json`: exact configuration used.
- `summary.json`: configuration plus strategy summaries.
- `report.md`: concise markdown report and baseline validation note.
- `rescue_states_<strategy>.csv`: detailed state-level Rescue results grouped by
  pre-hit hard/soft total, dealer upcard, bust card, busted total, replacement
  card, final outcome, split status, double status, and pre-hit cards.
- `practical_chart_busted_total_*.csv`
- `practical_chart_busted_total_dealer_*.csv`
- `practical_chart_prehit_dealer_*.csv`
- `practical_chart_full_*.csv`
- `threshold_sweep.csv`
- Optional `house_edge_by_strategy.png`.

## Baseline validation

Before using Rescue results, run the Never Rescue control and inspect the
reported house edge.  The report flags results outside a broad plausible band
for six-deck S17 DAS 3:2 blackjack after enough hands.  This is a smoke check,
not a proof of correctness; unit tests cover hand values, dealer play, splits,
settlement, Rescue replacement order, one-Rescue limits, and strategy fallbacks.

## Shoe depletion

The shoe reshuffles only between rounds after the cut card.  If an active round
unexpectedly cannot be completed, the default documented procedure aborts that
round, reshuffles, and retries without counting the aborted hand.  This avoids
introducing an in-round reshuffle that would break finite-shoe semantics.

## Mathematical/procedural cautions

- Immediate Rescue survival probability is not full Rescue EV.
- Rescue changes card consumption, so common random seeds are reproducible but
  downstream shoes diverge after different Rescue decisions.
- Full-visible empirical tables can be sparse; low-sample states are marked
  uncertain and should be validated independently.
