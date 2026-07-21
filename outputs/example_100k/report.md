# Blackjack Rescue Simulation Report

## Assumptions and configurable ambiguous rules

- Rescue wager default: nonrefundable fee paid to replace the bust card.
- A rescued win pays only the original hand wager; default net is +0.5 units.
- A rescued push loses the Rescue fee; default net is -0.5 units.
- Rescue is allowed on split hands but not after doubled hands by default.
- The bust-causing card is exposed, removed from the hand, and discarded.
- The replacement is the next physical card in the finite shoe.
- The player may hit again after a successful Rescue by default.
- Rescue does not apply to dealer hands.
- If an active shoe cannot complete a round, the default procedure aborts that round, reshuffles, and retries without counting the aborted hand.

## Configuration

```json
{
  "blackjack_payout": 1.5,
  "can_double_after_successful_rescue": false,
  "can_hit_after_successful_rescue": true,
  "dealer_peeks": true,
  "dealer_soft17": "S17",
  "decks": 6,
  "discarded_bust_card_exposed": true,
  "double_after_split": true,
  "double_allowed_any_two": true,
  "insurance_enabled": false,
  "max_rescues_per_hand": 1,
  "max_split_hands": 4,
  "natural_blackjack_original_only": true,
  "original_wager": 1.0,
  "penetration": 0.75,
  "rescue_allowed_after_double": false,
  "rescue_allowed_on_split_hands": true,
  "rescue_applies_to_dealer": false,
  "rescue_cost": 0.5,
  "rescue_fee_base": "original",
  "rescue_on_split_aces": false,
  "rescue_settlement_model": "nonrefundable_fee",
  "rescued_win_pays_original_only": true,
  "resplit_aces": false,
  "shoe_depletion_policy": "abort_round_and_reshuffle",
  "split_aces_receive_one_card": true,
  "surrender_enabled": false
}
```

## Baseline validation

Never Rescue house edge was 0.007395 over 100000 hands, within a broad plausible range for six-deck S17 DAS 3:2 blackjack.

## Strategy comparison

| Strategy | Hands | Player net | House edge vs initial | House edge vs action | Rescue attempts | Avg inc EV |
|---|---:|---:|---:|---:|---:|---:|
| never | 100000 | -739.5000 | 0.007395 | 0.006502 | 0 | 0.000000 |
| always | 100000 | 654.0000 | -0.006540 | -0.005370 | 16029 | 0.059299 |
| busted_total_22_to_22 | 100000 | -234.5000 | 0.002345 | 0.002019 | 4656 | 0.137027 |
| busted_total_22_to_23 | 100000 | 338.0000 | -0.003380 | -0.002864 | 8260 | 0.101695 |
| busted_total_22_to_24 | 100000 | 549.5000 | -0.005495 | -0.004598 | 11393 | 0.083077 |
| best_busted_total_threshold_busted_total_22_to_25 | 100000 | 677.5000 | -0.006775 | -0.005606 | 14048 | 0.077022 |
| busted_total_22_to_26 | 100000 | 654.0000 | -0.006540 | -0.005370 | 16029 | 0.059299 |
| busted_total_22_to_27 | 100000 | 654.0000 | -0.006540 | -0.005370 | 16029 | 0.059299 |
| busted_total_22_to_28 | 100000 | 654.0000 | -0.006540 | -0.005370 | 16029 | 0.059299 |
| busted_total_22_to_29 | 100000 | 654.0000 | -0.006540 | -0.005370 | 16029 | 0.059299 |
| busted_total_22_to_30 | 100000 | 654.0000 | -0.006540 | -0.005370 | 16029 | 0.059299 |
| learned_busted_total_dealer | 100000 | 628.5000 | -0.006285 | -0.005255 | 11973 | 0.088324 |
| empirical_full_visible | 100000 | 554.0000 | -0.005540 | -0.004781 | 4322 | 0.130032 |

## Mathematical and procedural issues discovered

- Immediate replacement survival probability is not equivalent to full Rescue EV; surviving hands can later lose or push.
- Rescue changes card consumption, so common random seeds provide reproducibility but not identical downstream shoes after divergent decisions.
- Low-sample full-visible states require independent validation and should be marked uncertain.
