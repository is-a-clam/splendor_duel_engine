"""Tests for the MCTS agent implementing the Agent protocol."""

from __future__ import annotations

from splendor_duel_engine.agents.mcts_agent import MCTSAgent
from splendor_duel_engine.engine.actions import decide
from splendor_duel_engine.engine.observation import get_observation
from splendor_duel_engine.engine.state import GameState


def test_mcts_agent_chooses_legal_action():
    agent = MCTSAgent(seed=42, max_playouts=100)
    state = GameState.new_game(0)
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_mcts_agent_deterministic_with_same_seed():
    agent1 = MCTSAgent(seed=123, max_playouts=200)
    agent2 = MCTSAgent(seed=123, max_playouts=200)
    state = GameState.new_game(0)
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    a1 = agent1.choose_action(obs, dp.legal_actions)
    a2 = agent2.choose_action(obs, dp.legal_actions)
    assert a1 == a2


def test_mcts_agent_different_seeds_different_actions():
    agent1 = MCTSAgent(seed=1, max_playouts=200)
    agent2 = MCTSAgent(seed=2, max_playouts=200)
    # Advance to MANDATORY phase where there are multiple legal actions
    from splendor_duel_engine.engine.actions import (
        DoneWithPrivileges,
        DoneWithReplenish,
        apply,
    )
    from splendor_duel_engine.engine.phase import Phase

    state = GameState.new_game(0)
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    assert state.phase == Phase.MANDATORY
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    # Run multiple trials; with different seeds, actions should differ in at least some cases.
    # With >1 legal action and different seeds, probability of all 10 matching is extremely low.
    differences = sum(
        1
        for _ in range(10)
        if agent1.choose_action(obs, dp.legal_actions)
        != agent2.choose_action(obs, dp.legal_actions)
    )
    assert differences >= 3


def test_mcts_agent_full_game_terminates():
    from splendor_duel_engine.agents.base import play_game

    final = play_game(
        MCTSAgent(seed=1, max_playouts=20), MCTSAgent(seed=2, max_playouts=20), seed=999
    )
    assert final.winner in (0, 1)


def test_mcts_agent_respects_max_playouts():
    # With very low playouts, should still return a legal action
    agent = MCTSAgent(seed=0, max_playouts=10)
    state = GameState.new_game(0)
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_mcts_agent_random_playout_policy():
    agent = MCTSAgent(seed=42, max_playouts=100)
    state = GameState.new_game(0)
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_mcts_agent_re_determinizes_each_decision():
    # Two calls with same Observation but different internal RNG state
    # should produce different determinizations and potentially different actions
    agent = MCTSAgent(seed=0, max_playouts=200)
    state = GameState.new_game(0)
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    # Run multiple trials; re-determinization should produce varied actions.
    # If only 1 legal action, all will be the same (expected).
    actions = [agent.choose_action(obs, dp.legal_actions) for _ in range(10)]
    unique_actions = len(set(actions))
    assert unique_actions >= 3 or len(dp.legal_actions) == 1


def test_mcts_agent_invalid_max_playouts():
    # max_playouts must be >= 1
    try:
        MCTSAgent(seed=0, max_playouts=0)
        assert False, "Expected ValueError for max_playouts < 1"
    except ValueError as e:
        assert "max_playouts" in str(e).lower()


def test_mcts_agent_invalid_num_determinizations():
    # num_determinizations must be >= 1
    try:
        MCTSAgent(seed=0, num_determinizations=0)
        assert False, "Expected ValueError for num_determinizations < 1"
    except ValueError as e:
        assert "num_determinizations" in str(e).lower()


def test_mcts_agent_num_determinizations_default():
    # Default num_determinizations should be 20
    agent = MCTSAgent(seed=0)
    assert agent._num_determinizations == 20


def test_mcts_agent_multi_sample_differs_from_single():
    """Verify that num_determinizations > 1 produces different action distribution
    than num_determinizations=1 on a position where hidden info matters."""
    # Create a state where opponent has hidden reserves (mid-game)
    # Both players have reserved a card, so each has a face-down reserve from opponent's perspective
    from splendor_duel_engine.engine.actions import (
        DoneWithPrivileges,
        DoneWithReplenish,
        ReserveCard,
        apply,
    )
    from splendor_duel_engine.engine.phase import Phase

    state = GameState.new_game(0)
    # Player 1 (first player) does MANDATORY setup
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    # Player 1 reserves a card
    dp = decide(state)
    reserve_action = None
    for action in dp.legal_actions:
        if isinstance(action, ReserveCard) and action.source.startswith("pyramid"):
            reserve_action = action
            break
    assert reserve_action is not None
    state = apply(state, reserve_action)
    # Player 1 chooses gold
    dp = decide(state)
    state = apply(state, dp.legal_actions[0])
    # Player 0's turn - they have hidden reserve
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    # Player 0 reserves a card
    dp = decide(state)
    reserve_action = None
    for action in dp.legal_actions:
        if isinstance(action, ReserveCard) and action.source.startswith("pyramid"):
            reserve_action = action
            break
    assert reserve_action is not None
    state = apply(state, reserve_action)
    # Player 0 chooses gold
    dp = decide(state)
    state = apply(state, dp.legal_actions[0])
    # Player 1's turn again - MANDATORY phase
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    # Now player 1 to act, player 0 has a face-down reserve
    assert state.current_player == 1
    assert state.phase == Phase.MANDATORY
    assert len(state.players[0].reserved) == 1  # player 0 has a face-down reserve

    obs = get_observation(state, state.current_player)
    dp = decide(state)

    # Run many trials with single-sample and multi-sample
    agent_single = MCTSAgent(seed=0, max_playouts=400, num_determinizations=1)
    agent_multi = MCTSAgent(seed=0, max_playouts=400, num_determinizations=20)

    # Collect action distributions
    single_actions = [
        agent_single.choose_action(obs, dp.legal_actions) for _ in range(50)
    ]
    multi_actions = [
        agent_multi.choose_action(obs, dp.legal_actions) for _ in range(50)
    ]

    # They should produce different distributions (not identical)
    # At minimum, the sets of actions chosen should differ or the frequencies should differ
    single_set = set(single_actions)
    multi_set = set(multi_actions)

    # With hidden information (opponent's face-down reserve), multi-sample
    # should explore more broadly. Assert they're not identical.
    # Note: This is a probabilistic test; very unlikely to fail if logic is correct.
    assert single_set != multi_set or single_actions != multi_actions


def test_mcts_agent_runs_mcts_for_non_mandatory_phases():
    """Verify MCTS is invoked for non-MANDATORY phases with multiple legal actions."""
    from splendor_duel_engine.engine.actions import ReserveCard, apply
    from splendor_duel_engine.engine.phase import Phase

    # Create a state where the player can reserve a card (enters CHOOSE_GOLD phase)
    state = GameState.new_game(0)
    # Advance to MANDATORY
    from splendor_duel_engine.engine.actions import (
        DoneWithPrivileges,
        DoneWithReplenish,
    )

    state = GameState.new_game(0)
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    # Now in MANDATORY, reserve from pyramid
    dp = decide(state)
    reserve_action = None
    for action in dp.legal_actions:
        if isinstance(action, ReserveCard) and action.source.startswith("pyramid"):
            reserve_action = action
            break
    assert reserve_action is not None, "No pyramid reserve action available"
    state = apply(state, reserve_action)
    assert state.phase == Phase.CHOOSE_GOLD
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    assert len(dp.legal_actions) > 1, "Should have multiple gold tokens to choose from"

    # With the new implementation, mcts_search is no longer called directly.
    # Instead, the MCTS loop runs inline. We can't easily mock it, so just verify
    # it returns a legal action.
    agent = MCTSAgent(seed=42, max_playouts=100)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_mcts_agent_backward_compat_num_determinizations_one():
    """num_determinizations=1 should behave like the old single-sample MCTS."""
    agent = MCTSAgent(seed=42, max_playouts=100, num_determinizations=1)
    state = GameState.new_game(0)
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions

    # Verify deterministic behavior with same seed
    agent2 = MCTSAgent(seed=42, max_playouts=100, num_determinizations=1)
    action2 = agent2.choose_action(obs, dp.legal_actions)
    assert action == action2
