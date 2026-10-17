"""Card data and loader tests.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup" and
"Card abilities".
"""

from __future__ import annotations

import json

import pytest

from splendor_duel_engine.engine.cards import CARDS_PATH, Ability, load_cards
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens


def test_deck_composition():
    jewels, _ = load_cards()
    assert len(jewels) == 67  # spec: 67 jewel cards
    assert [sum(1 for c in jewels if c.level == n) for n in (1, 2, 3)] == [30, 24, 13]
    assert sum(c.crowns for c in jewels) == 28  # spec: total crowns
    assert sum(c.points for c in jewels) == 92  # spec: total prestige


def test_multicolor_cards():
    jewels, _ = load_cards()
    multi = [c for c in jewels if c.ability is Ability.MULTICOLOR]
    assert len(multi) == 9  # spec: 9 copy-bonus cards
    assert all(c.bonus is None for c in multi)
    # Every other card keeps its color bonus, except the spec's "colorless
    # no-bonus cards" (bonus_count == 0; spec: "colorless no-bonus cards and
    # royals do not count"). Only the packaged joker cards lose their bonus.
    assert all(
        c.bonus is not None
        for c in jewels
        if c.ability is not Ability.MULTICOLOR and c.bonus_count > 0
    )


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
    assert (Tokens(white=3) - Tokens(white=1)).white == 2
    assert Tokens(white=1).total() == 1


def test_tokens_count_by_color():
    assert GEM_COLORS == (Color.WHITE, Color.BLUE, Color.GREEN, Color.RED, Color.BLACK)
    tokens = Tokens(white=2, black=1)
    assert tokens.count(Color.WHITE) == 2
    assert tokens.count(Color.BLACK) == 1
    assert tokens.count(Color.GOLD) == 0
