"""Colors and token counts for Splendor Duel.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup" (25 tokens:
4 each of the five gems, 2 pearls, 3 gold).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Color(Enum):
    """A token and bonus color; values match the keys in ``cards.json``."""

    WHITE = "white"
    BLUE = "blue"
    GREEN = "green"
    RED = "red"
    BLACK = "black"
    PEARL = "pearl"
    GOLD = "gold"


GEM_COLORS: tuple[Color, ...] = (
    Color.WHITE,
    Color.BLUE,
    Color.GREEN,
    Color.RED,
    Color.BLACK,
)
PAY_COLORS: tuple[Color, ...] = GEM_COLORS + (Color.PEARL,)
ALL_COLORS: tuple[Color, ...] = PAY_COLORS + (Color.GOLD,)


@dataclass(frozen=True, slots=True)
class Tokens:
    """An immutable, hashable count of tokens, one field per color."""

    white: int = 0
    blue: int = 0
    green: int = 0
    red: int = 0
    black: int = 0
    pearl: int = 0
    gold: int = 0
