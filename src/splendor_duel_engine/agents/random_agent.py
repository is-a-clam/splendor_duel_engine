"""Random baseline agent: picks uniformly from the offered legal actions."""

from __future__ import annotations

import random

from splendor_duel_engine.engine.actions import Action
from splendor_duel_engine.engine.observation import Observation


class RandomAgent:
    """Chooses uniformly at random from the legal actions it is given.

    Deterministic given ``seed``: all randomness comes from an internal
    :class:`random.Random`, never the global generator.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        """Return one of ``legal_actions`` selected uniformly at random."""
        return self._rng.choice(legal_actions)
