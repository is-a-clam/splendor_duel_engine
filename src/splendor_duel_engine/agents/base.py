"""Agent protocol and shared game-running helpers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from splendor_duel_engine.engine.actions import (
    Action,
    BuyCard,
    ReserveCard,
    TakeTokens,
    apply,
    decide,
)
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


def play_game(
    agent0: Agent,
    agent1: Agent,
    seed: int,
    max_turns: int | None = 400,
) -> GameState:
    """Play a full game between two agents and return the final state.

    The game is deterministic given ``seed`` and the agents' choices.

    Args:
        agent0: Agent for player 0.
        agent1: Agent for player 1.
        seed: Seed for the game's RNG (board setup, deck shuffle, etc.).
        max_turns: Maximum number of main actions (BuyCard, TakeTokens, ReserveCard)
            before raising. Default 400. Set to ``None`` to disable the cap.

    Returns:
        The final ``GameState`` with ``winner`` and ``phase == GAME_OVER`` set.

    Raises:
        RuntimeError: If ``max_turns`` is exceeded before the game ends.
    """
    state = new_game(seed)
    agents = (agent0, agent1)
    turn_count = 0
    while state.winner is None:
        player = state.current_player
        obs = observation(state, player)
        dp = decide(state)
        action = agents[player].choose_action(obs, dp.legal_actions)
        state = apply(state, action)

        # Count main actions (turns) — these are the three action types that
        # advance the game meaningfully. Sub-decisions (payment, privilege use,
        # etc.) are not counted as separate turns.
        if isinstance(action, (TakeTokens, BuyCard, ReserveCard)):
            turn_count += 1
            if max_turns is not None and turn_count > max_turns:
                raise RuntimeError(
                    f"Game exceeded max_turns={max_turns} at turn {turn_count} "
                    f"(seed={seed}). Agents may be cycling."
                )
    return state
