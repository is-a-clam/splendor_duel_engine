"""Tests for the MCTS core with UCT tree search."""

from __future__ import annotations

import random
from dataclasses import replace

from splendor_duel_engine.engine.actions import (
    BuyCard,
    DoneWithPrivileges,
    DoneWithReplenish,
    apply,
    decide,
)
from splendor_duel_engine.engine.cards import load_cards
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import (
    GameState,
    PlayerState,
    PurchasedCard,
)
from splendor_duel_engine.mcts.mcts_core import (
    MCTSNode,
    _heuristic_evaluation,
    backpropagate,
    expand,
    mcts_search,
    uct_select,
)
from splendor_duel_engine.mcts.mcts_determinize import determinize


def _advance_to_mandatory(state):
    """Advance from initial state to MANDATORY phase."""
    # USE_PRIVILEGES -> DoneWithPrivileges -> REPLENISH
    state = replace(state, phase=Phase.USE_PRIVILEGES)
    state = apply(state, DoneWithPrivileges())
    # REPLENISH -> DoneWithReplenish -> MANDATORY (bag is empty initially)
    state = apply(state, DoneWithReplenish())
    assert state.phase == Phase.MANDATORY
    return state


def test_mcts_node_creation():
    state = GameState.new_game(0)
    node = MCTSNode(state=state, parent=None, action=None)
    assert node.visits == 0
    assert node.value == 0.0
    assert node.children == {}
    assert node.untried_actions is None  # populated lazily on first expand/select


def test_uct_select_prefers_unvisited():
    # Node with unvisited children should select one of them
    state = _advance_to_mandatory(GameState.new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    # Manually populate children with one visited, one unvisited
    dp = decide(state)
    actions = list(dp.legal_actions)
    assert len(actions) >= 2

    child1 = MCTSNode(state=GameState.new_game(1), parent=root, action=actions[0])
    child1.visits = 1
    child1.value = 1.0
    root.children[actions[0]] = child1

    child2 = MCTSNode(state=GameState.new_game(2), parent=root, action=actions[1])
    child2.visits = 0
    child2.value = 0.0
    root.children[actions[1]] = child2

    root.untried_actions = []  # fully expanded

    selected = uct_select(root, exploration=1.414)
    # Should select the unvisited child
    assert selected is child2


def test_uct_select_balances_exploitation_exploration():
    # Child with high value but many visits vs low value few visits
    state = _advance_to_mandatory(GameState.new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    dp = decide(state)
    actions = list(dp.legal_actions)
    assert len(actions) >= 2

    # Child with high win rate but many visits
    child1 = MCTSNode(state=GameState.new_game(1), parent=root, action=actions[0])
    child1.visits = 100
    child1.value = 90.0  # 90% win rate
    root.children[actions[0]] = child1

    # Child with lower win rate but very few visits
    child2 = MCTSNode(state=GameState.new_game(2), parent=root, action=actions[1])
    child2.visits = 2
    child2.value = 1.0  # 50% win rate
    root.children[actions[1]] = child2

    root.untried_actions = []
    root.visits = 102

    # With high exploration constant, should prefer the less-visited child
    selected = uct_select(root, exploration=10.0)
    assert selected is child2

    # With zero exploration, should prefer the higher value child
    selected = uct_select(root, exploration=0.0)
    assert selected is child1


def test_expand_creates_valid_child():
    state = _advance_to_mandatory(GameState.new_game(0))
    node = MCTSNode(state=state, parent=None, action=None)
    # Manually populate untried_actions from decide(state).legal_actions
    dp = decide(state)
    node.untried_actions = list(dp.legal_actions)
    original_untried = list(node.untried_actions)

    child = expand(node, random.Random(0))
    assert child.parent is node
    assert child.action in original_untried  # action was from untried before removal
    assert child.action not in node.untried_actions  # removed from untried
    assert child.action in node.children
    assert node.children[child.action] is child


def test_backpropagate_updates_path():
    state = _advance_to_mandatory(GameState.new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    dp = decide(state)
    some_action = dp.legal_actions[0]
    child = MCTSNode(state=GameState.new_game(1), parent=root, action=some_action)
    root.children[some_action] = child
    backpropagate(child, 1.0)
    assert child.visits == 1
    assert child.value == 1.0
    assert root.visits == 1
    assert root.value == 1.0


def test_backpropagate_partial_result():
    state = _advance_to_mandatory(GameState.new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    dp = decide(state)
    some_action = dp.legal_actions[0]
    child = MCTSNode(state=GameState.new_game(1), parent=root, action=some_action)
    root.children[some_action] = child
    backpropagate(child, 0.5)
    assert child.visits == 1
    assert child.value == 0.5
    assert root.visits == 1
    assert root.value == 0.5


def test_mcts_search_returns_legal_action():
    state = _advance_to_mandatory(GameState.new_game(0))
    obs = observation(state, 0)
    det_state = determinize(obs, random.Random(0))
    visits = mcts_search(det_state, random.Random(0), max_playouts=100)
    # Action must be legal in the original state
    dp = decide(state)
    # Get the most-visited action
    best_action = max(visits.items(), key=lambda kv: kv[1])[0]
    assert best_action in dp.legal_actions


def test_mcts_search_deterministic_with_same_seed():
    state = _advance_to_mandatory(GameState.new_game(0))
    obs = observation(state, 0)
    det = determinize(obs, random.Random(0))
    a1 = mcts_search(det, random.Random(42), max_playouts=200)
    a2 = mcts_search(det, random.Random(42), max_playouts=200)
    assert a1 == a2


def test_mcts_search_handles_terminal_state():
    # If the root is already terminal, search should raise an error (not a valid use case)
    state = _advance_to_mandatory(GameState.new_game(0))
    terminal_state = replace(state, winner=0)
    try:
        mcts_search(terminal_state, random.Random(0), max_playouts=10)
        assert False, "Expected ValueError for terminal state"
    except ValueError as e:
        assert "terminal" in str(e).lower()


def test_mcts_node_is_terminal():
    state = _advance_to_mandatory(GameState.new_game(0))
    node = MCTSNode(state=state, parent=None, action=None)
    assert not node.is_terminal()

    terminal_state = replace(state, winner=0)
    terminal_node = MCTSNode(state=terminal_state, parent=None, action=None)
    assert terminal_node.is_terminal()


def test_mcts_node_is_fully_expanded():
    state = _advance_to_mandatory(GameState.new_game(0))
    node = MCTSNode(state=state, parent=None, action=None)
    assert not node.is_fully_expanded()  # untried_actions is None -> not fully expanded

    dp = decide(state)
    node.untried_actions = list(dp.legal_actions)
    assert not node.is_fully_expanded()

    node.untried_actions = []
    assert node.is_fully_expanded()


def test_expand_auto_expands_forced_moves():
    """Test that expand auto-expands through forced move chains.

    From the initial state, expanding should skip the forced phases
    (USE_PRIVILEGES -> DONE_WITH_PRIVILEGES -> REPLENISH -> DONE_WITH_REPLENISH)
    and create children at the MANDATORY phase where real decisions happen.
    """
    state = GameState.new_game(0)
    root = MCTSNode(state=state, parent=None, action=None)

    # Initial state is USE_PRIVILEGES with only one legal action: DoneWithPrivileges
    dp = decide(state)
    assert len(dp.legal_actions) == 1
    assert isinstance(dp.legal_actions[0], DoneWithPrivileges)

    # Expand once
    child = expand(root, random.Random(0))

    # The child should be at MANDATORY phase (after auto-expanding through
    # USE_PRIVILEGES -> DONE_WITH_PRIVILEGES -> REPLENISH -> DONE_WITH_REPLENISH)
    from splendor_duel_engine.engine.phase import Phase

    assert child.state.phase == Phase.MANDATORY, (
        f"Expected MANDATORY phase after auto-expand, got {child.state.phase}"
    )

    # The root should have exactly one child (the forced move chain was auto-expanded)
    assert len(root.children) == 1

    # The child should have multiple legal actions (actual decisions at MANDATORY)
    child_dp = decide(child.state)
    assert len(child_dp.legal_actions) > 1, (
        f"Expected multiple legal actions at MANDATORY, got {len(child_dp.legal_actions)}"
    )


def test_heuristic_evaluation_returns_valid_range():
    """Test that _heuristic_evaluation returns a value in [0, 1]."""
    state = _advance_to_mandatory(GameState.new_game(0))
    # Test from both perspectives
    for perspective in (0, 1):
        value = _heuristic_evaluation(state, perspective)
        assert 0.0 <= value <= 1.0, (
            f"Heuristic value {value} not in [0, 1] for perspective {perspective}"
        )


def test_heuristic_evaluation_symmetric():
    """Test that heuristic evaluation is symmetric (v1 = 1 - v2 for zero-sum)."""
    state = _advance_to_mandatory(GameState.new_game(0))
    v0 = _heuristic_evaluation(state, 0)
    v1 = _heuristic_evaluation(state, 1)
    # For the initial symmetric state, both should be 0.5
    assert abs(v0 - 0.5) < 0.01, f"Initial state should be ~0.5 for player 0, got {v0}"
    assert abs(v1 - 0.5) < 0.01, f"Initial state should be ~0.5 for player 1, got {v1}"
    # And they should sum to 1.0
    assert abs(v0 + v1 - 1.0) < 0.01


def test_heuristic_evaluation_favors_leading_player():
    """Test that heuristic favors player with more prestige, crowns, and color concentration."""
    from dataclasses import replace as dc_replace

    from splendor_duel_engine.engine.cards import Card

    # Create a state where player 0 is clearly winning
    base_state = _advance_to_mandatory(GameState.new_game(0))

    # Give player 0 more prestige and crowns
    player0 = PlayerState(
        tokens=Tokens(),
        bonus=Tokens(white=2),  # 2 white bonuses
        prestige=15,
        crowns=5,
        reserved=(),
        purchased=(
            # Add a purchased card with white bonus to increase color prestige
            PurchasedCard(
                card=Card(
                    id="TEST-WHITE",
                    level=1,
                    points=3,
                    crowns=0,
                    bonus=Color.WHITE,
                    bonus_count=2,
                    ability=None,
                    is_multicolor=False,
                    cost=Tokens(),
                ),
                chosen_color=None,
            ),
        ),
        privileges=0,
    )
    player1 = PlayerState(
        tokens=Tokens(),
        bonus=Tokens(),
        prestige=5,
        crowns=1,
        reserved=(),
        purchased=(),
        privileges=0,
    )

    test_state = dc_replace(base_state, players=(player0, player1))

    v0 = _heuristic_evaluation(test_state, 0)
    v1 = _heuristic_evaluation(test_state, 1)

    # Player 0 should have a significantly higher evaluation
    assert v0 > 0.7, f"Player 0 should be strongly favored, got {v0}"
    assert v1 < 0.3, f"Player 1 should be disfavored, got {v1}"
    assert v0 > v1
