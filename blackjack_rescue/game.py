"""Round engine for Blackjack Rescue."""

from __future__ import annotations

import random

from .basic_strategy import Action, ActionAvailability, BasicStrategy
from .cards import Rank
from .config import GameConfig, ShoeDepletionPolicy
from .hand import FinalOutcome, Hand, hand_value, is_blackjack, is_bust, is_soft, settle_hand
from .rescue_strategy import (
    RescuePolicy,
    exact_replacement_analysis,
    make_context_from_cards,
)
from .shoe import Shoe, ShoeDepleted
from .statistics import RescueEvent, SimulationMetrics


def dealer_play(
    dealer_cards: list[int],
    shoe: Shoe,
    config: GameConfig,
    metrics: SimulationMetrics | None = None,
) -> list[int]:
    """Play dealer hand according to configured S17/H17 rule."""

    while True:
        total = hand_value(dealer_cards)
        soft = is_soft(dealer_cards)
        if total > 21:
            return dealer_cards
        if total > 17:
            return dealer_cards
        if total == 17 and (not soft or config.dealer_soft17.value == "S17"):
            return dealer_cards
        dealer_cards.append(shoe.deal())
        if metrics is not None:
            metrics.dealer_cards_drawn += 1


class BlackjackRescueGame:
    """Single-player, finite-shoe blackjack game simulator."""

    def __init__(
        self,
        config: GameConfig,
        rng: random.Random,
        rescue_policy: RescuePolicy,
        metrics: SimulationMetrics,
    ) -> None:
        self.config = config
        self.rng = rng
        self.rescue_policy = rescue_policy
        self.metrics = metrics
        self.shoe = Shoe(config, rng)
        self.basic_strategy = BasicStrategy(config)

    def play_one_initial_hand(self) -> bool:
        """Play one initial wager.

        Returns false when a round is aborted due to mid-round shoe depletion.
        Under the default documented policy the shoe is then freshly shuffled and
        the hand is retried by the simulation loop without counting it.
        """

        if self.shoe.needs_shuffle():
            self.shoe.shuffle_new_shoe()
        try:
            return self._play_one_initial_hand()
        except ShoeDepleted:
            self.metrics.aborted_rounds += 1
            if self.config.shoe_depletion_policy == ShoeDepletionPolicy.RAISE:
                raise
            self.shoe.shuffle_new_shoe()
            return False

    def _play_one_initial_hand(self) -> bool:
        cfg = self.config
        self.metrics.original_wagers += cfg.original_wager

        player = Hand([self.shoe.deal()], wager=cfg.original_wager)
        dealer_cards = [self.shoe.deal()]
        player.add_card(self.shoe.deal())
        dealer_cards.append(self.shoe.deal())
        dealer_upcard = dealer_cards[0]

        if player.blackjack():
            self.metrics.blackjack_count += 1

        dealer_blackjack = is_blackjack(dealer_cards, original_unsplit=True)
        if cfg.dealer_peeks and dealer_upcard in {Rank.ACE, Rank.TEN} and dealer_blackjack:
            self.metrics.dealer_blackjack_count += 1
            result, outcome = settle_hand(
                player, dealer_cards, cfg, dealer_blackjack=dealer_blackjack
            )
            self._finish_rescue_events([player], outcome, result)
            self._discard_round([player], dealer_cards)
            self.metrics.add_round_result(result)
            return True

        if player.blackjack():
            result, outcome = settle_hand(player, dealer_cards, cfg)
            self._finish_rescue_events([player], outcome, result)
            self._discard_round([player], dealer_cards)
            self.metrics.add_round_result(result)
            return True

        hands = [player]
        self._play_player_hands(hands, dealer_upcard)

        any_live = any(
            not hand.bust() and not hand.surrendered for hand in hands
        )
        if any_live:
            dealer_play(dealer_cards, self.shoe, cfg, self.metrics)

        round_result = 0.0
        for hand in hands:
            result, outcome = settle_hand(hand, dealer_cards, cfg)
            round_result += result
            self._finish_rescue_events([hand], outcome, result)

        self._discard_round(hands, dealer_cards)
        self.metrics.add_round_result(round_result)
        return True

    def _play_player_hands(self, hands: list[Hand], dealer_upcard: int) -> None:
        idx = 0
        while idx < len(hands):
            hand = hands[idx]
            if hand.split_aces and self.config.split_aces_receive_one_card:
                idx += 1
                continue
            self._play_single_hand(hands, idx, dealer_upcard)
            # A split replaces the current hand and inserts another hand.  The
            # current index should be replayed in that case.
            if idx < len(hands) and hands[idx] is hand:
                idx += 1

    def _play_single_hand(self, hands: list[Hand], idx: int, dealer_upcard: int) -> None:
        hand = hands[idx]
        while True:
            if hand.bust() or hand.surrendered:
                return
            availability = self._availability(hand, hands)
            action = self.basic_strategy.choose(hand, dealer_upcard, availability)
            if action == Action.STAND:
                return
            if action == Action.SURRENDER and availability.can_surrender:
                hand.surrendered = True
                return
            if action == Action.SPLIT and availability.can_split:
                self._split_hand(hands, idx)
                return
            if action == Action.DOUBLE and availability.can_double:
                hand.doubled = True
                self.metrics.double_wagers += hand.wager
                hand.wager *= 2
                self._hit_hand(hand, dealer_upcard)
                return
            self._hit_hand(hand, dealer_upcard)
            if hand.bust():
                return
            if hand.rescue_used and not self.config.can_hit_after_successful_rescue:
                return

    def _availability(self, hand: Hand, hands: list[Hand]) -> ActionAvailability:
        cfg = self.config
        two_cards = len(hand.cards) == 2
        can_double = (
            two_cards
            and cfg.double_allowed_any_two
            and (not hand.is_split or cfg.double_after_split)
            and (hand.rescue_used == 0 or cfg.can_double_after_successful_rescue)
        )
        can_split = (
            two_cards
            and hand.pair()
            and len(hands) < cfg.max_split_hands
        )
        if can_split and hand.cards[0] == Rank.ACE and hand.is_split and not cfg.resplit_aces:
            can_split = False
        can_surrender = cfg.surrender_enabled and two_cards and not hand.is_split
        return ActionAvailability(can_double, can_split, can_surrender)

    def _split_hand(self, hands: list[Hand], idx: int) -> None:
        original = hands[idx]
        first_card, second_card = original.cards
        split_aces = first_card == Rank.ACE
        h1 = Hand(
            [first_card, self.shoe.deal()],
            wager=original.wager,
            is_split=True,
            split_aces=split_aces,
            original_unsplit=False,
        )
        h2 = Hand(
            [second_card, self.shoe.deal()],
            wager=original.wager,
            is_split=True,
            split_aces=split_aces,
            original_unsplit=False,
        )
        hands[idx] = h1
        hands.insert(idx + 1, h2)
        self.metrics.split_wagers += self.config.original_wager

    def _hit_hand(self, hand: Hand, dealer_upcard: int) -> None:
        pre_cards = list(hand.cards)
        can_double_before_hit = self._availability(hand, [hand]).can_double
        card = self.shoe.deal()
        hand.add_card(card)
        if not hand.bust():
            return
        self.metrics.player_bust_before_rescue += 1

        context = make_context_from_cards(
            pre_cards,
            card,
            dealer_upcard,
            from_split=hand.is_split,
            doubled=hand.doubled,
            can_double=can_double_before_hit,
            rescue_used=hand.rescue_used,
        )
        if not self._rescue_legal(hand):
            return

        analysis = exact_replacement_analysis(context.pre_hit_cards, self.shoe.remaining_counts())
        accepted = self.rescue_policy.accept(context, self.shoe.remaining_counts())
        if not accepted:
            event = RescueEvent(
                context=context,
                accepted=False,
                final_outcome=FinalOutcome.LOSS,
                final_result=-hand.wager - hand.rescue_fees,
                decline_result=-hand.wager - hand.rescue_fees,
                exact_survival_probability=analysis.survival_probability,
            )
            hand.rescue_events.append(event)
            return

        bust_card = hand.remove_last_card()
        self.shoe.discard_card(bust_card)
        fee = self.config.rescue_fee_for_wager(hand.wager)
        hand.rescue_fees += fee
        hand.rescue_used += 1
        self.metrics.rescue_wagers += fee

        replacement = self.shoe.deal()
        hand.add_card(replacement)
        immediate_survived = not hand.bust()
        event = RescueEvent(
            context=context,
            accepted=True,
            replacement_card=replacement,
            immediate_survived=immediate_survived,
            decline_result=-hand.wager - (hand.rescue_fees - fee),
            exact_survival_probability=analysis.survival_probability,
        )
        hand.rescue_events.append(event)

    def _rescue_legal(self, hand: Hand) -> bool:
        cfg = self.config
        if hand.rescue_used >= cfg.max_rescues_per_hand:
            return False
        if hand.is_split and not cfg.rescue_allowed_on_split_hands:
            return False
        if hand.doubled and not cfg.rescue_allowed_after_double:
            return False
        if hand.split_aces and not cfg.rescue_on_split_aces:
            return False
        return True

    def _finish_rescue_events(
        self, hands: list[Hand], outcome: FinalOutcome, result: float
    ) -> None:
        for hand in hands:
            for event in hand.rescue_events:
                if event.final_result is None:
                    event.final_result = result
                    event.final_outcome = outcome
                self.metrics.record_rescue_event(event)

    def _discard_round(self, hands: list[Hand], dealer_cards: list[int]) -> None:
        for hand in hands:
            self.shoe.discard_cards(hand.cards)
        self.shoe.discard_cards(dealer_cards)
