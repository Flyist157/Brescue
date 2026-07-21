"""Rescue decision policies and state descriptions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import sqrt
from typing import Mapping, Protocol

from .cards import RANKS, card_value, cards_label, rank_label
from .hand import hand_value, is_bust, is_soft


@dataclass(frozen=True, slots=True)
class RescueContext:
    pre_hit_cards: tuple[int, ...]
    pre_hit_total: int
    pre_hit_soft: bool
    bust_card: int
    busted_total: int
    dealer_upcard: int
    from_split: bool
    doubled: bool
    can_double: bool
    rescue_used: int

    @property
    def dealer_label(self) -> str:
        return rank_label(self.dealer_upcard)

    @property
    def bust_card_label(self) -> str:
        return rank_label(self.bust_card)

    def full_key(self) -> tuple[object, ...]:
        return (
            cards_label(self.pre_hit_cards),
            self.pre_hit_total,
            self.pre_hit_soft,
            self.bust_card,
            self.busted_total,
            self.dealer_upcard,
            self.from_split,
            self.doubled,
            self.can_double,
        )

    def busted_total_key(self) -> tuple[int]:
        return (self.busted_total,)

    def busted_total_dealer_key(self) -> tuple[int, int]:
        return (self.busted_total, self.dealer_upcard)

    def prehit_dealer_key(self) -> tuple[int, bool, int]:
        return (self.pre_hit_total, self.pre_hit_soft, self.dealer_upcard)


@dataclass(slots=True)
class ReplacementAnalysis:
    saving_ranks: tuple[int, ...]
    busting_ranks: tuple[int, ...]
    survival_probability: float
    cards_remaining: int


def exact_replacement_analysis(
    pre_hit_cards: tuple[int, ...], remaining_counts: Counter[int]
) -> ReplacementAnalysis:
    """Compute exact immediate survival probability from current shoe ranks."""

    saving: list[int] = []
    busting: list[int] = []
    total_remaining = sum(remaining_counts.values())
    saving_cards = 0
    for rank in RANKS:
        count = remaining_counts.get(int(rank), 0)
        if count <= 0:
            continue
        candidate = list(pre_hit_cards) + [int(rank)]
        if is_bust(candidate):
            busting.append(int(rank))
        else:
            saving.append(int(rank))
            saving_cards += count
    probability = saving_cards / total_remaining if total_remaining else 0.0
    return ReplacementAnalysis(tuple(saving), tuple(busting), probability, total_remaining)


class RescuePolicy(Protocol):
    name: str

    def accept(self, context: RescueContext, remaining_counts: Counter[int] | None = None) -> bool:
        ...


class NeverRescue:
    name = "never"

    def accept(self, context: RescueContext, remaining_counts: Counter[int] | None = None) -> bool:
        return False


class AlwaysRescue:
    name = "always"

    def accept(self, context: RescueContext, remaining_counts: Counter[int] | None = None) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class BustedTotalPolicy:
    """Rescue on an explicit set or on 22 through a cutoff."""

    cutoff: int | None = None
    totals: frozenset[int] | None = None

    @property
    def name(self) -> str:
        if self.totals is not None:
            return "busted_total_" + "_".join(str(v) for v in sorted(self.totals))
        return f"busted_total_22_to_{self.cutoff}"

    def accept(self, context: RescueContext, remaining_counts: Counter[int] | None = None) -> bool:
        if self.totals is not None:
            return context.busted_total in self.totals
        if self.cutoff is None:
            return False
        return 22 <= context.busted_total <= self.cutoff


@dataclass(frozen=True, slots=True)
class TablePolicy:
    """Generic positive/negative table-driven Rescue policy."""

    name: str
    table: Mapping[tuple[object, ...], bool]
    key_type: str

    def _key(self, context: RescueContext) -> tuple[object, ...]:
        if self.key_type == "busted_total_dealer":
            return context.busted_total_dealer_key()
        if self.key_type == "prehit_dealer":
            return context.prehit_dealer_key()
        if self.key_type == "full":
            return context.full_key()
        if self.key_type == "busted_total":
            return context.busted_total_key()
        raise ValueError(f"unknown key_type {self.key_type}")

    def accept(self, context: RescueContext, remaining_counts: Counter[int] | None = None) -> bool:
        return bool(self.table.get(self._key(context), False))


@dataclass(frozen=True, slots=True)
class ImmediateSurvivalPolicy:
    """Optional composition-dependent mode based on exact one-step survival."""

    threshold: float
    name: str = "composition_survival"

    def accept(self, context: RescueContext, remaining_counts: Counter[int] | None = None) -> bool:
        if remaining_counts is None:
            return False
        analysis = exact_replacement_analysis(context.pre_hit_cards, remaining_counts)
        return analysis.survival_probability >= self.threshold


@dataclass(slots=True)
class EmpiricalEstimate:
    samples: int
    mean_incremental_ev: float
    standard_error: float
    ci95_low: float
    ci95_high: float
    recommendation: str


def estimate_from_samples(samples: list[float], min_samples: int = 30) -> EmpiricalEstimate:
    n = len(samples)
    if n == 0:
        return EmpiricalEstimate(0, 0.0, 0.0, 0.0, 0.0, "uncertain")
    mean = sum(samples) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in samples) / (n - 1)
        se = sqrt(variance / n)
    else:
        se = 0.0
    low = mean - 1.96 * se
    high = mean + 1.96 * se
    if n < min_samples:
        rec = "uncertain"
    elif low > 0:
        rec = "rescue"
    elif high < 0:
        rec = "decline"
    else:
        rec = "uncertain"
    return EmpiricalEstimate(n, mean, se, low, high, rec)


def make_context_from_cards(
    pre_hit_cards: list[int],
    bust_card: int,
    dealer_upcard: int,
    *,
    from_split: bool,
    doubled: bool,
    can_double: bool,
    rescue_used: int,
) -> RescueContext:
    busted_cards = list(pre_hit_cards) + [int(bust_card)]
    return RescueContext(
        pre_hit_cards=tuple(int(card) for card in pre_hit_cards),
        pre_hit_total=hand_value(pre_hit_cards),
        pre_hit_soft=is_soft(pre_hit_cards),
        bust_card=int(bust_card),
        busted_total=hand_value(busted_cards),
        dealer_upcard=int(dealer_upcard),
        from_split=from_split,
        doubled=doubled,
        can_double=can_double,
        rescue_used=rescue_used,
    )
