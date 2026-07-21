"""Blackjack Rescue finite-shoe simulator."""

from .config import GameConfig
from .simulation import run_simulation, run_strategy_suite

__all__ = ["GameConfig", "run_simulation", "run_strategy_suite"]
