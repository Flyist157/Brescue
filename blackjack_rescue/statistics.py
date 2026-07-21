"""Aggregated simulation and Rescue-state statistics."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Any

from .cards import cards_label, rank_label
from .hand import FinalOutcome
from .rescue_strategy import RescueContext


@dataclass(slots=True)
class RunningStats:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, x: float) -> None:
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (x - self.mean)

    def merge(self, other: "RunningStats") -> None:
        if other.n == 0:
            return
        if self.n == 0:
            self.n = other.n
            self.mean = other.mean
            self.m2 = other.m2
            return
        total_n = self.n + other.n
        delta = other.mean - self.mean
        self.m2 = self.m2 + other.m2 + delta * delta * self.n * other.n / total_n
        self.mean = (self.mean * self.n + other.mean * other.n) / total_n
        self.n = total_n

    @property
    def variance(self) -> float:
        return self.m2 / (self.n - 1) if self.n > 1 else 0.0

    @property
    def stddev(self) -> float:
        return sqrt(self.variance)

    @property
    def standard_error(self) -> float:
        return self.stddev / sqrt(self.n) if self.n else 0.0

    def ci95(self) -> tuple[float, float]:
        half = 1.96 * self.standard_error
        return self.mean - half, self.mean + half


@dataclass(slots=True)
class RescueEvent:
    context: RescueContext
    accepted: bool
    replacement_card: int | None = None
    immediate_survived: bool | None = None
    final_outcome: FinalOutcome | None = None
    final_result: float | None = None
    decline_result: float = -1.0
    exact_survival_probability: float | None = None

    @property
    def incremental_ev_sample(self) -> float | None:
        if self.final_result is None:
            return None
        return self.final_result - self.decline_result


@dataclass(slots=True)
class RescueStateAggregate:
    opportunities: int = 0
    attempts: int = 0
    immediate_successes: int = 0
    immediate_rebusts: int = 0
    final_wins: int = 0
    final_pushes: int = 0
    final_losses: int = 0
    result_stats: RunningStats = field(default_factory=RunningStats)
    incremental_stats: RunningStats = field(default_factory=RunningStats)

    def record(self, event: RescueEvent) -> None:
        self.opportunities += 1
        if not event.accepted:
            return
        self.attempts += 1
        if event.immediate_survived:
            self.immediate_successes += 1
        else:
            self.immediate_rebusts += 1
        if event.final_result is not None:
            self.result_stats.add(event.final_result)
        inc = event.incremental_ev_sample
        if inc is not None:
            self.incremental_stats.add(inc)
        if event.final_outcome in {FinalOutcome.WIN, FinalOutcome.BLACKJACK}:
            self.final_wins += 1
        elif event.final_outcome == FinalOutcome.PUSH:
            self.final_pushes += 1
        elif event.final_outcome in {FinalOutcome.LOSS, FinalOutcome.SURRENDER}:
            self.final_losses += 1


@dataclass(slots=True)
class SimulationMetrics:
    strategy_name: str
    initial_hands: int = 0
    rounds: int = 0
    aborted_rounds: int = 0
    original_wagers: float = 0.0
    rescue_wagers: float = 0.0
    double_wagers: float = 0.0
    split_wagers: float = 0.0
    player_net_result: float = 0.0
    blackjack_count: int = 0
    dealer_blackjack_count: int = 0
    player_bust_before_rescue: int = 0
    rescue_opportunities: int = 0
    rescue_attempts: int = 0
    rescue_immediate_successes: int = 0
    rescue_immediate_rebusts: int = 0
    rescued_final_wins: int = 0
    rescued_final_losses: int = 0
    rescued_final_pushes: int = 0
    dealer_cards_drawn: int = 0
    round_result_stats: RunningStats = field(default_factory=RunningStats)
    rescue_incremental_stats: RunningStats = field(default_factory=RunningStats)
    state_groups: dict[tuple[Any, ...], RescueStateAggregate] = field(default_factory=dict)
    policy_groups: dict[str, dict[tuple[Any, ...], RunningStats]] = field(
        default_factory=lambda: {
            "busted_total": {},
            "busted_total_dealer": {},
            "prehit_dealer": {},
            "full": {},
        }
    )
    extra_casino_revenue_vs_never: float = 0.0

    def add_round_result(self, result: float) -> None:
        self.rounds += 1
        self.initial_hands += 1
        self.player_net_result += result
        self.round_result_stats.add(result)

    def record_rescue_event(self, event: RescueEvent) -> None:
        self.rescue_opportunities += 1
        key = state_csv_key(event)
        self.state_groups.setdefault(key, RescueStateAggregate()).record(event)
        if not event.accepted:
            return
        self.rescue_attempts += 1
        if event.immediate_survived:
            self.rescue_immediate_successes += 1
        else:
            self.rescue_immediate_rebusts += 1
        inc = event.incremental_ev_sample
        if inc is not None:
            self.rescue_incremental_stats.add(inc)
            ctx = event.context
            keys = {
                "busted_total": ctx.busted_total_key(),
                "busted_total_dealer": ctx.busted_total_dealer_key(),
                "prehit_dealer": ctx.prehit_dealer_key(),
                "full": ctx.full_key(),
            }
            for group_name, key_value in keys.items():
                self.policy_groups[group_name].setdefault(key_value, RunningStats()).add(inc)
        if event.final_outcome in {FinalOutcome.WIN, FinalOutcome.BLACKJACK}:
            self.rescued_final_wins += 1
        elif event.final_outcome == FinalOutcome.PUSH:
            self.rescued_final_pushes += 1
        elif event.final_outcome in {FinalOutcome.LOSS, FinalOutcome.SURRENDER}:
            self.rescued_final_losses += 1

    @property
    def total_money_wagered(self) -> float:
        return (
            self.original_wagers
            + self.rescue_wagers
            + self.double_wagers
            + self.split_wagers
        )

    @property
    def casino_net_result(self) -> float:
        return -self.player_net_result

    def to_summary_dict(self) -> dict[str, Any]:
        ci_low, ci_high = self.round_result_stats.ci95()
        attempts = self.rescue_attempts
        opps = self.rescue_opportunities
        total_action = self.total_money_wagered
        initial = self.initial_hands
        return {
            "strategy": self.strategy_name,
            "number_of_initial_hands": initial,
            "number_of_rounds": self.rounds,
            "aborted_rounds": self.aborted_rounds,
            "total_original_wagers": self.original_wagers,
            "total_rescue_wagers": self.rescue_wagers,
            "total_double_wagers": self.double_wagers,
            "total_split_wagers": self.split_wagers,
            "total_money_wagered": total_action,
            "player_net_result": self.player_net_result,
            "casino_net_result": self.casino_net_result,
            "return_to_player": (
                (total_action + self.player_net_result) / total_action
                if total_action
                else 0.0
            ),
            "house_edge_vs_original_initial_wagers": (
                self.casino_net_result / self.original_wagers
                if self.original_wagers
                else 0.0
            ),
            "house_edge_vs_total_action": (
                self.casino_net_result / total_action if total_action else 0.0
            ),
            "average_casino_win_per_initial_hand": (
                self.casino_net_result / initial if initial else 0.0
            ),
            "standard_deviation_per_initial_hand": self.round_result_stats.stddev,
            "standard_error": self.round_result_stats.standard_error,
            "confidence_interval_95": [ci_low, ci_high],
            "blackjack_frequency": self.blackjack_count / initial if initial else 0.0,
            "dealer_blackjack_frequency": (
                self.dealer_blackjack_count / initial if initial else 0.0
            ),
            "player_bust_frequency_before_rescue": (
                self.player_bust_before_rescue / initial if initial else 0.0
            ),
            "rescue_opportunities": opps,
            "rescue_attempts": attempts,
            "rescue_acceptance_rate": attempts / opps if opps else 0.0,
            "immediate_rescue_success_rate": (
                self.rescue_immediate_successes / attempts if attempts else 0.0
            ),
            "immediate_rescue_rebust_rate": (
                self.rescue_immediate_rebusts / attempts if attempts else 0.0
            ),
            "rescued_hand_final_win_rate": (
                self.rescued_final_wins / attempts if attempts else 0.0
            ),
            "rescued_hand_final_loss_rate": (
                self.rescued_final_losses / attempts if attempts else 0.0
            ),
            "rescued_hand_final_push_rate": (
                self.rescued_final_pushes / attempts if attempts else 0.0
            ),
            "average_incremental_ev_per_rescue_decision": (
                self.rescue_incremental_stats.mean
                if self.rescue_incremental_stats.n
                else 0.0
            ),
            "additional_casino_revenue_attributable_to_rescue_vs_never": (
                self.extra_casino_revenue_vs_never
            ),
            "estimated_rescue_decisions_per_100_hands": (
                100 * opps / initial if initial else 0.0
            ),
            "estimated_extra_dealer_actions_per_100_hands": (
                100 * self.dealer_cards_drawn / initial if initial else 0.0
            ),
        }

    def merge(self, other: "SimulationMetrics") -> None:
        self.initial_hands += other.initial_hands
        self.rounds += other.rounds
        self.aborted_rounds += other.aborted_rounds
        self.original_wagers += other.original_wagers
        self.rescue_wagers += other.rescue_wagers
        self.double_wagers += other.double_wagers
        self.split_wagers += other.split_wagers
        self.player_net_result += other.player_net_result
        self.blackjack_count += other.blackjack_count
        self.dealer_blackjack_count += other.dealer_blackjack_count
        self.player_bust_before_rescue += other.player_bust_before_rescue
        self.rescue_opportunities += other.rescue_opportunities
        self.rescue_attempts += other.rescue_attempts
        self.rescue_immediate_successes += other.rescue_immediate_successes
        self.rescue_immediate_rebusts += other.rescue_immediate_rebusts
        self.rescued_final_wins += other.rescued_final_wins
        self.rescued_final_losses += other.rescued_final_losses
        self.rescued_final_pushes += other.rescued_final_pushes
        self.dealer_cards_drawn += other.dealer_cards_drawn
        self.round_result_stats.merge(other.round_result_stats)
        self.rescue_incremental_stats.merge(other.rescue_incremental_stats)
        for key, value in other.state_groups.items():
            target = self.state_groups.setdefault(key, RescueStateAggregate())
            target.opportunities += value.opportunities
            target.attempts += value.attempts
            target.immediate_successes += value.immediate_successes
            target.immediate_rebusts += value.immediate_rebusts
            target.final_wins += value.final_wins
            target.final_pushes += value.final_pushes
            target.final_losses += value.final_losses
            target.result_stats.merge(value.result_stats)
            target.incremental_stats.merge(value.incremental_stats)
        for group_name, groups in other.policy_groups.items():
            target_groups = self.policy_groups.setdefault(group_name, {})
            for key, stats in groups.items():
                target_groups.setdefault(key, RunningStats()).merge(stats)


def state_csv_key(event: RescueEvent) -> tuple[Any, ...]:
    ctx = event.context
    return (
        "soft" if ctx.pre_hit_soft else "hard",
        ctx.pre_hit_total,
        rank_label(ctx.dealer_upcard),
        rank_label(ctx.bust_card),
        ctx.busted_total,
        rank_label(event.replacement_card) if event.replacement_card is not None else "",
        event.final_outcome.value if event.final_outcome is not None else "declined",
        ctx.from_split,
        ctx.doubled,
        cards_label(ctx.pre_hit_cards),
    )


def state_group_row(key: tuple[Any, ...], aggregate: RescueStateAggregate) -> dict[str, Any]:
    attempts = aggregate.attempts
    low, high = aggregate.incremental_stats.ci95()
    mean_inc = aggregate.incremental_stats.mean if aggregate.incremental_stats.n else 0.0
    if aggregate.incremental_stats.n < 30:
        recommendation = "uncertain"
    elif low > 0:
        recommendation = "rescue"
    elif high < 0:
        recommendation = "decline"
    else:
        recommendation = "uncertain"
    return {
        "pre_hit_hard_or_soft": key[0],
        "pre_hit_total": key[1],
        "dealer_upcard": key[2],
        "bust_causing_card": key[3],
        "busted_total": key[4],
        "replacement_card": key[5],
        "final_hand_outcome": key[6],
        "split_hand_status": key[7],
        "double_status": key[8],
        "player_cards_before_hit": key[9],
        "opportunities": aggregate.opportunities,
        "rescue_attempts": attempts,
        "survival_probability": (
            aggregate.immediate_successes / attempts if attempts else 0.0
        ),
        "final_win_probability": aggregate.final_wins / attempts if attempts else 0.0,
        "final_push_probability": aggregate.final_pushes / attempts if attempts else 0.0,
        "final_loss_probability": aggregate.final_losses / attempts if attempts else 0.0,
        "average_total_result": aggregate.result_stats.mean if attempts else 0.0,
        "incremental_rescue_ev_versus_declining": mean_inc,
        "standard_error": aggregate.incremental_stats.standard_error,
        "confidence_interval_95_low": low,
        "confidence_interval_95_high": high,
        "recommended_decision": recommendation,
    }
