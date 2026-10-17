"""Static geometry of the 5x5 token board.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup". The 25 board
spaces fill in a printed spiral; ``SPIRAL[i]`` is the board index (row-major,
0..24) of the i-th token dealt at setup, so ``SPIRAL[0]`` is the centre.
"""

from __future__ import annotations

#: Row-major board indices in spiral order, centre first.
SPIRAL: tuple[int, ...] = (
    12,
    7,
    8,
    13,
    18,
    17,
    16,
    11,
    6,
    1,
    2,
    3,
    4,
    9,
    14,
    19,
    24,
    23,
    22,
    21,
    20,
    15,
    10,
    5,
    0,
)
