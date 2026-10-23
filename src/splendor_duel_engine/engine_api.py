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
    "load_cards",
    "observation",
    "helpers",
]

_BACKEND = os.environ.get("SPLENDOR_DUEL_ENGINE", "python").strip().lower()

if _BACKEND == "rust":
    from splendor_duel_engine.rust_engine import (
        GEM_COLORS,
        Ability,
        Action,
        BuyCard,
        Card,
        ChooseGold,
        ChooseMatchingToken,
        ChooseMulticolor,
        ChooseRoyal,
        ChooseStealToken,
        Color,
        DecisionPoint,
        DiscardTokens,
        DoneWithPrivileges,
        DoneWithReplenish,
        GameState,
        Observation,
        PayTokens,
        Phase,
        PlayerState,
        PlayerView,
        PurchasedCard,
        Replenish,
        ReserveCard,
        ReservedCard,
        RoyalCard,
        TakeTokens,
        Tokens,
        UsePrivilege,
        apply,
        decide,
        load_cards,
        observation,
        helpers,
    )
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
