"""Tests for the MCTS core with UCT tree search."""

from __future__ import annotations

import random
from dataclasses import replace

from splendor_duel_engine.agents.mcts_core import (
    MCTSNode,
    _heuristic_evaluation,
    backpropagate,
    expand,
    mcts_search,
    playout,
    uct_select,
)
from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.engine.actions import (
    DoneWithPrivileges,
    DoneWithReplenish,
    apply,
    decide,
)
from splendor_duel_engine.engine.cards import load_cards
from splendor_duel_engine.engine.colors import Color
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import (
    PlayerState,
    PurchasedCard,
    Tokens,
    new_game,
)


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
    state = new_game(0)
    node = MCTSNode(state=state, parent=None, action=None)
    assert node.visits == 0
    assert node.value == 0.0
    assert node.children == {}
    assert node.untried_actions is None  # populated lazily on first expand/select


def test_uct_select_prefers_unvisited():
    # Node with unvisited children should select one of them
    state = _advance_to_mandatory(new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    # Manually populate children with one visited, one unvisited
    dp = decide(state)
    actions = list(dp.legal_actions)
    assert len(actions) >= 2

    child1 = MCTSNode(state=new_game(1), parent=root, action=actions[0])
    child1.visits = 1
    child1.value = 1.0
    root.children[actions[0]] = child1

    child2 = MCTSNode(state=new_game(2), parent=root, action=actions[1])
    child2.visits = 0
    child2.value = 0.0
    root.children[actions[1]] = child2

    root.untried_actions = []  # fully expanded

    selected = uct_select(root, exploration=1.414)
    # Should select the unvisited child
    assert selected is child2


def test_uct_select_balances_exploitation_exploration():
    # Child with high value but many visits vs low value few visits
    state = _advance_to_mandatory(new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    dp = decide(state)
    actions = list(dp.legal_actions)
    assert len(actions) >= 2

    # Child with high win rate but many visits
    child1 = MCTSNode(state=new_game(1), parent=root, action=actions[0])
    child1.visits = 100
    child1.value = 90.0  # 90% win rate
    root.children[actions[0]] = child1

    # Child with lower win rate but very few visits
    child2 = MCTSNode(state=new_game(2), parent=root, action=actions[1])
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
    state = _advance_to_mandatory(new_game(0))
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


def test_playout_returns_valid_result():
    state = _advance_to_mandatory(new_game(0))
    result = playout(state, random.Random(0), playout_policy="random")
    assert 0.0 <= result <= 1.0


def test_playout_handles_multiple_replenishes():
    # During playout, if a second replenish occurs, the engine should
    # resample from the current bag (which includes tokens spent since last replenish)
    # This test verifies the engine's apply handles this correctly.
    # For MCTS core, we just verify playout terminates and returns valid value.
    state = _advance_to_mandatory(new_game(0))
    result = playout(state, random.Random(0), playout_policy="random")
    assert 0.0 <= result <= 1.0


def test_backpropagate_updates_path():
    state = _advance_to_mandatory(new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    dp = decide(state)
    some_action = dp.legal_actions[0]
    child = MCTSNode(state=new_game(1), parent=root, action=some_action)
    root.children[some_action] = child
    backpropagate(child, 1.0)
    assert child.visits == 1
    assert child.value == 1.0
    assert root.visits == 1
    assert root.value == 1.0


def test_backpropagate_partial_result():
    state = _advance_to_mandatory(new_game(0))
    root = MCTSNode(state=state, parent=None, action=None)
    dp = decide(state)
    some_action = dp.legal_actions[0]
    child = MCTSNode(state=new_game(1), parent=root, action=some_action)
    root.children[some_action] = child
    backpropagate(child, 0.5)
    assert child.visits == 1
    assert child.value == 0.5
    assert root.visits == 1
    assert root.value == 0.5


def test_mcts_search_returns_legal_action():
    state = _advance_to_mandatory(new_game(0))
    obs = observation(state, 0)
    det_state = determinize(obs, random.Random(0))
    action = mcts_search(det_state, random.Random(0), max_playouts=100)
    # Action must be legal in the original state
    dp = decide(state)
    assert action in dp.legal_actions


def test_mcts_search_deterministic_with_same_seed():
    state = _advance_to_mandatory(new_game(0))
    obs = observation(state, 0)
    det = determinize(obs, random.Random(0))
    a1 = mcts_search(det, random.Random(42), max_playouts=200)
    a2 = mcts_search(det, random.Random(42), max_playouts=200)
    assert a1 == a2


def test_mcts_search_handles_terminal_state():
    # If the root is already terminal, search should raise an error (not a valid use case)
    state = _advance_to_mandatory(new_game(0))
    terminal_state = replace(state, winner=0)
    try:
        mcts_search(terminal_state, random.Random(0), max_playouts=10)
        assert False, "Expected ValueError for terminal state"
    except ValueError as e:
        assert "terminal" in str(e).lower()


def test_mcts_search_with_greedy_policy():
    state = _advance_to_mandatory(new_game(0))
    obs = observation(state, 0)
    det_state = determinize(obs, random.Random(0))
    action = mcts_search(
        det_state, random.Random(0), max_playouts=50, playout_policy="greedy"
    )
    dp = decide(state)
    assert action in dp.legal_actions


def test_mcts_node_is_terminal():
    state = _advance_to_mandatory(new_game(0))
    node = MCTSNode(state=state, parent=None, action=None)
    assert not node.is_terminal()

    terminal_state = replace(state, winner=0)
    terminal_node = MCTSNode(state=terminal_state, parent=None, action=None)
    assert terminal_node.is_terminal()


def test_mcts_node_is_fully_expanded():
    state = _advance_to_mandatory(new_game(0))
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
    state = new_game(0)
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


def test_playout_from_near_terminal_state():
    """Playout from a state one move from game end should terminate quickly with correct winner.

    This test verifies that playout actually continues from the given state
    (not from a fresh game) and correctly identifies the winner.
    """
    from dataclasses import replace as dc_replace

    from splendor_duel_engine.engine.state import Phase, PlayerState, Tokens

    # Create a near-terminal state: player 0 has 19 prestige and can buy a 1-point card
    jewels, _royals = load_cards()

    # Find a cheap 1-point card to use as the winning purchase
    cheap_card = None
    for card in jewels:
        if card.points == 1 and card.level == 1:
            cheap_card = card
            break
    assert cheap_card is not None, "Need a level 1, 1-point card for test"

    # Build a minimal state where player 0 is about to win
    # Player 0 has 19 prestige, the cheap card is in the pyramid, and they can afford it
    base_state = new_game(0)

    # Advance to MANDATORY phase
    state = replace(base_state, phase=Phase.USE_PRIVILEGES)
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    assert state.phase == Phase.MANDATORY

    # Place the cheap card in the pyramid at a known position
    pyramid = [list(row) for row in state.pyramid]
    # Put the cheap card at pyramid[2][0] (level 1, first slot)
    pyramid[2][0] = cheap_card
    new_pyramid = tuple(tuple(row) for row in pyramid)

    # Give player 0 19 prestige and enough tokens to buy the cheap card
    # Cheap card costs should be affordable - give them the exact tokens needed
    cost = cheap_card.cost
    tokens = Tokens(
        white=cost.white,
        blue=cost.blue,
        green=cost.green,
        red=cost.red,
        black=cost.black,
        pearl=cost.pearl,
        gold=0,
    )
    # Bonuses don't matter since we give exact cost
    player0 = PlayerState(
        tokens=tokens,
        bonus=Tokens(),
        prestige=19,
        crowns=0,
        reserved=(),
        purchased=(),
        privileges=0,
    )
    player1 = PlayerState(
        tokens=Tokens(),
        bonus=Tokens(),
        prestige=0,
        crowns=0,
        reserved=(),
        purchased=(),
        privileges=0,
    )

    near_end_state = dc_replace(
        state,
        players=(player0, player1),
        pyramid=new_pyramid,
        current_player=0,
        phase=Phase.MANDATORY,
    )

    # Verify the state is set up correctly
    dp = decide(near_end_state)
    buy_actions = [
        a for a in dp.legal_actions if hasattr(a, "card") and a.card.id == cheap_card.id
    ]
    assert buy_actions, f"Cheap card {cheap_card.id} should be buyable"

    # Run playout with greedy policy from this state
    # Player 0 should win immediately by buying the card
    result = playout(near_end_state, random.Random(42), playout_policy="greedy")

    # From player 0's perspective (current player), result should be 1.0 (win)
    assert result == 1.0, f"Expected win (1.0) for current player, got {result}"


def test_heuristic_evaluation_returns_valid_range():
    """Test that _heuristic_evaluation returns a value in [0, 1]."""
    state = _advance_to_mandatory(new_game(0))
    # Test from both perspectives
    for perspective in (0, 1):
        value = _heuristic_evaluation(state, perspective)
        assert 0.0 <= value <= 1.0, (
            f"Heuristic value {value} not in [0, 1] for perspective {perspective}"
        )


def test_heuristic_evaluation_symmetric():
    """Test that heuristic evaluation is symmetric (v1 = 1 - v2 for zero-sum)."""
    state = _advance_to_mandatory(new_game(0))
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
    from splendor_duel_engine.engine.state import PlayerState, Tokens

    # Create a state where player 0 is clearly winning
    base_state = _advance_to_mandatory(new_game(0))

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


def test_playout_respects_max_depth():
    """Test that playout respects the max_depth parameter."""
    state = _advance_to_mandatory(new_game(0))

    # With max_depth=0, should immediately return heuristic evaluation
    result_depth0 = playout(
        state, random.Random(0), playout_policy="random", max_depth=0
    )
    # Should be the heuristic value (around 0.5 for initial state)
    assert 0.4 <= result_depth0 <= 0.6

    # With max_depth=1, should make one ply then evaluate
    result_depth1 = playout(
        state, random.Random(0), playout_policy="random", max_depth=1
    )
    assert 0.0 <= result_depth1 <= 1.0

    # With larger max_depth, should still return valid result
    result_depth10 = playout(
        state, random.Random(0), playout_policy="random", max_depth=10
    )
    assert 0.0 <= result_depth10 <= 1.0


def test_playout_limited_depth_vs_full():
    """Test that limited-depth playout gives reasonable results compared to full playout.

    Note: We can't easily test "full playout" since the old implementation used
    play_game_from_state. This test verifies that limited-depth playout produces
    valid results and terminates quickly.
    """
    state = _advance_to_mandatory(new_game(0))

    # Run several limited-depth playouts
    results = []
    for i in range(10):
        result = playout(state, random.Random(i), playout_policy="random", max_depth=5)
        results.append(result)
        assert 0.0 <= result <= 1.0

    # All results should be valid
    assert len(results) == 10


def test_mcts_search_with_max_depth():
    """Test that mcts_search accepts and uses the max_depth parameter."""
    state = _advance_to_mandatory(new_game(0))
    obs = observation(state, 0)
    det_state = determinize(obs, random.Random(0))

    # Should work with default max_depth
    action1 = mcts_search(det_state, random.Random(0), max_playouts=20)
    dp = decide(state)
    assert action1 in dp.legal_actions

    # Should work with custom max_depth
    action2 = mcts_search(det_state, random.Random(0), max_playouts=20, max_depth=5)
    assert action2 in dp.legal_actions

    # Should work with max_depth=0 (pure heuristic)
    action3 = mcts_search(det_state, random.Random(0), max_playouts=20, max_depth=0)
    assert action3 in dp.legal_actions


def test_color_prestige_computation():
    """Test that PlayerState.color_prestige correctly computes color prestige."""
    from splendor_duel_engine.engine.cards import Card
    from splendor_duel_engine.engine.state import PurchasedCard

    # Create a player with some purchased cards
    player = PlayerState(
        tokens=Tokens(),
        bonus=Tokens(),
        prestige=10,
        crowns=2,
        reserved=(),
        purchased=(
            PurchasedCard(
                card=Card(
                    id="WHITE-1",
                    level=1,
                    points=2,
                    crowns=1,
                    bonus=Color.WHITE,
                    bonus_count=1,
                    ability=None,
                    is_multicolor=False,
                    cost=Tokens(),
                ),
                chosen_color=None,
            ),
            PurchasedCard(
                card=Card(
                    id="WHITE-2",
                    level=2,
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
            PurchasedCard(
                card=Card(
                    id="BLUE-1",
                    level=1,
                    points=1,
                    crowns=0,
                    bonus=Color.BLUE,
                    bonus_count=1,
                    ability=None,
                    is_multicolor=False,
                    cost=Tokens(),
                ),
                chosen_color=None,
            ),
        ),
        privileges=0,
    )

    # White prestige: (2 points + 1 bonus) + (3 points + 2 bonus) = 8
    assert player.color_prestige(Color.WHITE) == 8
    # Blue prestige: 1 point + 1 bonus = 2
    assert player.color_prestige(Color.BLUE) == 2
    # Other colors: 0
    assert player.color_prestige(Color.GREEN) == 0
    assert player.color_prestige(Color.RED) == 0
    assert player.color_prestige(Color.BLACK) == 0


def test_color_prestige_multicolor():
    """Test that multicolor cards use chosen_color for color prestige."""
    from splendor_duel_engine.engine.cards import Card
    from splendor_duel_engine.engine.state import PurchasedCard

    player = PlayerState(
        tokens=Tokens(),
        bonus=Tokens(),
        prestige=5,
        crowns=1,
        reserved=(),
        purchased=(
            PurchasedCard(
                card=Card(
                    id="MULTI-1",
                    level=2,
                    points=4,
                    crowns=1,
                    bonus=None,
                    bonus_count=2,
                    ability=None,
                    is_multicolor=True,
                    cost=Tokens(),
                ),
                chosen_color=Color.RED,  # Player chose RED
            ),
        ),
        privileges=0,
    )

    # Multicolor card with chosen_color=RED should count toward RED
    # Points (4) + bonus_count (2) = 6
    assert player.color_prestige(Color.RED) == 6
    assert player.color_prestige(Color.WHITE) == 0
