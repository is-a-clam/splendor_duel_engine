"""MCTS Agent implementing the Agent protocol."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field

from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.engine.actions import Action, apply, decide
from splendor_duel_engine.engine.colors import GEM_COLORS
from splendor_duel_engine.engine.observation import Observation, observation
from splendor_duel_engine.engine.state import GameState

# Factory functions for playout policies to ensure fresh RNG per playout.
# Both are callables accepting a seed derived from the MCTS RNG.
PLAYOUT_POLICIES = {
    "greedy": lambda seed: (
        GreedyAgent()
    ),  # GreedyAgent doesn't use seed, but keep consistent signature
    "random": lambda seed: RandomAgent(seed=seed),
}


@dataclass(slots=True)
class MCTSNode:
    """A node in the MCTS tree.

    Attributes:
        state: The game state at this node.
        parent: Parent node, or None for root.
        action: The action taken from parent to reach this node, or None for root.
        children: Map from action to child node.
        visits: Number of times this node has been visited.
        value: Accumulated value (sum of playout results from this node's perspective).
        untried_actions: Legal actions not yet expanded. Populated lazily on first expand.
            None means not yet initialized.
    """

    state: GameState
    parent: MCTSNode | None
    action: Action | None
    children: dict[Action, MCTSNode] = field(default_factory=dict)
    visits: int = 0
    value: float = 0.0
    untried_actions: list[Action] | None = None

    def is_fully_expanded(self) -> bool:
        """Return True if all legal actions have been tried."""
        if self.untried_actions is None:
            return False  # Not initialized yet
        return len(self.untried_actions) == 0

    def is_terminal(self) -> bool:
        """Return True if the game is over in this state."""
        return self.state.winner is not None


def uct_select(node: MCTSNode, exploration: float = 1.414) -> MCTSNode:
    """Select a node using the UCT formula.

    Traverses from the given node down to a leaf that is either not fully expanded
    or is terminal. At each step, if there are untried actions, returns the current
    node for expansion. Otherwise, selects the child with the highest UCT value.

    UCT formula: value/visits + exploration * sqrt(ln(parent.visits) / visits)

    Args:
        node: Starting node (typically the root).
        exploration: Exploration constant (default sqrt(2) ≈ 1.414).

    Returns:
        A node that is either terminal or not fully expanded.
    """
    while not node.is_terminal():
        if not node.is_fully_expanded():
            return node
        # Prefer unvisited children (visits == 0) for pure exploration
        unvisited = [c for c in node.children.values() if c.visits == 0]
        if unvisited:
            return unvisited[0]
        # UCT formula: value/visits + exploration * sqrt(ln(parent.visits)/visits)
        best_child = max(
            node.children.values(),
            key=lambda c: (
                (c.value / c.visits)
                + exploration * math.sqrt(math.log(node.visits) / c.visits)
            ),
        )
        node = best_child
    return node


def expand(node: MCTSNode, rng: random.Random) -> MCTSNode:
    """Expand the node by picking an untried action and creating a child.

    If untried_actions is None or empty, it is populated from the current state's legal
    actions. An action is chosen randomly from untried_actions, removed from the
    list, applied to the state, and a new child node is created and registered.
    Then, if the child has only one legal action (forced move), recursively expand
    through the chain of forced moves to skip deterministic transitions.

    Args:
        node: The node to expand.
        rng: Random number generator for action selection.

    Returns:
        The leaf node after auto-expanding through any forced moves.
    """
    if node.untried_actions is None or not node.untried_actions:
        node.untried_actions = list(decide(node.state).legal_actions)
    action = rng.choice(node.untried_actions)
    node.untried_actions.remove(action)
    new_state = apply(node.state, action)
    child = MCTSNode(state=new_state, parent=node, action=action)
    node.children[action] = child

    return _auto_expand_forced_moves(child)


def _auto_expand_forced_moves(node: MCTSNode) -> MCTSNode:
    """Recursively expand through forced moves (nodes with exactly one legal action).

    Many game phases have exactly one legal action (e.g., USE_PRIVILEGES -> DONE_WITH_PRIVILEGES
    -> REPLENISH -> DONE_WITH_REPLENISH -> MANDATORY). This function skips these
    deterministic chains so playouts start at actual decision points.

    Note: Even if the forced move is stochastic (e.g., REPLENISH draws random tokens),
    the child's state.rng is already advanced by apply(), so the single child correctly
    captures that randomness. The auto-expansion just skips the "choice" of which forced
    action to take (there's only one).

    Args:
        node: The node to start auto-expanding from.

    Returns:
        The leaf node after expanding through all forced moves.
    """
    while not node.is_terminal():
        dp = decide(node.state)
        if len(dp.legal_actions) != 1:
            break
        action = dp.legal_actions[0]
        new_state = apply(node.state, action)
        child = MCTSNode(state=new_state, parent=node, action=action)
        node.children[action] = child
        node = child
    return node


def _heuristic_evaluation(state: GameState, perspective: int) -> float:
    """Evaluate state from perspective player's view. Returns value in [0, 1].

    Heuristic combines:
    - Prestige difference (normalized)
    - Crown difference (each crown ~2 prestige value)
    - Single-color win proximity (color prestige difference)
    - Token advantage (especially gold)
    - Bonus token advantage
    - Reserved card potential

    Args:
        state: The game state to evaluate.
        perspective: The player index (0 or 1) to evaluate from.

    Returns:
        Value in [0, 1] where 1.0 is a certain win for perspective player,
        0.0 is a certain loss, 0.5 is even.
    """
    p = state.players[perspective]
    opp = state.players[1 - perspective]

    # Prestige difference (normalized)
    prestige_diff = p.prestige - opp.prestige

    # Crown difference (each crown ~2 prestige value)
    crown_diff = (p.crowns - opp.crowns) * 2

    # Single-color win proximity
    color_bonus = 0.0
    for color in GEM_COLORS:
        color_bonus += (p.color_prestige(color) - opp.color_prestige(color)) * 0.1

    # Token advantage: gold is most valuable, then pearls, then gems
    token_diff = (p.tokens.gold - opp.tokens.gold) * 3.0
    token_diff += (p.tokens.pearl - opp.tokens.pearl) * 1.5
    for color in GEM_COLORS:
        token_diff += (p.tokens.count(color) - opp.tokens.count(color)) * 0.5

    # Bonus token advantage (each bonus is worth ~1 prestige in that color)
    bonus_diff = 0.0
    for color in GEM_COLORS:
        bonus_diff += (p.bonus.count(color) - opp.bonus.count(color)) * 1.0

    # Reserved card potential (high-value reserved cards)
    reserved_diff = 0.0
    for rc in p.reserved:
        card = rc.card
        reserved_diff += card.points * 0.5 + card.crowns * 1.0
    for rc in opp.reserved:
        card = rc.card
        reserved_diff -= card.points * 0.5 + card.crowns * 1.0

    # Combine and normalize to [0, 1]
    # Scaling factor: prestige ~20, crowns ~20, color ~10, tokens ~20, bonuses ~10, reserved ~10
    score = (
        prestige_diff
        + crown_diff
        + color_bonus
        + token_diff
        + bonus_diff
        + reserved_diff
    )
    return max(0.0, min(1.0, 0.5 + score / 80.0))


def playout(
    state: GameState,
    rng: random.Random,
    playout_policy: str = "greedy",
    max_depth: int = 15,
) -> float:
    """
    Simulate from current state with limited-depth playout.

    - state.rng is pre-seeded from determinization (for tree determinism)
    - engine.apply deep-copies state.rng before any random draw
    - First replenish: uses the pre-seeded RNG (deterministic per root)
    - Subsequent random draws: use the advanced RNG from previous draws
    - playout_policy agents are seeded from MCTS RNG for decision randomness
    - Playouts stop at max_depth plies and return heuristic evaluation

    Args:
        state: Starting game state (must be determinized).
        rng: Random number generator (used to derive agent seeds).
        playout_policy: "greedy" or "random" (default "greedy").
        max_depth: Maximum number of plies to simulate before heuristic evaluation (default 15).

    Returns:
        1.0 if current player wins, 0.5 for draw, 0.0 if current player loses.
    """
    current_player = state.current_player

    # Derive distinct agent seeds from the MCTS RNG to avoid correlation
    # in symmetric positions. XOR with 0xFFFFFFFF ensures different sequences.
    agent_seed_0 = rng.randint(0, 2**31 - 1)
    agent_seed_1 = rng.randint(0, 2**31 - 1) ^ 0xFFFFFFFF

    policy_factory = PLAYOUT_POLICIES[playout_policy]
    agent0 = policy_factory(agent_seed_0)
    agent1 = policy_factory(agent_seed_1)

    current_state = state
    depth = 0

    while current_state.winner is None and depth < max_depth:
        player = current_state.current_player
        obs = observation(current_state, player)
        dp = decide(current_state)
        agent = agent0 if player == 0 else agent1
        action = agent.choose_action(obs, dp.legal_actions)
        current_state = apply(current_state, action)
        depth += 1

    if current_state.winner is not None:
        return 1.0 if current_state.winner == current_player else 0.0

    # Heuristic evaluation from current_state perspective
    return _heuristic_evaluation(current_state, current_player)


def backpropagate(node: MCTSNode, result: float):
    """Backpropagate the playout result up to the root.

    Updates visits and value for each node on the path from the given node
    to the root (inclusive).

    Args:
        node: The leaf node where the playout ended.
        result: Playout result from the perspective of the root player
            (1.0 win, 0.5 draw, 0.0 loss).
    """
    current: MCTSNode | None = node
    while current is not None:
        current.visits += 1
        current.value += result
        current = current.parent


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
