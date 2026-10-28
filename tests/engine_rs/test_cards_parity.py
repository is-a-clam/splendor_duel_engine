"""Parity between the Rust card loader and the Python one."""

from __future__ import annotations

from splendor_duel_engine._core import load_cards

from splendor_duel_engine.engine.cards import load_cards as py_load_cards


def test_jewel_count_matches() -> None:
    rust_jewels, rust_royals = load_cards()
    py_jewels, py_royals = py_load_cards()
    assert len(rust_jewels) == len(py_jewels) == 67
    assert len(rust_royals) == len(py_royals) == 4


def test_card_ids_and_order_match() -> None:
    rust_jewels, rust_royals = load_cards()
    py_jewels, py_royals = py_load_cards()
    assert [c.id for c in rust_jewels] == [c.id for c in py_jewels]
    assert [r.id for r in rust_royals] == [r.id for r in py_royals]


def test_every_card_field_matches() -> None:
    rust_jewels, _ = load_cards()
    py_jewels, _ = py_load_cards()
    for rust, py in zip(rust_jewels, py_jewels, strict=True):
        assert rust.id == py.id
        assert rust.level == py.level
        assert rust.points == py.points
        assert rust.crowns == py.crowns
        assert rust.bonus_count == py.bonus_count
        assert rust.is_multicolor == py.is_multicolor
        assert (rust.bonus.value if rust.bonus is not None else None) == (
            py.bonus.value if py.bonus is not None else None
        )
        assert (rust.ability.value if rust.ability is not None else None) == (
            py.ability.value if py.ability is not None else None
        )
        for field in ("white", "blue", "green", "red", "black", "pearl", "gold"):
            assert getattr(rust.cost, field) == getattr(py.cost, field)


def test_level_census_matches() -> None:
    rust_jewels, _ = load_cards()
    py_jewels, _ = py_load_cards()
    for level in (1, 2, 3):
        assert sum(1 for c in rust_jewels if c.level == level) == sum(
            1 for c in py_jewels if c.level == level
        )


def test_color_and_phase_members_match_the_python_enums() -> None:
    from splendor_duel_engine._core import Ability, Color, Phase

    from splendor_duel_engine.engine.cards import Ability as PyAbility
    from splendor_duel_engine.engine.colors import Color as PyColor
    from splendor_duel_engine.engine.phase import Phase as PyPhase

    for name in ("WHITE", "BLUE", "GREEN", "RED", "BLACK", "PEARL", "GOLD"):
        assert getattr(Color, name).value == getattr(PyColor, name).value
    for name in ("EXTRA_TURN", "TAKE_MATCHING_TOKEN", "STEAL_TOKEN", "PRIVILEGE"):
        assert getattr(Ability, name).value == getattr(PyAbility, name).value
    for name in (
        "USE_PRIVILEGES",
        "REPLENISH",
        "MANDATORY",
        "CHOOSE_PAYMENT",
        "CHOOSE_GOLD",
        "MULTICOLOR_COLOR",
        "STEAL_TOKEN",
        "TAKE_MATCHING_TOKEN",
        "CHOOSE_ROYAL",
        "DISCARD",
        "GAME_OVER",
    ):
        assert getattr(Phase, name).value == getattr(PyPhase, name).value


def test_gem_colors_matches() -> None:
    from splendor_duel_engine._core import GEM_COLORS as RustGemColors

    from splendor_duel_engine.engine.colors import GEM_COLORS as PyGemColors

    assert tuple(c.value for c in RustGemColors) == tuple(c.value for c in PyGemColors)
