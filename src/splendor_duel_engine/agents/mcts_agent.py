"""MCTS Agent implementing the Agent protocol."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from splendor_duel_engine.agents.mcts_core import mcts_search
from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.engine.actions import Action
from splendor_duel_engine.engine.observation import Observation

if TYPE_CHECKING:
    from splendor_duel_engine.engine.observation import Observation


class MCTSAgent:
    """Monte Carlo Tree Search agent for Splendor Duel.

    Uses determinized MCTS: samples hidden information from the observation
    to create a fully-determined GameState, then runs UCT search with playouts.
    Runs MCTS for any decision point with multiple legal actions.
    """

    def __init__(
        self,
        seed: int | None = None,
        max_playouts: int = 2000,
        exploration: float = 1.414,
        playout_policy: str = "greedy",
    ) -> None:
        """Create an MCTS agent.

        Args:
            seed: Random seed for reproducibility. If None, uses system entropy.
            max_playouts: Number of playouts per search (default 2000).
            exploration: UCT exploration constant (default sqrt(2) ≈ 1.414).
            playout_policy: "greedy" or "random" for playout simulations (default "greedy").
        """
        if max_playouts < 1:
            raise ValueError("max_playouts must be >= 1")
        if playout_policy not in ("greedy", "random"):
            raise ValueError(
                f"playout_policy must be 'greedy' or 'random', got {playout_policy}"
            )
        self._rng = random.Random(seed)
        self._max_playouts = max_playouts
        self._exploration = exploration
        self._playout_policy = playout_policy

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        """Choose an action using MCTS from the given observation.

        Runs MCTS for any decision point with multiple legal actions.
        Early-returns the only legal action for forced moves.

        Args:
            observation: Partial observation from the player's perspective.
            legal_actions: Legal actions at this decision point.

        Returns:
            The action with the highest visit count from MCTS root,
            or the single legal action for forced moves.
        """
        # Fast path: forced moves (only 1 legal action)
        if len(legal_actions) == 1:
            return legal_actions[0]

        # Determinize the observation into a full GameState
        det_state = determinize(observation, self._rng)

        # Run MCTS search
        action = mcts_search(
            root_state=det_state,
            rng=self._rng,
            max_playouts=self._max_playouts,
            exploration=self._exploration,
            playout_policy=self._playout_policy,
        )

        # Action must be in legal_actions (it will be, since MCTS only expands legal moves)
        assert action in legal_actions
        return action
