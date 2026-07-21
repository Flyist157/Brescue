"""CSV, JSON, markdown, and optional chart reporting."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .cards import rank_label
from .config import GameConfig
from .statistics import SimulationMetrics, state_group_row


def ensure_output_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_summary_json(
    metrics: Iterable[SimulationMetrics], config: GameConfig, output_dir: str | Path
) -> Path:
    out = ensure_output_dir(output_dir)
    payload = {
        "configuration": config.to_dict(),
        "results": [m.to_summary_dict() for m in metrics],
    }
    path = out / "summary.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def write_state_csv(metrics: SimulationMetrics, output_dir: str | Path) -> Path:
    out = ensure_output_dir(output_dir)
    path = out / f"rescue_states_{metrics.strategy_name}.csv"
    rows = [state_group_row(key, agg) for key, agg in metrics.state_groups.items()]
    rows.sort(
        key=lambda row: (
            row["pre_hit_hard_or_soft"],
            row["pre_hit_total"],
            row["dealer_upcard"],
            row["busted_total"],
            row["replacement_card"],
            row["final_hand_outcome"],
        )
    )
    fieldnames = [
        "pre_hit_hard_or_soft",
        "pre_hit_total",
        "dealer_upcard",
        "bust_causing_card",
        "busted_total",
        "replacement_card",
        "final_hand_outcome",
        "split_hand_status",
        "double_status",
        "player_cards_before_hit",
        "opportunities",
        "rescue_attempts",
        "survival_probability",
        "final_win_probability",
        "final_push_probability",
        "final_loss_probability",
        "average_total_result",
        "incremental_rescue_ev_versus_declining",
        "standard_error",
        "confidence_interval_95_low",
        "confidence_interval_95_high",
        "recommended_decision",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_policy_chart_csv(
    metrics: SimulationMetrics, group_name: str, output_dir: str | Path, min_samples: int = 30
) -> Path:
    out = ensure_output_dir(output_dir)
    path = out / f"practical_chart_{group_name}_{metrics.strategy_name}.csv"
    rows: list[dict[str, object]] = []
    for key, stats in metrics.policy_groups.get(group_name, {}).items():
        low, high = stats.ci95()
        if stats.n < min_samples:
            rec = "uncertain"
        elif low > 0:
            rec = "rescue"
        elif high < 0:
            rec = "decline"
        else:
            rec = "uncertain"
        row: dict[str, object] = {
            "samples": stats.n,
            "mean_incremental_ev": stats.mean,
            "standard_error": stats.standard_error,
            "confidence_interval_95_low": low,
            "confidence_interval_95_high": high,
            "recommended_decision": rec,
        }
        if group_name == "busted_total":
            row["busted_total"] = key[0]
        elif group_name == "busted_total_dealer":
            row["busted_total"] = key[0]
            row["dealer_upcard"] = rank_label(key[1])
        elif group_name == "prehit_dealer":
            row["pre_hit_total"] = key[0]
            row["pre_hit_soft"] = key[1]
            row["dealer_upcard"] = rank_label(key[2])
        elif group_name == "full":
            row.update(
                {
                    "player_cards_before_hit": key[0],
                    "pre_hit_total": key[1],
                    "pre_hit_soft": key[2],
                    "bust_card": rank_label(key[3]),
                    "busted_total": key[4],
                    "dealer_upcard": rank_label(key[5]),
                    "split_hand": key[6],
                    "doubled": key[7],
                    "double_available": key[8],
                }
            )
        rows.append(row)
    rows.sort(key=lambda r: tuple(str(v) for v in r.values()))
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    if not fieldnames:
        fieldnames = ["samples", "mean_incremental_ev", "recommended_decision"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_markdown_report(
    metrics: Iterable[SimulationMetrics],
    config: GameConfig,
    output_dir: str | Path,
    *,
    validation_note: str = "",
) -> Path:
    out = ensure_output_dir(output_dir)
    metrics_list = list(metrics)
    path = out / "report.md"
    with path.open("w", encoding="utf-8") as fh:
        fh.write("# Blackjack Rescue Simulation Report\n\n")
        fh.write("## Assumptions and configurable ambiguous rules\n\n")
        fh.write(
            "- Rescue wager default: nonrefundable fee paid to replace the bust card.\n"
            "- A rescued win pays only the original hand wager; default net is +0.5 units.\n"
            "- A rescued push loses the Rescue fee; default net is -0.5 units.\n"
            "- Rescue is allowed on split hands but not after doubled hands by default.\n"
            "- The bust-causing card is exposed, removed from the hand, and discarded.\n"
            "- The replacement is the next physical card in the finite shoe.\n"
            "- The player may hit again after a successful Rescue by default.\n"
            "- Rescue does not apply to dealer hands.\n"
            "- If an active shoe cannot complete a round, the default procedure aborts that round, reshuffles, and retries without counting the aborted hand.\n\n"
        )
        fh.write("## Configuration\n\n")
        fh.write("```json\n")
        fh.write(json.dumps(config.to_dict(), indent=2, sort_keys=True))
        fh.write("\n```\n\n")
        if validation_note:
            fh.write("## Baseline validation\n\n")
            fh.write(validation_note + "\n\n")
        fh.write("## Strategy comparison\n\n")
        fh.write(
            "| Strategy | Hands | Player net | House edge vs initial | House edge vs action | Rescue attempts | Avg inc EV |\n"
        )
        fh.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for m in metrics_list:
            s = m.to_summary_dict()
            fh.write(
                f"| {m.strategy_name} | {s['number_of_initial_hands']} | "
                f"{s['player_net_result']:.4f} | "
                f"{s['house_edge_vs_original_initial_wagers']:.6f} | "
                f"{s['house_edge_vs_total_action']:.6f} | "
                f"{s['rescue_attempts']} | "
                f"{s['average_incremental_ev_per_rescue_decision']:.6f} |\n"
            )
        fh.write("\n## Mathematical and procedural issues discovered\n\n")
        fh.write(
            "- Immediate replacement survival probability is not equivalent to full Rescue EV; surviving hands can later lose or push.\n"
            "- Rescue changes card consumption, so common random seeds provide reproducibility but not identical downstream shoes after divergent decisions.\n"
            "- Low-sample full-visible states require independent validation and should be marked uncertain.\n"
        )
    return path


def maybe_write_charts(metrics: Iterable[SimulationMetrics], output_dir: str | Path) -> list[Path]:
    """Create optional charts when matplotlib is available."""

    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        return []
    out = ensure_output_dir(output_dir)
    metrics_list = list(metrics)
    paths: list[Path] = []
    names = [m.strategy_name for m in metrics_list]
    edges = [m.to_summary_dict()["house_edge_vs_original_initial_wagers"] for m in metrics_list]
    plt.figure(figsize=(max(6, len(names) * 0.8), 4))
    plt.bar(names, edges)
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("House edge vs initial wager")
    plt.tight_layout()
    path = out / "house_edge_by_strategy.png"
    plt.savefig(path)
    plt.close()
    paths.append(path)
    return paths
