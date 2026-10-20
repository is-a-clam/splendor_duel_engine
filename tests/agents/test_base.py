"""Tests for the Agent protocol and play_game helper (Task 1)."""

from splendor_duel_engine.agents.base import Agent, play_game


def test_agent_protocol_exists():
    # Just verify the protocol can be imported and used for type checking
    class DummyAgent:
        def choose_action(self, obs, legal_actions):
            return legal_actions[0]

    assert isinstance(DummyAgent(), Agent)


def test_play_game_runs_to_completion():
    class FirstLegalAgent:
        def choose_action(self, obs, legal_actions):
            return legal_actions[0]

    final = play_game(FirstLegalAgent(), FirstLegalAgent(), seed=0)
    assert final.winner in (0, 1)
    assert final.phase.name == "GAME_OVER"


def test_play_game_raises_when_turn_cap_exceeded():
    import pytest

    from splendor_duel_engine.agents.random_agent import RandomAgent

    # Any real game needs more than one main action, so a cap of 1 always trips.
    with pytest.raises(RuntimeError, match="turn"):
        play_game(RandomAgent(seed=1), RandomAgent(seed=2), seed=0, max_turns=1)


def test_play_game_max_turns_none_disables_cap():
    from splendor_duel_engine.agents.random_agent import RandomAgent

    final = play_game(RandomAgent(seed=1), RandomAgent(seed=2), seed=0, max_turns=None)
    assert final.winner in (0, 1)
