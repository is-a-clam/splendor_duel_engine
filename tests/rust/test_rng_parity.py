"""Parity between the Rust RNG and CPython's ``random.Random``.

The engine's games must be reproducible across both engines, so the Rust RNG
must be bit-identical to CPython's MT19937 — not merely statistically similar.
"""

from __future__ import annotations

import random

import pytest

from splendor_duel_engine._core import Random

# Deliberately includes a negative seed, a seed that does not fit in 32 bits,
# and a seed that is exactly 2**32.
SEEDS = [0, 1, 7, 42, 2**31, 2**32, 2**32 + 1, 2**63 - 1, 987654321012345678, -42]


@pytest.mark.parametrize("seed", SEEDS)
def test_first_32_bit_output_matches(seed: int) -> None:
    assert Random(seed).getrandbits(32) == random.Random(seed).getrandbits(32)


@pytest.mark.parametrize("seed", SEEDS)
def test_negative_seed_matches_its_absolute_value(seed: int) -> None:
    assert Random(seed).getrandbits(32) == Random(abs(seed)).getrandbits(32)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_long_run_of_outputs_matches(seed: int) -> None:
    rust = Random(seed)
    py = random.Random(seed)
    for _ in range(200):
        assert rust.getrandbits(32) == py.getrandbits(32)


@pytest.mark.parametrize("seed", SEEDS)
def test_getrandbits_below_32_bits_matches(seed: int) -> None:
    rust = Random(seed)
    py = random.Random(seed)
    for k in (1, 2, 3, 8, 16, 31, 32):
        assert rust.getrandbits(k) == py.getrandbits(k)


@pytest.mark.parametrize("seed", SEEDS)
def test_randbelow_matches(seed: int) -> None:
    rust = Random(seed)
    py = random.Random(seed)
    for n in (2, 3, 7, 25, 64, 2**31):
        assert rust.randbelow(n) == py._randbelow(n)


@pytest.mark.parametrize("seed", SEEDS)
def test_randrange_matches(seed: int) -> None:
    rust = Random(seed)
    py = random.Random(seed)
    for _ in range(50):
        assert rust.randrange(2) == py.randrange(2)


@pytest.mark.parametrize("seed", SEEDS)
def test_shuffle_matches(seed: int) -> None:
    rust_items = list(range(25))
    py_items = list(range(25))
    Random(seed).shuffle(rust_items)
    random.Random(seed).shuffle(py_items)
    assert rust_items == py_items


def test_copy_continues_the_same_stream_independently() -> None:
    rng = Random(42)
    for _ in range(10):
        rng.getrandbits(32)
    clone = rng.copy()
    assert clone.getrandbits(32) == rng.getrandbits(32)


def test_randbelow_zero_raises() -> None:
    """CPython's randrange(0) raises ValueError; our randbelow mirrors this."""
    with pytest.raises(ValueError, match="empty range"):
        Random(42).randbelow(0)
    with pytest.raises(ValueError, match="empty range"):
        random.Random(42).randrange(0)