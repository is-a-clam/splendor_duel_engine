"""The engine surface the agents use.

The backend is chosen by the ``SPLENDOR_DUEL_ENGINE`` environment variable:

- ``python`` (the default) — the pure-Python reference engine.
- ``rust`` — the Rust extension, which reproduces the reference engine
  exactly.

Both backends expose the same names with the same semantics, so no agent code
changes when the backend changes. Agents import engine names from this module
and never from ``splendor_duel_engine.engine.*`` directly.

The switch is resolved once, at import time: it is a process-wide setting.
"""

from __future__ import annotations

import os

__all__ = [
    "GEM_COLORS",
    "Ability",
    "Action",
    "BuyCard",
    "Card",
    "ChooseGold",
    "ChooseMatchingToken",
    "ChooseMulticolor",
    "ChooseRoyal",
    "ChooseStealToken",
    "Color",
    "DecisionPoint",
    "DiscardTokens",
    "DoneWithPrivileges",
    "DoneWithReplenish",
    "GameState",
    "Observation",
    "PayTokens",
    "Phase",
    "PlayerState",
    "PlayerView",
    "PurchasedCard",
    "Replenish",
    "ReserveCard",
    "ReservedCard",
    "RoyalCard",
    "TakeTokens",
    "Tokens",
    "UsePrivilege",
    "apply",
    "decide",
    "helpers",
    "is_winner",
    "load_cards",
    "observation",
]

_BACKEND = os.environ.get("SPLENDOR_DUEL_ENGINE", "python").strip().lower()

if _BACKEND == "rust":
    from splendor_duel_engine.rust_engine import (
        GEM_COLORS as RustGEM_COLORS,
        Ability,
        Action,
        BuyCard,
        Card as RustCard,
        ChooseGold,
        ChooseMatchingToken,
        ChooseMulticolor,
        ChooseRoyal,
        ChooseStealToken,
        Color as RustColor,
        DecisionPoint,
        DiscardTokens,
        DoneWithPrivileges,
        DoneWithReplenish,
        GameState,
        Observation,
        PayTokens,
        Phase,
        PlayerState as RustPlayerState,
        PlayerView as RustPlayerView,
        PurchasedCard as RustPurchasedCard,
        Replenish,
        ReserveCard,
        ReservedCard as RustReservedCard,
        RoyalCard as RustRoyalCard,
        TakeTokens,
        Tokens as RustTokens,
        UsePrivilege,
        apply,
        decide,
        load_cards,
        observation,
    )
    from splendor_duel_engine.engine import helpers as py_helpers
    from splendor_duel_engine.engine.colors import GEM_COLORS as PyGEM_COLORS
    from splendor_duel_engine.engine.colors import Color as PyColor, Tokens as PyTokens

    # Re-export Rust types under the standard names
    Color = RustColor
    Tokens = RustTokens
    Card = RustCard
    PlayerState = RustPlayerState
    PlayerView = RustPlayerView
    PurchasedCard = RustPurchasedCard
    ReservedCard = RustReservedCard
    RoyalCard = RustRoyalCard
    GEM_COLORS = PyGEM_COLORS  # Use Python GEM_COLORS for helpers

    # Create unified helpers that convert Rust types to Python types before calling Python helpers
    class _RustHelpers:
        """Wrapper that converts Rust types to Python types before calling Python helpers."""

        @staticmethod
        def _to_py_color(c):
            """Convert Rust Color to Python Color."""
            if hasattr(c, 'value'):  # Rust Color
                return getattr(PyColor, c.value.upper())
            return c  # Already Python Color

        @staticmethod
        def _to_py_tokens(t):
            """Convert Rust Tokens to Python Tokens."""
            if hasattr(t, 'inner'):  # Rust Tokens
                return PyTokens(
                    white=t.white, blue=t.blue, green=t.green, red=t.red,
                    black=t.black, pearl=t.pearl, gold=t.gold
                )
            return t  # Already Python Tokens

        def cost_deficits(self, cost, bonus, paid):
            return py_helpers.cost_deficits(
                self._to_py_tokens(cost),
                self._to_py_tokens(bonus),
                self._to_py_tokens(paid)
            )

        def can_afford_card(self, card, tokens, bonus):
            return py_helpers.can_afford_card(card, self._to_py_tokens(tokens), self._to_py_tokens(bonus))

        def legal_payments(self, card, tokens, bonus):
            return py_helpers.legal_payments(card, self._to_py_tokens(tokens), self._to_py_tokens(bonus))

        def take_penalty(self, colors):
            py_colors = [self._to_py_color(c) for c in colors]
            return py_helpers.take_penalty(py_colors)

        def color_points(self, purchased, color):
            return py_helpers.color_points(purchased, self._to_py_color(color))

        def discard_subsets(self, tokens, excess):
            return py_helpers.discard_subsets(self._to_py_tokens(tokens), excess)

        def can_reserve(self, board, reserved_count):
            py_board = [self._to_py_color(c) if c else None for c in board]
            return py_helpers.can_reserve(py_board, reserved_count)

        def visible_cards(self, pyramid, reserved_public, reserved_deck):
            return py_helpers.visible_cards(pyramid, reserved_public, reserved_deck)

        def is_winner(self, player):
            return py_helpers.is_winner(player)

        # Constants
        TOKEN_LIMIT = py_helpers.TOKEN_LIMIT
        MAX_RESERVED = py_helpers.MAX_RESERVED
        PRESTIGE_WIN = py_helpers.PRESTIGE_WIN
        CROWNS_WIN = py_helpers.CROWNS_WIN
        COLOR_WIN_POINTS = py_helpers.COLOR_WIN_POINTS

    helpers = _RustHelpers()
    is_winner = py_helpers.is_winner

elif _BACKEND == "python":
    from splendor_duel_engine.engine import helpers
    from splendor_duel_engine.engine.actions import (
        Action,
        BuyCard,
        ChooseGold,
        ChooseMatchingToken,
        ChooseMulticolor,
        ChooseRoyal,
        ChooseStealToken,
        DecisionPoint,
        DiscardTokens,
        DoneWithPrivileges,
        DoneWithReplenish,
        PayTokens,
        Replenish,
        ReserveCard,
        TakeTokens,
        UsePrivilege,
        apply,
        decide,
    )
    from splendor_duel_engine.engine.cards import (
        Ability,
        Card,
        RoyalCard,
        load_cards,
    )
    from splendor_duel_engine.engine.colors import (
        GEM_COLORS,
        Color,
        Tokens,
    )
    from splendor_duel_engine.engine.helpers import is_winner
    from splendor_duel_engine.engine.observation import (
        Observation,
        PlayerView,
        observation,
    )
    from splendor_duel_engine.engine.phase import Phase
    from splendor_duel_engine.engine.state import (
        GameState,
        PlayerState,
        PurchasedCard,
        ReservedCard,
    )
else:
    raise ValueError(
        f"unknown SPLENDOR_DUEL_ENGINE backend: {_BACKEND!r} "
        "(expected 'python' or 'rust')"
    )
