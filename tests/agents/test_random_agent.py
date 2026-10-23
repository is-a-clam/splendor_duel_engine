"""Tests for the random baseline agent (Task 2)."""

from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.engine.actions import (
    DoneWithPrivileges,
    DoneWithReplenish,
    apply,
    decide,
)
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState


def _opening_mandatory_decision():
    """Return the opening MANDATORY decision, which offers many legal actions."""
    state = GameState.new_game(0)
    state = apply(state, DoneWithPrivileges())
    if state.phase == Phase.REPLENISH:
        state = apply(state, DoneWithReplenish())
    assert state.phase == Phase.MANDATORY
    obs = observation(state, state.current_player)
    dp = decide(state)
    assert len(dp.legal_actions) > 1
    return obs, dp.legal_actions


def test_random_agent_chooses_legal_action():
    agent = RandomAgent(seed=42)
    state = GameState.new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_random_agent_deterministic_with_same_seed():
    agent1 = RandomAgent(seed=123)
    agent2 = RandomAgent(seed=123)
    obs, legal_actions = _opening_mandatory_decision()
    # Both agents should make the same choices given the same RNG state.
    choices1 = [agent1.choose_action(obs, legal_actions) for _ in range(10)]
    choices2 = [agent2.choose_action(obs, legal_actions) for _ in range(10)]
    assert choices1 == choices2


def test_random_agent_different_seeds_different_choices():
    agent1 = RandomAgent(seed=1)
    agent2 = RandomAgent(seed=2)
    obs, legal_actions = _opening_mandatory_decision()
    # Very likely different (not guaranteed but extremely likely with >1 action)
    choices1 = [agent1.choose_action(obs, legal_actions) for _ in range(10)]
    choices2 = [agent2.choose_action(obs, legal_actions) for _ in range(10)]
    assert choices1 != choices2  # different sequences


def test_random_agent_full_game_terminates():
    final = play_game(RandomAgent(seed=1), RandomAgent(seed=2), seed=999)
    assert final.winner in (0, 1)
