"""Card data and loader tests.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup" and
"Card abilities".
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from splendor_duel_engine.engine.cards import CARDS_PATH, Ability, load_cards
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.helpers import get_tokens, sub_tokens, total_tokens


def test_deck_composition():
    jewels, _ = load_cards()
    assert len(jewels) == 67  # spec: 67 jewel cards
    assert [sum(1 for c in jewels if c.level == n) for n in (1, 2, 3)] == [30, 24, 13]
    assert sum(c.crowns for c in jewels) == 28  # spec: total crowns
    assert sum(c.points for c in jewels) == 92  # spec: total prestige
    # Restored data pins the ability census and the orthogonal multicolor set.
    census = Counter(c.ability for c in jewels)
    assert census[Ability.EXTRA_TURN] == 6
    assert census[Ability.TAKE_MATCHING_TOKEN] == 5
    assert census[Ability.STEAL_TOKEN] == 5
    assert census[Ability.PRIVILEGE] == 5
    assert census[None] == 46
    assert sum(1 for c in jewels if c.is_multicolor) == 9


def test_multicolor_cards():
    jewels, _ = load_cards()
    multi = [c for c in jewels if c.is_multicolor]
    assert len(multi) == 9  # spec: 9 copy-bonus cards
    assert all(c.bonus is None and c.bonus_count >= 1 for c in multi)
    # multicolor is orthogonal to abilities: L3-01 is multicolor AND extra_turn (Ruling R3)
    assert [c.id for c in multi if c.ability is not None] == ["L3-01"]
    # the colorless no-bonus cards have no color bonus and are not multicolor
    colorless = [c for c in jewels if not c.is_multicolor and c.bonus is None]
    assert sorted(c.id for c in colorless) == ["L1-29", "L2-23", "L3-12"]
    assert all(c.bonus_count == 0 for c in colorless)


def test_royal_cards():
    _, royals = load_cards()
    assert len(royals) == 4
    assert sorted((r.points, r.ability) for r in royals) == [
        (2, Ability.EXTRA_TURN),
        (2, Ability.PRIVILEGE),
        (2, Ability.STEAL_TOKEN),
        (3, None),
    ]


def test_load_cards_rejects_bad_data(tmp_path):
    """A mutated copy (one jewel card short) is rejected by the loader."""
    raw = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    raw["jewel_cards"].pop()
    bad_path = tmp_path / "cards.json"
    bad_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="67"):
        load_cards(bad_path)


def test_load_cards_rejects_unknown_cost_key(tmp_path):
    """Gold is never a card cost; an unknown cost key is rejected."""
    raw = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    raw["jewel_cards"][0]["cost"]["gold"] = 1
    bad_path = tmp_path / "cards.json"
    bad_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="cost"):
        load_cards(bad_path)


def test_tokens_are_hashable_and_arithmetic():
    assert hash(Tokens(white=2, pearl=1)) is not None
    assert sub_tokens(Tokens(white=3), Tokens(white=1)).white == 2
    assert total_tokens(Tokens(white=1)) == 1


def test_tokens_count_by_color():
    assert GEM_COLORS == (Color.WHITE, Color.BLUE, Color.GREEN, Color.RED, Color.BLACK)
    tokens = Tokens(white=2, black=1)
    assert get_tokens(tokens, Color.WHITE) == 2
    assert get_tokens(tokens, Color.BLACK) == 1
    assert get_tokens(tokens, Color.GOLD) == 0
