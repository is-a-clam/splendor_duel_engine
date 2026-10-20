"""MCTS core with UCT tree search, playouts, and backpropagation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from splendor_duel_engine.agents.base import play_game_from_state
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.engine.actions import Action, apply, decide
from splendor_duel_engine.engine.state import GameState

# Factory functions for playout policies to ensure fresh RNG per playout.
# Both are callables accepting a seed derived from the MCTS RNG.
PLAYOUT_POLICIES = {
    "greedy": lambda seed: GreedyAgent(),
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

    Args:
        node: The node to expand.
        rng: Random number generator for action selection.

    Returns:
        The newly created child node.
    """
    if node.untried_actions is None or not node.untried_actions:
        node.untried_actions = list(decide(node.state).legal_actions)
    action = rng.choice(node.untried_actions)
    node.untried_actions.remove(action)
    new_state = apply(node.state, action)
    child = MCTSNode(state=new_state, parent=node, action=action)
    node.children[action] = child
    return child


def playout(
    state: GameState, rng: random.Random, playout_policy: str = "greedy"
) -> float:
    """Simulate from the current state to terminal using the given policy.

    Returns the result from the perspective of the player whose turn it is
    in the given state: 1.0 for win, 0.5 for draw, 0.0 for loss.

    A fresh RNG is derived from the passed ``rng`` for this playout branch,
    used for both game-internal randomness (replenish draws, etc.) and for
    seeding the playout agents.

    Args:
        state: Starting game state.
        rng: Random number generator (used to derive playout branch RNG and agent seeds).
        playout_policy: "greedy" or "random" (default "greedy").

    Returns:
        1.0 if current player wins, 0.5 for draw, 0.0 if current player loses.
    """
    current_player = state.current_player

    # Derive a branch-specific RNG and agent seeds from the MCTS RNG
    branch_rng = random.Random(rng.randint(0, 2**31 - 1))
    agent_seed = rng.randint(0, 2**31 - 1)

    policy_factory = PLAYOUT_POLICIES[playout_policy]
    agent0 = policy_factory(agent_seed)
    agent1 = policy_factory(agent_seed)

    final = play_game_from_state(state, agent0, agent1, branch_rng)

    if final.winner is None:
        return 0.5
    return 1.0 if final.winner == current_player else 0.0


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


def mcts_search(
    root_state: GameState,
    rng: random.Random,
    max_playouts: int,
    exploration: float = 1.414,
    playout_policy: str = "greedy",
) -> Action:
    """Run MCTS search and return the most-visited action.

    Builds a tree from the determinized root state, runs the specified number
    of playouts, and returns the action with the highest visit count at the root.

    The tree is discarded after each call (no memory leak across decisions).

    Args:
        root_state: Fully determinized game state to search from.
        rng: Random number generator for reproducibility.
        max_playouts: Number of playouts to run.
        exploration: UCT exploration constant (default sqrt(2)).
        playout_policy: "greedy" or "random" for playout simulations.

    Returns:
        The action with the most visits from the root.
    """
    # Handle terminal root state
    if root_state.winner is not None:
        # Game is already over; return a dummy legal action (should not happen in practice)
        # but we need to return something. Get legal actions from a non-terminal copy.
        # Actually, this case should never be called in practice.
        raise ValueError("mcts_search called on terminal state")

    root = MCTSNode(state=root_state, parent=None, action=None)
    for _ in range(max_playouts):
        node = uct_select(root, exploration)
        if node.is_terminal():
            # Terminal node — backpropagate result directly
            current_player = root_state.current_player
            result = 1.0 if node.state.winner == current_player else 0.0
            backpropagate(node, result)
        elif not node.is_fully_expanded():
            # Leaf node that can be expanded
            node = expand(node, rng)
            result = playout(node.state, rng, playout_policy)
            backpropagate(node, result)
        else:
            # This branch should be unreachable: uct_select guarantees we only
            # reach here for terminal or not-fully-expanded nodes.
            # If somehow reached (e.g., logic bug), treat as a draw to avoid
            # corrupting the tree with arbitrary values.
            backpropagate(node, 0.5)
    # Return most-visited action
    if not root.children:
        # No playouts completed (e.g., max_playouts=0 or all led to terminal immediately)
        # Fall back to a legal action
        legal = decide(root_state).legal_actions
        if legal:
            return legal[0]
        raise ValueError("no legal actions in root state")
    best_action = max(root.children.items(), key=lambda kv: kv[1].visits)[0]
    return best_action
