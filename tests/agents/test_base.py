from splendor_duel_engine.engine.actions import decide
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.engine.observation import observation
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
