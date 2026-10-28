"""The cross-engine parity harness.

Both engines are driven from the same seed with the same action sequence, and
the state is compared after every single move. Any divergence shows up at the
first move that differs.
"""

from __future__ import annotations

import pytest
from splendor_duel_engine._core import apply as rust_apply
from splendor_duel_engine._core import decide as rust_decide
from splendor_duel_engine._core import GameState as RustGameState
from splendor_duel_engine._core import observation as rust_observation

from splendor_duel_engine.engine.actions import apply as py_apply
from splendor_duel_engine.engine.actions import decide as py_decide
from splendor_duel_engine.engine.observation import get_observation as py_observation
from splendor_duel_engine.engine.state import GameState as PyGameState
from tests.engine_rs.parity import (
    action_fingerprint,
    observation_fingerprint,
    state_fingerprint,
)

SEEDS = [0, 1, 7, 42, 1234]


def _drive(seed: int, moves: int) -> None:
    rust_state = RustGameState.new_game(seed)
    py_state = PyGameState.new_game(seed)

    for move in range(moves):
        # Both engines raise ``ValueError("game is over")`` from ``decide`` once
        # there is a winner, so stop there. The winner itself is compared so the
        # final position is still checked.
        assert (rust_state.winner is None) == (py_state.winner is None), (
            f"winner presence differs at move {move}"
        )
        if rust_state.winner is not None:
            assert rust_state.winner == py_state.winner, (
                f"winner differs at move {move}"
            )
            break

        rust_dp = rust_decide(rust_state)
        py_dp = py_decide(py_state)

        assert rust_dp.phase.value == py_dp.phase.value, f"phase differs at move {move}"
        assert [action_fingerprint(a) for a in rust_dp.legal_actions] == [
            action_fingerprint(a) for a in py_dp.legal_actions
        ], f"legal actions differ at move {move}"

        if not rust_dp.legal_actions:
            break

        # Always take the first legal action: deterministic, and it walks the
        # game through every phase.
        rust_state = rust_apply(rust_state, rust_dp.legal_actions[0])
        py_state = py_apply(py_state, py_dp.legal_actions[0])

        assert state_fingerprint(rust_state) == state_fingerprint(py_state), (
            f"state differs after move {move}"
        )

        for player in (0, 1):
            assert observation_fingerprint(rust_observation(rust_state, player)) == (
                observation_fingerprint(py_observation(py_state, player))
            ), f"observation differs after move {move} for player {player}"


@pytest.mark.parametrize("seed", SEEDS)
def test_first_forty_moves_match(seed: int) -> None:
    _drive(seed, 40)


@pytest.mark.parametrize("seed", SEEDS)
def test_long_game_matches(seed: int) -> None:
    _drive(seed, 400)
