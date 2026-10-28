"""Agent protocol and shared game-running helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar, runtime_checkable

from splendor_duel_engine.engine_api import (
    Action,
    BuyCard,
    GameState,
    Observation,
    ReserveCard,
    TakeTokens,
    apply,
    decide,
    get_observation,
)

A = TypeVar("A")


@runtime_checkable
class Agent(Protocol):
    """An agent chooses one action from the legal actions it is offered.

    Agents see only :class:`Observation` (hidden information excluded) and must
    return an action taken verbatim from ``legal_actions``.
    """

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action: ...


def first_of(actions: Iterable[A], kind: type[A]) -> A | None:
    """Return the first action of type ``kind``, or ``None`` if there is none."""
    for action in actions:
        if isinstance(action, kind):
            return action
    return None


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
    state = GameState.new_game(seed)
    return play_game_from_state(state, agent0, agent1, max_turns)


def play_game_from_state(
    state: GameState,
    agent0: Agent,
    agent1: Agent,
    max_turns: int | None = 400,
) -> GameState:
    """Continue a game from the given state using the state's RNG for game-internal randomness.

    The agents' internal RNGs (if any) are used for their decisions. The state's RNG
    is used for engine-internal randomness (replenish draws, deck draws if needed, etc.).
    The ``apply`` function deep-copies the state's RNG before mutating it, ensuring
    deterministic playout branches.

    Args:
        state: The game state to continue from. Must not be terminal.
        agent0: Agent for player 0.
        agent1: Agent for player 1.
        max_turns: Maximum number of main actions (BuyCard, TakeTokens, ReserveCard)
            before raising. Default 400. Set to ``None`` to disable the cap.

    Returns:
        The final ``GameState`` with ``winner`` and ``phase == GAME_OVER`` set.

    Raises:
        ValueError: If the given state is already terminal.
        RuntimeError: If ``max_turns`` is exceeded before the game ends.
    """
    if state.winner is not None:
        raise ValueError("Cannot continue from terminal state")

    agents = (agent0, agent1)
    turn_count = 0
    while state.winner is None:
        player = state.current_player
        obs = get_observation(state, player)
        dp = decide(state)
        action = agents[player].choose_action(obs, dp.legal_actions)
        state = apply(state, action)

        # Count main actions (turns) — these are the three action types that
        # advance the game meaningfully. Sub-decision (payment, privilege use,
        # etc.) are not counted as separate turns.
        if isinstance(action, (TakeTokens, BuyCard, ReserveCard)):
            turn_count += 1
            if max_turns is not None and turn_count > max_turns:
                raise RuntimeError(
                    f"Game exceeded max_turns={max_turns} at turn {turn_count} "
                    f"from given state. Agents may be cycling."
                )
    return state
