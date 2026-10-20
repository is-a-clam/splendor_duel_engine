"""Agent protocol and shared game-running helpers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from splendor_duel_engine.engine.actions import Action, apply, decide
from splendor_duel_engine.engine.observation import Observation, observation
from splendor_duel_engine.engine.state import GameState, new_game


@runtime_checkable
class Agent(Protocol):
    """An agent chooses one action from the legal actions it is offered.

    Agents see only :class:`Observation` (hidden information excluded) and must
    return an action taken verbatim from ``legal_actions``.
    """

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action: ...


def play_game(agent0: Agent, agent1: Agent, seed: int) -> GameState:
    """Play a full game between two agents and return the final state.

    The game is deterministic given ``seed`` and the agents' choices.
    """
    state = new_game(seed)
    agents = (agent0, agent1)
    while state.winner is None:
        player = state.current_player
        obs = observation(state, player)
        dp = decide(state)
        action = agents[player].choose_action(obs, dp.legal_actions)
        state = apply(state, action)
    return state
