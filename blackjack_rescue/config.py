"""Configuration for Blackjack Rescue.

The dataclass below intentionally documents ambiguous commercial rules in one
place.  Defaults implement the rule set requested for six-deck S17 DAS blackjack
with a nonrefundable Rescue fee.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any


class DealerSoft17Rule(str, Enum):
    """Dealer behavior on soft 17."""

    STAND = "S17"
    HIT = "H17"


class RescueSettlementModel(str, Enum):
    """Commercial treatment of the Rescue wager.

    NONREFUNDABLE_FEE:
        The Rescue wager buys replacement of the bust card.  It is never paid
        back.  If the original wager later wins, loses, or pushes, the fee
        remains lost.  This is the default model.

    LIVE_SIDE_WAGER:
        The Rescue amount is treated as an added live wager that follows the
        original hand result after a successful replacement.  Immediate
        replacement bust loses both original action and the Rescue amount.
    """

    NONREFUNDABLE_FEE = "nonrefundable_fee"
    LIVE_SIDE_WAGER = "live_side_wager"


class ShoeDepletionPolicy(str, Enum):
    """Procedure when an active round cannot be completed from the shoe."""

    ABORT_ROUND_AND_RESHUFFLE = "abort_round_and_reshuffle"
    RAISE = "raise"


@dataclass(slots=True)
class GameConfig:
    """All major blackjack and Rescue rules.

    Ambiguous Rescue modeling rules are represented explicitly:

    * ``rescue_settlement_model`` controls whether the Rescue wager is a
      nonrefundable fee (default) or an additional live wager.
    * ``rescued_win_pays_original_only`` is true for the default fee model: a
      rescued ordinary win nets +1 original unit minus the Rescue fee.
    * ``rescue_allowed_after_double`` defaults false.  If enabled, a declined
      doubled bust loses the doubled original action, and the Rescue fee is
      based on ``rescue_fee_base``.
    * ``rescue_allowed_on_split_hands`` defaults true.
    * ``max_rescues_per_hand`` defaults to one.
    * ``can_hit_after_successful_rescue`` defaults true.
    * ``can_double_after_successful_rescue`` defaults false.
    * ``discarded_bust_card_exposed`` is tracked as true: the bust-causing card
      is removed from the hand and placed in the discard tray.
    * ``rescue_on_split_aces`` defaults false because split aces receive one
      card only under the default blackjack rules.
    * ``rescue_applies_to_dealer`` defaults false.
    * ``shoe_depletion_policy`` documents what happens if the shoe runs out
      between the discarded bust card and replacement or elsewhere mid-round.
    """

    decks: int = 6
    penetration: float = 0.75
    dealer_soft17: DealerSoft17Rule = DealerSoft17Rule.STAND
    dealer_peeks: bool = True
    blackjack_payout: float = 1.5
    double_allowed_any_two: bool = True
    double_after_split: bool = True
    max_split_hands: int = 4
    resplit_aces: bool = False
    split_aces_receive_one_card: bool = True
    surrender_enabled: bool = False
    insurance_enabled: bool = False
    natural_blackjack_original_only: bool = True
    original_wager: float = 1.0
    rescue_cost: float = 0.5
    rescue_settlement_model: RescueSettlementModel = (
        RescueSettlementModel.NONREFUNDABLE_FEE
    )
    rescued_win_pays_original_only: bool = True
    rescue_allowed_on_split_hands: bool = True
    rescue_allowed_after_double: bool = False
    rescue_fee_base: str = "original"  # "original" or "current_wager"
    max_rescues_per_hand: int = 1
    can_hit_after_successful_rescue: bool = True
    can_double_after_successful_rescue: bool = False
    discarded_bust_card_exposed: bool = True
    rescue_on_split_aces: bool = False
    rescue_applies_to_dealer: bool = False
    shoe_depletion_policy: ShoeDepletionPolicy = (
        ShoeDepletionPolicy.ABORT_ROUND_AND_RESHUFFLE
    )

    def __post_init__(self) -> None:
        if isinstance(self.dealer_soft17, str):
            self.dealer_soft17 = DealerSoft17Rule(self.dealer_soft17)
        if isinstance(self.rescue_settlement_model, str):
            self.rescue_settlement_model = RescueSettlementModel(
                self.rescue_settlement_model
            )
        if isinstance(self.shoe_depletion_policy, str):
            self.shoe_depletion_policy = ShoeDepletionPolicy(
                self.shoe_depletion_policy
            )
        if self.decks <= 0:
            raise ValueError("decks must be positive")
        if not 0 < self.penetration < 1:
            raise ValueError("penetration must be between 0 and 1")
        if self.blackjack_payout <= 0:
            raise ValueError("blackjack_payout must be positive")
        if self.original_wager <= 0:
            raise ValueError("original_wager must be positive")
        if self.rescue_cost < 0:
            raise ValueError("rescue_cost cannot be negative")
        if self.max_split_hands < 1:
            raise ValueError("max_split_hands must be at least one")
        if self.max_rescues_per_hand < 0:
            raise ValueError("max_rescues_per_hand cannot be negative")
        if self.rescue_fee_base not in {"original", "current_wager"}:
            raise ValueError("rescue_fee_base must be 'original' or 'current_wager'")

    @property
    def cards_per_shoe(self) -> int:
        return self.decks * 52

    @property
    def cut_card_index(self) -> int:
        return int(self.cards_per_shoe * self.penetration)

    def rescue_fee_for_wager(self, current_wager: float) -> float:
        if self.rescue_fee_base == "current_wager":
            return self.rescue_cost * (current_wager / self.original_wager)
        return self.rescue_cost

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Enum):
                data[key] = value.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameConfig":
        return cls(**data)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "GameConfig":
        with Path(path).open("r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def write_json(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
            fh.write("\n")
