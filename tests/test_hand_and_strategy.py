import unittest

from blackjack_rescue.basic_strategy import Action, ActionAvailability, BasicStrategy
from blackjack_rescue.cards import Rank
from blackjack_rescue.config import GameConfig
from blackjack_rescue.hand import (
    FinalOutcome,
    Hand,
    hand_value,
    is_blackjack,
    is_pair,
    is_soft,
    settle_hand,
)


class HandEvaluationTests(unittest.TestCase):
    def test_multiple_aces(self) -> None:
        self.assertEqual(hand_value([Rank.ACE, Rank.ACE, Rank.NINE]), 21)
        self.assertEqual(hand_value([Rank.ACE, Rank.ACE, Rank.NINE, Rank.TEN]), 21)
        self.assertEqual(hand_value([Rank.ACE, Rank.ACE, Rank.NINE, Rank.TEN, Rank.TEN]), 31)

    def test_soft_detection(self) -> None:
        self.assertTrue(is_soft([Rank.ACE, Rank.SIX]))
        self.assertFalse(is_soft([Rank.ACE, Rank.SIX, Rank.TEN]))

    def test_blackjack_recognition_original_only(self) -> None:
        self.assertTrue(is_blackjack([Rank.ACE, Rank.TEN], original_unsplit=True))
        self.assertFalse(is_blackjack([Rank.ACE, Rank.TEN], original_unsplit=False))
        self.assertFalse(is_blackjack([Rank.ACE, Rank.FIVE, Rank.FIVE], original_unsplit=True))

    def test_pair_recognition(self) -> None:
        self.assertTrue(is_pair([Rank.EIGHT, Rank.EIGHT]))
        self.assertFalse(is_pair([Rank.EIGHT, Rank.THREE]))


class SettlementTests(unittest.TestCase):
    def test_blackjack_payout(self) -> None:
        cfg = GameConfig()
        result, outcome = settle_hand(
            Hand([Rank.ACE, Rank.TEN]), [Rank.TEN, Rank.SEVEN], cfg
        )
        self.assertEqual(outcome, FinalOutcome.BLACKJACK)
        self.assertEqual(result, 1.5)

    def test_push_settlement(self) -> None:
        cfg = GameConfig()
        result, outcome = settle_hand(
            Hand([Rank.TEN, Rank.EIGHT]), [Rank.TEN, Rank.EIGHT], cfg
        )
        self.assertEqual(outcome, FinalOutcome.PUSH)
        self.assertEqual(result, 0.0)

    def test_double_settlement(self) -> None:
        cfg = GameConfig()
        hand = Hand([Rank.TEN, Rank.NINE], wager=2.0, doubled=True)
        result, outcome = settle_hand(hand, [Rank.TEN, Rank.EIGHT], cfg)
        self.assertEqual(outcome, FinalOutcome.WIN)
        self.assertEqual(result, 2.0)


class BasicStrategyTests(unittest.TestCase):
    def test_double_falls_back_to_hit(self) -> None:
        strategy = BasicStrategy(GameConfig())
        action = strategy.choose(
            Hand([Rank.FIVE, Rank.SIX]),
            Rank.SIX,
            ActionAvailability(can_double=False, can_split=False, can_surrender=False),
        )
        self.assertEqual(action, Action.HIT)

    def test_soft_19_double_falls_back_to_stand(self) -> None:
        strategy = BasicStrategy(GameConfig())
        action = strategy.choose(
            Hand([Rank.ACE, Rank.EIGHT]),
            Rank.SIX,
            ActionAvailability(can_double=False, can_split=False, can_surrender=False),
        )
        self.assertEqual(action, Action.STAND)

    def test_split_unavailable_fallback(self) -> None:
        strategy = BasicStrategy(GameConfig())
        action = strategy.choose(
            Hand([Rank.EIGHT, Rank.EIGHT]),
            Rank.TEN,
            ActionAvailability(can_double=False, can_split=False, can_surrender=False),
        )
        self.assertEqual(action, Action.HIT)


if __name__ == "__main__":
    unittest.main()
