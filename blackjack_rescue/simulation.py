"""Simulation orchestration and command-line interface."""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
from pathlib import Path
import random
import sys
from typing import Iterable

from .config import DealerSoft17Rule, GameConfig, RescueSettlementModel
from .game import BlackjackRescueGame
from .reporting import (
    ensure_output_dir,
    maybe_write_charts,
    write_markdown_report,
    write_policy_chart_csv,
    write_state_csv,
    write_summary_json,
)
from .rescue_strategy import (
    AlwaysRescue,
    BustedTotalPolicy,
    ImmediateSurvivalPolicy,
    NeverRescue,
    RescuePolicy,
    TablePolicy,
)
from .statistics import SimulationMetrics


def run_simulation(
    hands: int,
    config: GameConfig,
    rescue_policy: RescuePolicy,
    *,
    seed: int = 12345,
    progress: bool = False,
) -> SimulationMetrics:
    """Run one strategy for ``hands`` counted initial player hands."""

    rng = random.Random(seed)
    metrics = SimulationMetrics(strategy_name=rescue_policy.name)
    game = BlackjackRescueGame(config, rng, rescue_policy, metrics)
    next_progress = max(1, hands // 10)
    while metrics.initial_hands < hands:
        game.play_one_initial_hand()
        if progress and metrics.initial_hands and metrics.initial_hands % next_progress == 0:
            print(
                f"{rescue_policy.name}: {metrics.initial_hands}/{hands} hands",
                file=sys.stderr,
            )
    return metrics


def _run_worker(args: tuple[int, dict, object, int]) -> SimulationMetrics:
    hands, config_dict, policy, seed = args
    return run_simulation(
        hands,
        GameConfig.from_dict(config_dict),
        policy,  # type: ignore[arg-type]
        seed=seed,
        progress=False,
    )


def run_independent_runs(
    hands: int,
    config: GameConfig,
    policy: RescuePolicy,
    *,
    seed: int,
    runs: int = 1,
    workers: int = 1,
    progress: bool = False,
) -> SimulationMetrics:
    """Run independent seeds and aggregate their metrics."""

    if runs <= 1:
        return run_simulation(hands, config, policy, seed=seed, progress=progress)
    chunks = [hands // runs] * runs
    for i in range(hands % runs):
        chunks[i] += 1
    seeds = [seed + i * 1_000_003 for i in range(runs)]
    args = [(chunks[i], config.to_dict(), policy, seeds[i]) for i in range(runs)]
    aggregate = SimulationMetrics(strategy_name=policy.name)
    if workers > 1:
        with mp.Pool(processes=workers) as pool:
            for result in pool.imap_unordered(_run_worker, args):
                aggregate.merge(result)
    else:
        for arg in args:
            aggregate.merge(_run_worker(arg))
            if progress:
                print(
                    f"{policy.name}: {aggregate.initial_hands}/{hands} hands",
                    file=sys.stderr,
                )
    return aggregate


def policy_from_training(
    training_metrics: SimulationMetrics,
    group_name: str,
    *,
    name: str,
    min_samples: int = 30,
) -> TablePolicy:
    table = {
        key: stats.mean > 0.0
        for key, stats in training_metrics.policy_groups.get(group_name, {}).items()
        if stats.n >= min_samples
    }
    return TablePolicy(name=name, table=table, key_type=group_name)


def threshold_policies() -> list[BustedTotalPolicy]:
    return [BustedTotalPolicy(cutoff=cutoff) for cutoff in range(22, 31)]


def _set_relative_revenue(metrics: list[SimulationMetrics]) -> None:
    never = next((m for m in metrics if m.strategy_name == "never"), None)
    if never is None:
        return
    for metric in metrics:
        metric.extra_casino_revenue_vs_never = (
            metric.casino_net_result - never.casino_net_result
        )


def run_strategy_suite(
    hands: int,
    config: GameConfig,
    *,
    strategy: str = "all",
    seed: int = 12345,
    runs: int = 1,
    workers: int = 1,
    progress: bool = False,
    min_policy_samples: int = 30,
) -> tuple[list[SimulationMetrics], SimulationMetrics | None]:
    """Run requested strategies.

    Returns evaluation metrics and the Always-Rescue training metrics when a
    learned policy table was produced.
    """

    results: list[SimulationMetrics] = []
    training_metrics: SimulationMetrics | None = None

    def run(policy: RescuePolicy, run_seed: int = seed) -> SimulationMetrics:
        return run_independent_runs(
            hands,
            config,
            policy,
            seed=run_seed,
            runs=runs,
            workers=workers,
            progress=progress,
        )

    if strategy == "never":
        results.append(run(NeverRescue()))
    elif strategy == "always":
        results.append(run(AlwaysRescue()))
    elif strategy == "threshold-sweep":
        for policy in threshold_policies():
            results.append(run(policy))
    elif strategy == "composition":
        results.append(run(ImmediateSurvivalPolicy(threshold=2 / 3)))
    elif strategy in {"busted-total-dealer", "empirical", "all"}:
        training_metrics = run_independent_runs(
            hands,
            config,
            AlwaysRescue(),
            seed=seed,
            runs=runs,
            workers=workers,
            progress=progress,
        )
        if strategy == "busted-total-dealer":
            policy = policy_from_training(
                training_metrics,
                "busted_total_dealer",
                name="learned_busted_total_dealer",
                min_samples=min_policy_samples,
            )
            results.append(run(policy, seed + 99_991))
        elif strategy == "empirical":
            policy = policy_from_training(
                training_metrics,
                "full",
                name="empirical_full_visible",
                min_samples=min_policy_samples,
            )
            results.append(run(policy, seed + 99_991))
        else:
            results.append(run(NeverRescue()))
            results.append(training_metrics)
            threshold_results = [run(policy) for policy in threshold_policies()]
            results.extend(threshold_results)
            player_best = max(threshold_results, key=lambda m: m.player_net_result)
            player_best.strategy_name = "best_busted_total_threshold_" + player_best.strategy_name
            bt_dealer = policy_from_training(
                training_metrics,
                "busted_total_dealer",
                name="learned_busted_total_dealer",
                min_samples=min_policy_samples,
            )
            empirical = policy_from_training(
                training_metrics,
                "full",
                name="empirical_full_visible",
                min_samples=min_policy_samples,
            )
            results.append(run(bt_dealer, seed + 99_991))
            results.append(run(empirical, seed + 199_983))
    else:
        raise ValueError(f"unknown strategy {strategy}")

    _set_relative_revenue(results)
    return results, training_metrics


def baseline_validation_note(metrics: Iterable[SimulationMetrics]) -> str:
    never = next((m for m in metrics if m.strategy_name == "never"), None)
    if never is None:
        return "Never Rescue baseline was not run."
    hands = never.initial_hands
    edge = never.to_summary_dict()["house_edge_vs_original_initial_wagers"]
    plausible = -0.002 <= edge <= 0.010
    if hands < 50_000:
        return (
            f"Never Rescue house edge was {edge:.6f} over {hands} hands. "
            "This run is small, so the check is informational only."
        )
    if plausible:
        return (
            f"Never Rescue house edge was {edge:.6f} over {hands} hands, within "
            "a broad plausible range for six-deck S17 DAS 3:2 blackjack."
        )
    return (
        f"WARNING: Never Rescue house edge was {edge:.6f} over {hands} hands, "
        "outside the broad plausibility band used for a first-pass smoke check."
    )


def write_threshold_sweep_csv(metrics: Iterable[SimulationMetrics], output_dir: str | Path) -> Path:
    out = ensure_output_dir(output_dir)
    path = out / "threshold_sweep.csv"
    rows = [
        m.to_summary_dict()
        for m in metrics
        if m.strategy_name.startswith("busted_total_22_to_")
        or m.strategy_name.startswith("best_busted_total_threshold_")
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        if not rows:
            writer = csv.writer(fh)
            writer.writerow(["strategy"])
            return path
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_outputs(
    metrics: list[SimulationMetrics],
    config: GameConfig,
    output_dir: str | Path,
    training_metrics: SimulationMetrics | None = None,
) -> None:
    out = ensure_output_dir(output_dir)
    config.write_json(out / "config.json")
    write_summary_json(metrics, config, out)
    for metric in metrics:
        write_state_csv(metric, out)
    source_for_charts = training_metrics or next(
        (m for m in metrics if m.strategy_name == "always"), None
    )
    if source_for_charts is not None:
        for group in ["busted_total", "busted_total_dealer", "prehit_dealer", "full"]:
            write_policy_chart_csv(source_for_charts, group, out)
    write_threshold_sweep_csv(metrics, out)
    write_markdown_report(
        metrics,
        config,
        out,
        validation_note=baseline_validation_note(metrics),
    )
    maybe_write_charts(metrics, out)


def print_console_summary(metrics: Iterable[SimulationMetrics]) -> None:
    print("Strategy summary")
    print(
        "strategy,hands,player_net,house_edge_initial,house_edge_action,"
        "rescue_opportunities,rescue_attempts,avg_incremental_ev"
    )
    for metric in metrics:
        s = metric.to_summary_dict()
        print(
            f"{metric.strategy_name},{s['number_of_initial_hands']},"
            f"{s['player_net_result']:.4f},"
            f"{s['house_edge_vs_original_initial_wagers']:.6f},"
            f"{s['house_edge_vs_total_action']:.6f},"
            f"{s['rescue_opportunities']},{s['rescue_attempts']},"
            f"{s['average_incremental_ev_per_rescue_decision']:.6f}"
        )


def config_from_args(args: argparse.Namespace) -> GameConfig:
    if args.config:
        config = GameConfig.from_json_file(args.config)
    else:
        config = GameConfig()
    config.decks = args.decks
    config.penetration = args.penetration
    config.dealer_soft17 = DealerSoft17Rule.HIT if args.h17 else DealerSoft17Rule.STAND
    config.blackjack_payout = args.blackjack_payout
    config.rescue_cost = args.rescue_cost
    config.rescue_settlement_model = RescueSettlementModel(args.rescue_settlement_model)
    config.rescue_allowed_on_split_hands = args.rescue_on_splits
    config.rescue_allowed_after_double = args.rescue_after_doubles
    config.max_rescues_per_hand = args.max_rescues_per_hand
    config.__post_init__()
    return config


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blackjack Rescue Monte Carlo simulator")
    parser.add_argument("--hands", type=int, default=100_000)
    parser.add_argument("--strategy", default="all", choices=[
        "all",
        "never",
        "always",
        "threshold-sweep",
        "busted-total-dealer",
        "empirical",
        "composition",
    ])
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--decks", type=int, default=6)
    parser.add_argument("--penetration", type=float, default=0.75)
    parser.add_argument("--h17", action="store_true", help="Dealer hits soft 17")
    parser.add_argument("--blackjack-payout", type=float, default=1.5)
    parser.add_argument("--rescue-cost", type=float, default=0.5)
    parser.add_argument(
        "--rescue-settlement-model",
        choices=[model.value for model in RescueSettlementModel],
        default=RescueSettlementModel.NONREFUNDABLE_FEE.value,
    )
    parser.add_argument("--rescue-on-splits", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--rescue-after-doubles",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--max-rescues-per-hand", type=int, default=1)
    parser.add_argument("--output-dir", default="outputs/latest")
    parser.add_argument("--config", help="Optional JSON config file")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-policy-samples", type=int, default=30)
    parser.add_argument("--progress", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--charts", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.hands <= 0:
        parser.error("--hands must be positive")
    config = config_from_args(args)
    metrics, training_metrics = run_strategy_suite(
        args.hands,
        config,
        strategy=args.strategy,
        seed=args.seed,
        runs=args.runs,
        workers=args.workers,
        progress=args.progress,
        min_policy_samples=args.min_policy_samples,
    )
    write_outputs(metrics, config, args.output_dir, training_metrics=training_metrics)
    print_console_summary(metrics)
    print(f"Outputs written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
