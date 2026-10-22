"""Parity of the initial setup between the two engines."""

from __future__ import annotations

import pytest
from splendor_duel_engine._core import new_game as rust_new_game

from splendor_duel_engine.engine.state import new_game as py_new_game
from tests.rust.parity import state_fingerprint

SEEDS = [0, 1, 7, 42, 1234, 2**31, 2**63 - 1]


@pytest.mark.parametrize("seed", SEEDS)
def test_setup_matches(seed: int) -> None:
    assert state_fingerprint(rust_new_game(seed)) == state_fingerprint(
        py_new_game(seed)
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_setup_is_reproducible(seed: int) -> None:
    assert state_fingerprint(rust_new_game(seed)) == state_fingerprint(
        rust_new_game(seed)
    )
