"""Compact card representation.

Ranks are stored as small integers.  Ten, Jack, Queen, and King are consolidated
as ``Rank.TEN`` while preserving the correct count of 16 ten-value cards per
deck.
"""

from __future__ import annotations

from collections import Counter
from enum import IntEnum
from typing import Iterable


class Rank(IntEnum):
    ACE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10


RANKS: tuple[Rank, ...] = (
    Rank.ACE,
    Rank.TWO,
    Rank.THREE,
    Rank.FOUR,
    Rank.FIVE,
    Rank.SIX,
    Rank.SEVEN,
    Rank.EIGHT,
    Rank.NINE,
    Rank.TEN,
)

RANK_LABELS: dict[int, str] = {
    Rank.ACE: "A",
    Rank.TWO: "2",
    Rank.THREE: "3",
    Rank.FOUR: "4",
    Rank.FIVE: "5",
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "10",
}

LABEL_TO_RANK: dict[str, Rank] = {v: Rank(k) for k, v in RANK_LABELS.items()}


def card_value(card: int) -> int:
    """Return blackjack point value for a single card with ace counted as one."""

    return 1 if card == Rank.ACE else min(int(card), 10)


def dealer_upcard_value(card: int) -> int:
    """Return strategy-table dealer upcard value, using 11 for ace."""

    return 11 if card == Rank.ACE else min(int(card), 10)


def rank_label(card: int) -> str:
    return RANK_LABELS[int(card)]


def cards_label(cards: Iterable[int]) -> str:
    return "-".join(rank_label(card) for card in cards)


def one_deck() -> list[int]:
    """Return one 52-card deck with consolidated ten-value cards."""

    cards: list[int] = []
    cards.extend([Rank.ACE] * 4)
    for rank in range(2, 10):
        cards.extend([Rank(rank)] * 4)
    cards.extend([Rank.TEN] * 16)
    return [int(card) for card in cards]


def build_shoe(decks: int) -> list[int]:
    cards: list[int] = []
    deck = one_deck()
    for _ in range(decks):
        cards.extend(deck)
    return cards


def rank_counts(cards: Iterable[int]) -> Counter[int]:
    return Counter(int(card) for card in cards)
