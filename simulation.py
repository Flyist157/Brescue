"""Compatibility wrapper for ``python simulation.py``."""

from blackjack_rescue.simulation import main


if __name__ == "__main__":
    raise SystemExit(main())
