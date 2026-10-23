"""Parity of the legal-action mask between the two engines."""

from __future__ import annotations

import pytest
from splendor_duel_engine._core import decide as rust_decide
from splendor_duel_engine._core import GameState as RustGameState

from splendor_duel_engine.engine.actions import decide as py_decide
from splendor_duel_engine.engine.state import GameState as PyGameState
from tests.engine_rs.parity import action_fingerprint

SEEDS = [0, 1, 7, 42, 1234]


@pytest.mark.parametrize("seed", SEEDS)
def test_initial_decision_matches(seed: int) -> None:
    rust_dp = rust_decide(RustGameState.new_game(seed))
    py_dp = py_decide(PyGameState.new_game(seed))
    assert rust_dp.phase.value == py_dp.phase.value
    assert [action_fingerprint(a) for a in rust_dp.legal_actions] == [
        action_fingerprint(a) for a in py_dp.legal_actions
    ]
