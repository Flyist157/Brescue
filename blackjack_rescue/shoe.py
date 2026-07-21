"""Finite shoe with a real discard tray and sequential dealing."""

from __future__ import annotations

from collections import Counter
import random
from typing import Iterable

from .cards import build_shoe
from .config import GameConfig


class ShoeDepleted(RuntimeError):
    """Raised when an active round asks for a card that is not present."""


class Shoe:
    """A shuffled finite shoe.

    The shoe never reshuffles during an active round.  Callers check
    ``needs_shuffle`` between rounds and call ``shuffle_new_shoe`` then.
    """

    def __init__(
        self,
        config: GameConfig,
        rng: random.Random,
        cards: Iterable[int] | None = None,
        shuffle: bool = True,
    ) -> None:
        self.config = config
        self.rng = rng
        self.cards: list[int] = list(cards) if cards is not None else build_shoe(config.decks)
        if shuffle:
            self.rng.shuffle(self.cards)
        self.position = 0
        self.discard: list[int] = []

    @property
    def cards_dealt(self) -> int:
        return self.position

    @property
    def cards_remaining(self) -> int:
        return len(self.cards) - self.position

    def needs_shuffle(self) -> bool:
        return self.position >= self.config.cut_card_index

    def shuffle_new_shoe(self) -> None:
        self.cards = build_shoe(self.config.decks)
        self.rng.shuffle(self.cards)
        self.position = 0
        self.discard.clear()

    def deal(self) -> int:
        if self.position >= len(self.cards):
            raise ShoeDepleted("shoe cannot complete the active round")
        card = self.cards[self.position]
        self.position += 1
        return card

    def burn(self) -> int:
        card = self.deal()
        self.discard_card(card)
        return card

    def discard_card(self, card: int) -> None:
        self.discard.append(int(card))

    def discard_cards(self, cards: Iterable[int]) -> None:
        self.discard.extend(int(card) for card in cards)

    def remaining_cards(self) -> list[int]:
        return self.cards[self.position :]

    def remaining_counts(self) -> Counter[int]:
        return Counter(self.remaining_cards())
