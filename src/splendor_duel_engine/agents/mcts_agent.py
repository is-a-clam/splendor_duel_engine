"""MCTS Agent implementing the Agent protocol."""

from __future__ import annotations

import random
from collections import defaultdict

from splendor_duel_engine.agents.mcts_core import (
    MCTSNode,
    backpropagate,
    expand,
    playout,
    uct_select,
)
from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.engine.actions import Action
from splendor_duel_engine.engine.observation import Observation


class MCTSAgent:
    """Monte Carlo Tree Search agent for Splendor Duel.

    Uses multi-sample determinized MCTS: samples hidden information from the observation
    multiple times to create independent fully-determined GameStates, runs UCT search
    with playouts on each, and aggregates visit counts across all determinizations.
    Runs MCTS for any decision point with multiple legal actions.
    """

    def __init__(
        self,
        seed: int | None = None,
        max_playouts: int = 2000,
        exploration: float = 1.414,
        playout_policy: str = "random",
        num_determinizations: int = 20,
    ) -> None:
        """Create an MCTS agent.

        Args:
            seed: Random seed for reproducibility. If None, uses system entropy.
            max_playouts: Total number of playouts across all determinizations (default 2000).
            exploration: UCT exploration constant (default sqrt(2) ≈ 1.414).
            playout_policy: "greedy" or "random" for playout simulations (default "random").
            num_determinizations: Number of independent determinizations to sample (default 20).
                Each determinization gets max_playouts // num_determinizations playouts.
                Set to 1 to recover single-sample behavior.
        """
        if max_playouts < 1:
            raise ValueError("max_playouts must be >= 1")
        if playout_policy not in ("greedy", "random"):
            raise ValueError(
                f"playout_policy must be 'greedy' or 'random', got {playout_policy}"
            )
        if num_determinizations < 1:
            raise ValueError("num_determinizations must be >= 1")
        self._rng = random.Random(seed)
        self._max_playouts = max_playouts
        self._exploration = exploration
        self._playout_policy = playout_policy
        self._num_determinizations = num_determinizations

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        """Choose an action using multi-sample determinized MCTS.

        Runs MCTS on multiple independent determinizations of the observation
        and aggregates visit counts to reduce determinization bias.

        Args:
            observation: Partial observation from the player's perspective.
            legal_actions: Legal actions at this decision point.

        Returns:
            The action with the highest aggregated visit count across all determinizations,
            or the single legal action for forced moves.
        """
        # Fast path: forced moves (only 1 legal action)
        if len(legal_actions) == 1:
            return legal_actions[0]

        all_visits: dict[Action, int] = defaultdict(int)
        playouts_per_det = max(1, self._max_playouts // self._num_determinizations)

        for _ in range(self._num_determinizations):
            det_state = determinize(observation, self._rng)  # RNG advances each call
            root = MCTSNode(state=det_state, parent=None, action=None)

            for _ in range(playouts_per_det):
                node = uct_select(root, self._exploration)
                if node.is_terminal():
                    result = (
                        1.0 if node.state.winner == det_state.current_player else 0.0
                    )
                else:
                    node = expand(node, self._rng)
                    result = playout(
                        node.state, self._rng, self._playout_policy, max_depth=15
                    )
                backpropagate(node, result)

            # Aggregate visit counts
            for action, child in root.children.items():
                all_visits[action] += child.visits

        # Return most-visited action across all determinizations
        best_action = max(all_visits.items(), key=lambda kv: kv[1])[0]
        assert best_action in legal_actions
        return best_action
