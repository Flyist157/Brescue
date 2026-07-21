"""Hand evaluation and settlement helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .cards import Rank, card_value
from .config import GameConfig, RescueSettlementModel


class FinalOutcome(str, Enum):
    WIN = "win"
    LOSS = "loss"
    PUSH = "push"
    BLACKJACK = "blackjack"
    SURRENDER = "surrender"


def hand_value(cards: Iterable[int]) -> int:
    """Best blackjack total, counting aces as 11 where possible."""

    card_list = list(cards)
    total = sum(card_value(card) for card in card_list)
    aces = sum(1 for card in card_list if int(card) == Rank.ACE)
    while aces and total + 10 <= 21:
        total += 10
        aces -= 1
    return total


def is_soft(cards: Iterable[int]) -> bool:
    """True when at least one ace is currently counted as 11."""

    card_list = list(cards)
    total = sum(card_value(card) for card in card_list)
    aces = sum(1 for card in card_list if int(card) == Rank.ACE)
    return aces > 0 and total + 10 <= 21


def is_bust(cards: Iterable[int]) -> bool:
    return hand_value(cards) > 21


def is_blackjack(cards: Iterable[int], *, original_unsplit: bool = True) -> bool:
    card_list = list(cards)
    return original_unsplit and len(card_list) == 2 and hand_value(card_list) == 21


def is_pair(cards: Iterable[int]) -> bool:
    card_list = list(cards)
    return len(card_list) == 2 and int(card_list[0]) == int(card_list[1])


@dataclass(slots=True)
class Hand:
    cards: list[int]
    wager: float = 1.0
    is_split: bool = False
    split_aces: bool = False
    original_unsplit: bool = True
    doubled: bool = False
    surrendered: bool = False
    rescue_fees: float = 0.0
    rescue_used: int = 0
    rescue_events: list[object] = field(default_factory=list)

    def value(self) -> int:
        return hand_value(self.cards)

    def soft(self) -> bool:
        return is_soft(self.cards)

    def bust(self) -> bool:
        return is_bust(self.cards)

    def blackjack(self) -> bool:
        return is_blackjack(self.cards, original_unsplit=self.original_unsplit)

    def pair(self) -> bool:
        return is_pair(self.cards)

    def add_card(self, card: int) -> None:
        self.cards.append(int(card))

    def remove_last_card(self) -> int:
        if not self.cards:
            raise ValueError("cannot remove from empty hand")
        return self.cards.pop()


def settle_hand(
    hand: Hand,
    dealer_cards: list[int],
    config: GameConfig,
    *,
    dealer_blackjack: bool = False,
) -> tuple[float, FinalOutcome]:
    """Settle one player hand from the player's point of view."""

    if hand.surrendered:
        return -0.5 * config.original_wager - hand.rescue_fees, FinalOutcome.SURRENDER

    if hand.bust():
        return -hand.wager - hand.rescue_fees, FinalOutcome.LOSS

    if hand.blackjack():
        if dealer_blackjack:
            return -hand.rescue_fees, FinalOutcome.PUSH
        return (
            hand.wager * config.blackjack_payout - hand.rescue_fees,
            FinalOutcome.BLACKJACK,
        )

    if dealer_blackjack:
        return -hand.wager - hand.rescue_fees, FinalOutcome.LOSS

    dealer_total = hand_value(dealer_cards)
    player_total = hand.value()
    if dealer_total > 21 or player_total > dealer_total:
        if config.rescue_settlement_model == RescueSettlementModel.LIVE_SIDE_WAGER:
            return hand.wager + hand.rescue_fees, FinalOutcome.WIN
        return hand.wager - hand.rescue_fees, FinalOutcome.WIN
    if player_total < dealer_total:
        if config.rescue_settlement_model == RescueSettlementModel.LIVE_SIDE_WAGER:
            return -hand.wager - hand.rescue_fees, FinalOutcome.LOSS
        return -hand.wager - hand.rescue_fees, FinalOutcome.LOSS
    if config.rescue_settlement_model == RescueSettlementModel.LIVE_SIDE_WAGER:
        return 0.0, FinalOutcome.PUSH
    return -hand.rescue_fees, FinalOutcome.PUSH
