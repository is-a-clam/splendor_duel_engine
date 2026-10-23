"""The Rust engine, re-exported under the Python engine's names.

``splendor_duel_engine._core`` exposes its own types; this module gives them the
names the Python engine uses, so the rest of the package does not care which
backend is active. See :mod:`splendor_duel_engine.engine_api`.
"""

from __future__ import annotations

import typing

from splendor_duel_engine._core import (
    GEM_COLORS,
    Ability,
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

#: The Rust ``Action`` is an enum, not a ``#[pyclass]``: ``_core`` does not
#: export it. The rest of the package only ever uses it as a type annotation
#: (every module has ``from __future__ import annotations``), so a union of the
#: action classes is the correct stand-in and hashes/compares identically.
Action: typing.TypeAlias = (
    UsePrivilege
    | DoneWithPrivileges
    | Replenish
    | DoneWithReplenish
    | TakeTokens
    | BuyCard
    | PayTokens
    | ChooseGold
    | ChooseMulticolor
    | ChooseStealToken
    | ChooseMatchingToken
    | ChooseRoyal
    | DiscardTokens
    | ReserveCard
)

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
    "load_cards",
    "observation",
    "helpers",
]
