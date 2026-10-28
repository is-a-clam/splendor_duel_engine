"""Parity of the field constructor and observations between the two engines."""

from __future__ import annotations

import pytest
from splendor_duel_engine._core import GameState as RustGameState
from splendor_duel_engine._core import GameState as RustGameState
from splendor_duel_engine._core import observation as rust_observation

from splendor_duel_engine.engine.observation import get_observation as py_observation
from splendor_duel_engine.engine.state import GameState as PyGameState
from tests.engine_rs.parity import observation_fingerprint, state_fingerprint

SEEDS = [0, 7, 42, 1234, 2**63 - 1]


@pytest.mark.parametrize("seed", SEEDS)
def test_field_constructor_round_trip(seed: int) -> None:
    state = RustGameState.new_game(seed)
    rebuilt = RustGameState(
        players=state.players,
        board=state.board,
        bag=state.bag,
        decks=state.decks,
        pyramid=state.pyramid,
        royals_available=state.royals_available,
        privileges_supply=state.privileges_supply,
        current_player=state.current_player,
        winner=state.winner,
        phase=state.phase,
        pending_buy=state.pending_buy,
        pending_reserve=state.pending_reserve,
        seed=seed,
        extra_turn=state.extra_turn,
        pending_ability=state.pending_ability,
        pending_royal=state.pending_royal,
    )
    assert state_fingerprint(rebuilt) == state_fingerprint(state)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("player", [0, 1])
def test_observation_matches(seed: int, player: int) -> None:
    rust_obs = rust_observation(RustGameState.new_game(seed), player)
    py_obs = py_observation(PyGameState.new_game(seed), player)
    assert observation_fingerprint(rust_obs) == observation_fingerprint(py_obs)
