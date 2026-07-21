"""Rule-appropriate basic strategy for six-deck S17 DAS blackjack.

The default table is the standard multi-deck, dealer-stands-soft-17,
double-after-split strategy.  The engine returns a preferred action and then
applies availability fallbacks locally, so alternate tables can be added later
without changing game flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .cards import Rank, dealer_upcard_value
from .config import GameConfig
from .hand import Hand


class Action(str, Enum):
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"


@dataclass(frozen=True, slots=True)
class ActionAvailability:
    can_double: bool
    can_split: bool
    can_surrender: bool


def _hard_total_action(total: int, dealer: int, surrender: bool) -> Action:
    if surrender and total == 16 and dealer in {9, 10, 11}:
        return Action.SURRENDER
    if surrender and total == 15 and dealer == 10:
        return Action.SURRENDER
    if total >= 17:
        return Action.STAND
    if 13 <= total <= 16:
        return Action.STAND if 2 <= dealer <= 6 else Action.HIT
    if total == 12:
        return Action.STAND if 4 <= dealer <= 6 else Action.HIT
    if total == 11:
        return Action.DOUBLE
    if total == 10:
        return Action.DOUBLE if 2 <= dealer <= 9 else Action.HIT
    if total == 9:
        return Action.DOUBLE if 3 <= dealer <= 6 else Action.HIT
    return Action.HIT


def _soft_total_action(total: int, dealer: int) -> Action:
    if total >= 20:
        return Action.STAND
    if total == 19:
        return Action.DOUBLE if dealer == 6 else Action.STAND
    if total == 18:
        if 2 <= dealer <= 6:
            return Action.DOUBLE
        return Action.STAND if dealer in {7, 8} else Action.HIT
    if total == 17:
        return Action.DOUBLE if 3 <= dealer <= 6 else Action.HIT
    if total in {15, 16}:
        return Action.DOUBLE if 4 <= dealer <= 6 else Action.HIT
    if total in {13, 14}:
        return Action.DOUBLE if 5 <= dealer <= 6 else Action.HIT
    return Action.HIT


def _pair_action(rank: int, dealer: int, das: bool, surrender: bool) -> Action:
    if rank == Rank.ACE:
        return Action.SPLIT
    if rank == Rank.TEN:
        return Action.STAND
    if rank == Rank.NINE:
        return Action.SPLIT if dealer in {2, 3, 4, 5, 6, 8, 9} else Action.STAND
    if rank == Rank.EIGHT:
        if surrender and dealer == 11:
            return Action.SURRENDER
        return Action.SPLIT
    if rank == Rank.SEVEN:
        return Action.SPLIT if 2 <= dealer <= 7 else Action.HIT
    if rank == Rank.SIX:
        return Action.SPLIT if 2 <= dealer <= 6 else Action.HIT
    if rank == Rank.FIVE:
        return Action.DOUBLE if 2 <= dealer <= 9 else Action.HIT
    if rank == Rank.FOUR:
        return Action.SPLIT if das and dealer in {5, 6} else Action.HIT
    if rank in {Rank.TWO, Rank.THREE}:
        if das:
            return Action.SPLIT if 2 <= dealer <= 7 else Action.HIT
        return Action.SPLIT if 4 <= dealer <= 7 else Action.HIT
    return Action.HIT


class BasicStrategy:
    """Default basic-strategy engine."""

    def __init__(self, config: GameConfig) -> None:
        self.config = config

    def choose(self, hand: Hand, dealer_upcard: int, availability: ActionAvailability) -> Action:
        dealer = dealer_upcard_value(dealer_upcard)
        preferred = self.preferred_action(hand, dealer, availability)
        return self.apply_fallback(preferred, hand, dealer, availability)

    def preferred_action(
        self, hand: Hand, dealer: int, availability: ActionAvailability
    ) -> Action:
        if hand.pair() and availability.can_split:
            return _pair_action(
                hand.cards[0],
                dealer,
                self.config.double_after_split,
                self.config.surrender_enabled and availability.can_surrender,
            )
        if hand.soft():
            return _soft_total_action(hand.value(), dealer)
        return _hard_total_action(
            hand.value(),
            dealer,
            self.config.surrender_enabled and availability.can_surrender,
        )

    def apply_fallback(
        self,
        action: Action,
        hand: Hand,
        dealer: int,
        availability: ActionAvailability,
    ) -> Action:
        if action == Action.SURRENDER and not availability.can_surrender:
            action = Action.HIT if hand.value() < 17 else Action.STAND
        if action == Action.SPLIT and not availability.can_split:
            # Re-evaluate the pair as an ordinary hard/soft hand.
            if hand.soft():
                action = _soft_total_action(hand.value(), dealer)
            else:
                action = _hard_total_action(
                    hand.value(),
                    dealer,
                    self.config.surrender_enabled and availability.can_surrender,
                )
        if action == Action.DOUBLE and not availability.can_double:
            # Correct multi-deck fallback: soft doubles and hard 9/10/11 use hit
            # except soft 19 vs 6, where the unavailable double stands.
            if hand.soft() and hand.value() == 19:
                action = Action.STAND
            elif hand.value() >= 12 and not hand.soft():
                action = _hard_total_action(hand.value(), dealer, False)
                if action == Action.DOUBLE:
                    action = Action.HIT
            else:
                action = Action.HIT
        return action
