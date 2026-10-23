"""Colors and token counts for Splendor Duel.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup" (25 tokens:
4 each of the five gems, 2 pearls, 3 gold).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Color(str, enum.Enum):
    """A token and bonus color; values match the keys in ``cards.json``."""

    WHITE = "white"
    BLUE = "blue"
    GREEN = "green"
    RED = "red"
    BLACK = "black"
    PEARL = "pearl"
    GOLD = "gold"


#: The five gem colors. Pearls and gold are tokens but never card bonuses.
GEM_COLORS: tuple[Color, ...] = (
    Color.WHITE,
    Color.BLUE,
    Color.GREEN,
    Color.RED,
    Color.BLACK,
)

_TOKEN_FIELDS: tuple[str, ...] = (
    "white",
    "blue",
    "green",
    "red",
    "black",
    "pearl",
    "gold",
)


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

    def count(self, color: Color) -> int:
        """Return how many tokens of ``color`` are held."""
        from splendor_duel_engine.engine.helpers import count
        return count(self, color)

    def total(self) -> int:
        """Return the total number of tokens held across all colors."""
        from splendor_duel_engine.engine.helpers import total
        return total(self)

    def __add__(self, other: Tokens) -> Tokens:
        if not isinstance(other, Tokens):
            return NotImplemented
        from splendor_duel_engine.engine.helpers import add
        return add(self, other)

    def __sub__(self, other: Tokens) -> Tokens:
        if not isinstance(other, Tokens):
            return NotImplemented
        from splendor_duel_engine.engine.helpers import sub
        return sub(self, other)
