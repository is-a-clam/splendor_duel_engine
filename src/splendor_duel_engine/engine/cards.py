"""Card data model and loader.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup" (67 jewel
cards, 4 royal cards) and "Card abilities" (the four printed abilities; the
multicolor copy-bonus rule is an orthogonal card property, Ruling R3). The card
values live in ``cards.json`` and are treated as authoritative data; the loader
exposes the data's ``"bonus": "joker"`` spelling as :attr:`Card.is_multicolor`
and validates that the data still matches the spec's pinned counts.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.colors import GEM_COLORS, PAY_COLORS, Color, Tokens

if TYPE_CHECKING:
    from collections.abc import Iterable


CARDS_PATH: pathlib.Path = pathlib.Path(__file__).parents[1] / "data" / "cards.json"

_COST_KEYS: frozenset[str] = frozenset(color.value for color in PAY_COLORS)
_EXPECTED_JEWEL_CARDS: int = 67
_EXPECTED_LEVEL_COUNTS: dict[int, int] = {1: 30, 2: 24, 3: 13}
_EXPECTED_TOTAL_CROWNS: int = 28
_EXPECTED_TOTAL_POINTS: int = 92
_EXPECTED_MULTICOLOR_CARDS: int = 9
_EXPECTED_ROYAL_CARDS: int = 4


class Ability(Enum):
    """
    A printed card ability; values match the keys in ``cards.json``.
    """

    EXTRA_TURN = "extra_turn"
    TAKE_MATCHING_TOKEN = "take_matching_token"
    STEAL_TOKEN = "steal_token"
    PRIVILEGE = "privilege"


@dataclass(frozen=True, slots=True)
class Card:
    """
    A jewel card.

    ``is_multicolor`` marks the copy-bonus (joker) cards; it is orthogonal to
    ``ability``, so a card may be multicolor and still carry a printed ability
    """

    id: str
    level: int
    points: int
    crowns: int
    bonus: Color | None
    bonus_count: int
    ability: Ability | None
    is_multicolor: bool
    cost: Tokens


@dataclass(frozen=True, slots=True)
class RoyalCard:
    """A royal card: prestige and at most one ability"""

    id: str
    points: int
    ability: Ability | None


def load_cards(
    path: pathlib.Path | None = None,
) -> tuple[tuple[Card, ...], tuple[RoyalCard, ...]]:
    """Load and validate the card data.

    Returns ``(jewel_cards, royal_cards)`` in file order. ``path`` defaults to
    the packaged :data:`CARDS_PATH`. Raises :class:`ValueError` naming the
    failing expectation on any value or consistency failure, and
    :class:`TypeError` when the JSON document has the wrong shape.
    """
    source = CARDS_PATH if path is None else pathlib.Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{source}: top level must be a JSON object")

    jewels = _load_jewels(raw.get("jewel_cards"), source)
    royals = _load_royals(raw.get("royal_cards"), source)
    _validate_jewel_deck(jewels)
    return jewels, royals


def _load_jewels(raw_cards: object, source: pathlib.Path) -> tuple[Card, ...]:
    if not isinstance(raw_cards, list):
        raise TypeError(f"{source}: 'jewel_cards' must be a list")
    cards = tuple(_parse_card(entry, source) for entry in raw_cards)
    _ensure_unique_ids((card.id for card in cards), source)
    return cards


def _load_royals(raw_cards: object, source: pathlib.Path) -> tuple[RoyalCard, ...]:
    if not isinstance(raw_cards, list):
        raise TypeError(f"{source}: 'royal_cards' must be a list")
    royals = tuple(_parse_royal(entry, source) for entry in raw_cards)
    _ensure_unique_ids((royal.id for royal in royals), source)
    if len(royals) != _EXPECTED_ROYAL_CARDS:
        raise ValueError(
            f"{source}: expected {_EXPECTED_ROYAL_CARDS} royal cards, got {len(royals)}"
        )
    return royals


def _parse_card(entry: object, source: pathlib.Path) -> Card:
    if not isinstance(entry, dict):
        raise TypeError(f"{source}: jewel card entries must be JSON objects")
    card_id = entry.get("id")
    if not isinstance(card_id, str) or not card_id:
        raise ValueError(f"{source}: jewel card has a missing or invalid id")
    where = f"card {card_id}"

    level = _as_int(entry.get("level"), f"{where}.level", minimum=1)
    if level not in _EXPECTED_LEVEL_COUNTS:
        raise ValueError(f"{where}: level must be 1, 2 or 3, got {level}")
    points = _as_int(entry.get("points"), f"{where}.points")
    crowns = _as_int(entry.get("crowns"), f"{where}.crowns")
    bonus_count = _as_int(entry.get("bonus_count"), f"{where}.bonus_count")
    bonus, is_multicolor = _parse_bonus(entry.get("bonus"), where)
    ability = _parse_ability(entry.get("ability"), where)
    cost = _parse_cost(entry.get("cost"), where)

    if is_multicolor:
        if bonus is not None:
            raise ValueError(
                f"{where}: multicolor card must have no bonus, got {bonus.value!r}"
            )
        if bonus_count < 1:
            raise ValueError(
                f"{where}: multicolor card must have bonus_count >= 1, got {bonus_count}"
            )
    elif bonus is None:
        if bonus_count != 0:
            raise ValueError(
                f"{where}: colorless card must have bonus_count 0, got {bonus_count}"
            )
    elif bonus_count < 1:
        raise ValueError(
            f"{where}: card with a {bonus.value!r} bonus must have bonus_count >= 1"
        )

    return Card(
        id=card_id,
        level=level,
        points=points,
        crowns=crowns,
        bonus=bonus,
        bonus_count=bonus_count,
        ability=ability,
        is_multicolor=is_multicolor,
        cost=cost,
    )


def _parse_royal(entry: object, source: pathlib.Path) -> RoyalCard:
    if not isinstance(entry, dict):
        raise TypeError(f"{source}: royal card entries must be JSON objects")
    royal_id = entry.get("id")
    if not isinstance(royal_id, str) or not royal_id:
        raise ValueError(f"{source}: royal card has a missing or invalid id")
    where = f"royal {royal_id}"
    return RoyalCard(
        id=royal_id,
        points=_as_int(entry.get("points"), f"{where}.points"),
        ability=_parse_ability(entry.get("ability"), where),
    )


def _parse_bonus(value: object, where: str) -> tuple[Color | None, bool]:
    # "joker" is the data spelling of the multicolor (copy-bonus) property.
    if value is None:
        return None, False
    if value == "joker":
        return None, True
    try:
        bonus = Color(value)
    except ValueError as exc:
        raise ValueError(f"{where}: unknown bonus {value!r}") from exc
    if bonus not in GEM_COLORS:
        raise ValueError(f"{where}: bonus must be a gem color, got {value!r}")
    return bonus, False


def _parse_ability(value: object, where: str) -> Ability | None:
    if value is None:
        return None
    try:
        return Ability(value)
    except ValueError as exc:
        raise ValueError(f"{where}: unknown ability {value!r}") from exc


def _parse_cost(value: object, where: str) -> Tokens:
    if not isinstance(value, dict):
        raise TypeError(f"{where}: cost must be a JSON object")
    unknown = set(value) - _COST_KEYS
    if unknown:
        raise ValueError(f"{where}: cost has unknown keys {sorted(unknown)}")
    return Tokens(
        **{
            key: _as_int(amount, f"{where}.cost[{key!r}]")
            for key, amount in value.items()
        }
    )


def _as_int(value: object, where: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{where} must be an integer >= {minimum}, got {value!r}")
    return value


def _ensure_unique_ids(ids: Iterable[str], source: pathlib.Path) -> None:
    seen: set[str] = set()
    for card_id in ids:
        if card_id in seen:
            raise ValueError(f"{source}: duplicate card id {card_id!r}")
        seen.add(card_id)


def _validate_jewel_deck(jewels: tuple[Card, ...]) -> None:
    if len(jewels) != _EXPECTED_JEWEL_CARDS:
        raise ValueError(
            f"expected {_EXPECTED_JEWEL_CARDS} jewel cards, got {len(jewels)}"
        )
    for level, expected in _EXPECTED_LEVEL_COUNTS.items():
        actual = sum(1 for card in jewels if card.level == level)
        if actual != expected:
            raise ValueError(
                f"expected {expected} level-{level} jewel cards, got {actual}"
            )
    crowns = sum(card.crowns for card in jewels)
    if crowns != _EXPECTED_TOTAL_CROWNS:
        raise ValueError(
            f"expected {_EXPECTED_TOTAL_CROWNS} total jewel crowns, got {crowns}"
        )
    points = sum(card.points for card in jewels)
    if points != _EXPECTED_TOTAL_POINTS:
        raise ValueError(
            f"expected {_EXPECTED_TOTAL_POINTS} total jewel prestige points, got {points}"
        )
    multicolor = sum(1 for card in jewels if card.is_multicolor)
    if multicolor != _EXPECTED_MULTICOLOR_CARDS:
        raise ValueError(
            f"expected {_EXPECTED_MULTICOLOR_CARDS} multicolor jewel cards, got {multicolor}"
        )
