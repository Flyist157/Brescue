import random
import unittest

from blackjack_rescue.cards import Rank
from blackjack_rescue.config import DealerSoft17Rule, GameConfig
from blackjack_rescue.game import BlackjackRescueGame, dealer_play
from blackjack_rescue.rescue_strategy import AlwaysRescue
from blackjack_rescue.shoe import Shoe
from blackjack_rescue.statistics import SimulationMetrics


def run_fixed(cards: list[int], config: GameConfig | None = None) -> SimulationMetrics:
    cfg = config or GameConfig()
    metrics = SimulationMetrics(strategy_name="always")
    game = BlackjackRescueGame(cfg, random.Random(7), AlwaysRescue(), metrics)
    game.shoe = Shoe(cfg, random.Random(7), cards=cards, shuffle=False)
    counted = game.play_one_initial_hand()
    assert counted
    return metrics


class DealerPlayTests(unittest.TestCase):
    def test_dealer_stands_on_soft_17_by_default(self) -> None:
        cfg = GameConfig(dealer_soft17=DealerSoft17Rule.STAND)
        metrics = SimulationMetrics(strategy_name="test")
        shoe = Shoe(cfg, random.Random(1), cards=[Rank.FIVE], shuffle=False)
        cards = dealer_play([Rank.ACE, Rank.SIX], shoe, cfg, metrics)
        self.assertEqual(cards, [Rank.ACE, Rank.SIX])
        self.assertEqual(metrics.dealer_cards_drawn, 0)

    def test_dealer_hits_soft_17_when_configured(self) -> None:
        cfg = GameConfig(dealer_soft17=DealerSoft17Rule.HIT)
        metrics = SimulationMetrics(strategy_name="test")
        shoe = Shoe(cfg, random.Random(1), cards=[Rank.TEN], shuffle=False)
        cards = dealer_play([Rank.ACE, Rank.SIX], shoe, cfg, metrics)
        self.assertEqual(cards, [Rank.ACE, Rank.SIX, Rank.TEN])
        self.assertEqual(metrics.dealer_cards_drawn, 1)


class SplitAndRescueTests(unittest.TestCase):
    def test_split_hand_accounting(self) -> None:
        metrics = run_fixed(
            [
                Rank.EIGHT,
                Rank.SIX,
                Rank.EIGHT,
                Rank.TEN,
                Rank.THREE,
                Rank.TWO,
                Rank.TEN,
                Rank.TEN,
                Rank.TEN,
            ]
        )
        self.assertEqual(metrics.split_wagers, 1.0)
        self.assertEqual(metrics.double_wagers, 2.0)

    def test_rescue_uses_next_physical_card_and_discards_bust_card(self) -> None:
        metrics = run_fixed(
            [Rank.TEN, Rank.TEN, Rank.SIX, Rank.SEVEN, Rank.TEN, Rank.TWO]
        )
        self.assertEqual(metrics.rescue_attempts, 1)
        self.assertEqual(metrics.rescue_immediate_successes, 1)
        self.assertEqual(metrics.player_net_result, 0.5)
        event_group_keys = list(metrics.state_groups)
        self.assertTrue(any(key[5] == "2" for key in event_group_keys))

    def test_replacement_bust_settlement(self) -> None:
        metrics = run_fixed(
            [Rank.TEN, Rank.TEN, Rank.SIX, Rank.SEVEN, Rank.TEN, Rank.TEN]
        )
        self.assertEqual(metrics.rescue_attempts, 1)
        self.assertEqual(metrics.rescue_immediate_rebusts, 1)
        self.assertEqual(metrics.player_net_result, -1.5)

    def test_successful_rescue_followed_by_push(self) -> None:
        metrics = run_fixed(
            [Rank.TEN, Rank.TEN, Rank.SIX, Rank.EIGHT, Rank.TEN, Rank.TWO]
        )
        self.assertEqual(metrics.player_net_result, -0.5)
        self.assertEqual(metrics.rescued_final_pushes, 1)

    def test_successful_rescue_followed_by_loss(self) -> None:
        metrics = run_fixed(
            [Rank.TEN, Rank.TEN, Rank.SIX, Rank.NINE, Rank.TEN, Rank.TWO]
        )
        self.assertEqual(metrics.player_net_result, -1.5)
        self.assertEqual(metrics.rescued_final_losses, 1)

    def test_only_one_rescue_per_hand(self) -> None:
        metrics = run_fixed(
            [Rank.TEN, Rank.TEN, Rank.TWO, Rank.SEVEN, Rank.TEN, Rank.TWO, Rank.TEN]
        )
        self.assertEqual(metrics.player_bust_before_rescue, 2)
        self.assertEqual(metrics.rescue_opportunities, 1)
        self.assertEqual(metrics.rescue_attempts, 1)
        self.assertEqual(metrics.player_net_result, -1.5)


if __name__ == "__main__":
    unittest.main()
