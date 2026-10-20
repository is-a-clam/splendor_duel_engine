"""Tests for the MCTS agent implementing the Agent protocol."""

from __future__ import annotations

from splendor_duel_engine.agents.mcts_agent import MCTSAgent
from splendor_duel_engine.engine.actions import decide
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.state import new_game


def test_mcts_agent_chooses_legal_action():
    agent = MCTSAgent(seed=42, max_playouts=100)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_mcts_agent_deterministic_with_same_seed():
    agent1 = MCTSAgent(seed=123, max_playouts=200)
    agent2 = MCTSAgent(seed=123, max_playouts=200)
    state = new_game(0)
    obs = observation(state, state.current_player)
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

    state = new_game(0)
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    assert state.phase == Phase.MANDATORY
    obs = observation(state, state.current_player)
    dp = decide(state)
    a1 = agent1.choose_action(obs, dp.legal_actions)
    a2 = agent2.choose_action(obs, dp.legal_actions)
    # Very likely different with >1 legal action
    assert a1 != a2


def test_mcts_agent_full_game_terminates():
    from splendor_duel_engine.agents.base import play_game

    final = play_game(
        MCTSAgent(seed=1, max_playouts=20), MCTSAgent(seed=2, max_playouts=20), seed=999
    )
    assert final.winner in (0, 1)


def test_mcts_agent_respects_max_playouts():
    # With very low playouts, should still return a legal action
    agent = MCTSAgent(seed=0, max_playouts=10)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_mcts_agent_random_playout_policy():
    agent = MCTSAgent(seed=42, max_playouts=100, playout_policy="random")
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_mcts_agent_re_determinizes_each_decision():
    # Two calls with same Observation but different internal RNG state
    # should produce different determinizations and potentially different actions
    agent = MCTSAgent(seed=0, max_playouts=200)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    actions = [agent.choose_action(obs, dp.legal_actions) for _ in range(5)]
    # Should not be all identical (different determinizations each call)
    assert len(set(actions)) > 1 or len(dp.legal_actions) == 1


def test_mcts_agent_invalid_max_playouts():
    # max_playouts must be >= 1
    try:
        MCTSAgent(seed=0, max_playouts=0)
        assert False, "Expected ValueError for max_playouts < 1"
    except ValueError as e:
        assert "max_playouts" in str(e).lower()


def test_mcts_agent_invalid_playout_policy():
    # playout_policy must be 'greedy' or 'random'
    try:
        MCTSAgent(seed=0, playout_policy="invalid")
        assert False, "Expected ValueError for invalid playout_policy"
    except ValueError as e:
        assert "playout_policy" in str(e).lower()
