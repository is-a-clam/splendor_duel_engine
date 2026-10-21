"""Tests for the public rule helpers in :mod:`splendor_duel_engine.engine.helpers`.

Each helper is a mechanical rule query with no heuristics: these tests pin the
rule, not a preference.
"""

from __future__ import annotations

from splendor_duel_engine.engine.cards import Card
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.helpers import (
    can_afford_card,
    can_reserve,
    color_points,
    cost_deficits,
    discard_subsets,
    legal_payments,
    take_penalty,
    visible_cards,
)
from splendor_duel_engine.engine.state import PurchasedCard


def make_card(
    card_id: str = "T1",
    *,
    cost: Tokens | None = None,
    points: int = 0,
    crowns: int = 0,
    bonus: Color | None = None,
    bonus_count: int = 0,
    is_multicolor: bool = False,
) -> Card:
    """Build a test card. Defaults are a level-1 card with no ability."""
    return Card(
        id=card_id,
        level=1,
        points=points,
        crowns=crowns,
        bonus=bonus,
        bonus_count=bonus_count,
        ability=None,
        is_multicolor=is_multicolor,
        cost=cost if cost is not None else Tokens(),
    )


# --- cost_deficits -------------------------------------------------------


def test_cost_deficits_reports_missing_tokens_per_colour():
    cost = Tokens(white=3, blue=2, pearl=1)
    bonus = Tokens(white=1)
    paid = Tokens(white=1, blue=1)
    assert cost_deficits(cost, bonus, paid) == {
        Color.WHITE: 1,
        Color.BLUE: 1,
        Color.PEARL: 1,
    }


def test_cost_deficits_omits_colours_that_are_covered():
    cost = Tokens(white=2, blue=1)
    assert cost_deficits(cost, Tokens(), Tokens(white=2, blue=1)) == {}


def test_cost_deficits_never_discounts_pearls():
    # Pearls are never a card bonus, so a pearl cost is never reduced.
    assert cost_deficits(Tokens(pearl=2), Tokens(pearl=1), Tokens()) == {Color.PEARL: 2}


def test_cost_deficits_ignores_gold():
    # Gold is never a card cost; it is only a wild payment token.
    deficits = cost_deficits(Tokens(white=1, gold=2), Tokens(), Tokens())
    assert deficits == {Color.WHITE: 1}
    assert Color.GOLD not in deficits


def test_cost_deficits_orders_gem_colours_then_pearl():
    cost = Tokens(white=1, blue=1, green=1, red=1, black=1, pearl=1)
    deficits = cost_deficits(cost, Tokens(), Tokens())
    assert list(deficits) == [*GEM_COLORS, Color.PEARL]


# --- take_penalty --------------------------------------------------------


def test_take_penalty_for_three_of_a_colour():
    assert take_penalty([Color.WHITE, Color.WHITE, Color.WHITE])


def test_take_penalty_for_two_pearls():
    assert take_penalty([Color.PEARL, Color.PEARL])


def test_take_penalty_false_for_a_safe_line():
    assert not take_penalty([Color.WHITE, Color.BLUE])
    assert not take_penalty([Color.WHITE, Color.WHITE])


# --- color_points --------------------------------------------------------


def test_color_points_counts_card_points_only():
    purchased = (
        PurchasedCard(
            card=make_card("C1", points=3, bonus=Color.WHITE), chosen_color=None
        ),
        PurchasedCard(
            card=make_card("C2", points=2, bonus=Color.RED), chosen_color=None
        ),
    )
    assert color_points(purchased, Color.WHITE) == 3
    assert color_points(purchased, Color.RED) == 2
    assert color_points(purchased, Color.BLUE) == 0


def test_color_points_uses_the_chosen_colour_for_multicolor_cards():
    purchased = (
        PurchasedCard(
            card=make_card("M1", points=4, is_multicolor=True, bonus_count=1),
            chosen_color=Color.RED,
        ),
    )
    assert color_points(purchased, Color.RED) == 4
    assert color_points(purchased, Color.WHITE) == 0


def test_color_points_ignores_colourless_cards():
    purchased = (PurchasedCard(card=make_card("X1", points=5), chosen_color=None),)
    assert color_points(purchased, Color.WHITE) == 0


# --- discard_subsets -----------------------------------------------------


def test_discard_subsets_enumerates_distinct_subsets():
    tokens = Tokens(white=2, blue=1)
    assert discard_subsets(tokens, 1) == [Tokens(white=1), Tokens(blue=1)]
    assert discard_subsets(tokens, 2) == [
        Tokens(white=2),
        Tokens(white=1, blue=1),
    ]


def test_discard_subsets_returns_one_result_for_the_whole_hand():
    tokens = Tokens(white=2, blue=1)
    assert discard_subsets(tokens, 3) == [Tokens(white=2, blue=1)]


# --- can_reserve ---------------------------------------------------------


def test_can_reserve_requires_gold_on_board():
    assert not can_reserve((Color.WHITE,) * 25, 0)
    assert can_reserve((Color.GOLD,) + (Color.WHITE,) * 24, 0)


def test_can_reserve_requires_a_free_slot():
    board = (Color.GOLD,) + (Color.WHITE,) * 24
    assert can_reserve(board, 2)
    assert not can_reserve(board, 3)


# --- visible_cards -------------------------------------------------------


def test_visible_cards_orders_pyramid_then_reserves():
    pyramid = ((make_card("P1"), None), (make_card("P2"),))
    cards = visible_cards(pyramid, (make_card("R1"),), (make_card("D1"),))
    assert [c.id for c in cards] == ["P1", "P2", "R1", "D1"]


# --- can_afford_card -----------------------------------------------------


def test_can_afford_card_uses_gold_as_a_wild_token():
    card = make_card(cost=Tokens(white=2, blue=2))
    assert can_afford_card(card, Tokens(gold=4), Tokens())
    assert not can_afford_card(card, Tokens(gold=3), Tokens())


def test_can_afford_card_applies_bonuses():
    card = make_card(cost=Tokens(white=3))
    assert can_afford_card(card, Tokens(), Tokens(white=3))
    assert can_afford_card(card, Tokens(white=2), Tokens(white=1))
    assert not can_afford_card(card, Tokens(white=1), Tokens(white=1))


def test_can_afford_card_never_discounts_pearls_with_bonus():
    card = make_card(cost=Tokens(pearl=1))
    assert can_afford_card(card, Tokens(pearl=1), Tokens())
    assert not can_afford_card(card, Tokens(), Tokens(pearl=1))


def test_can_afford_card_rejects_multicolor_without_a_coloured_bonus():
    card = make_card(cost=Tokens(white=3), is_multicolor=True, bonus_count=1)
    assert not can_afford_card(card, Tokens(gold=3), Tokens())
    assert can_afford_card(card, Tokens(gold=3), Tokens(white=1))


def test_can_afford_card_does_not_require_a_bonus_for_ordinary_cards():
    card = make_card(cost=Tokens(white=1))
    assert can_afford_card(card, Tokens(white=1), Tokens())


# --- legal_payments ------------------------------------------------------


def test_legal_payments_yields_only_the_minimum_gold():
    # The minimum gold is per combination of coloured tokens and pearls: each
    # combination is yielded with the minimum gold needed for *that* combination.
    card = make_card(cost=Tokens(white=2))
    assert legal_payments(card, Tokens(white=2, gold=3), Tokens()) == [
        Tokens(gold=2),
        Tokens(white=1, gold=1),
        Tokens(white=2),
    ]


def test_legal_payments_yields_payments_that_use_more_gold_than_the_cheapest():
    # A payment that spends fewer coloured tokens and covers the shortfall with
    # more gold is still legal, so it is still yielded: the enumeration is not
    # filtered to the globally cheapest gold.
    card = make_card(cost=Tokens(white=2))
    payments = legal_payments(card, Tokens(white=2, gold=3), Tokens())
    assert Tokens(gold=2) in payments
    assert Tokens(white=2) in payments
    assert min(p.gold for p in payments) == 0
    assert max(p.gold for p in payments) == 2


def test_legal_payments_covers_a_shortfall_with_gold():
    card = make_card(cost=Tokens(white=3))
    assert legal_payments(card, Tokens(white=2, gold=1), Tokens()) == [
        Tokens(white=2, gold=1)
    ]


def test_legal_payments_is_empty_when_the_card_is_unaffordable():
    card = make_card(cost=Tokens(white=5))
    assert legal_payments(card, Tokens(white=1, gold=1), Tokens()) == []


def test_legal_payments_is_empty_for_multicolor_without_a_coloured_bonus():
    card = make_card(cost=Tokens(white=3), is_multicolor=True, bonus_count=1)
    assert legal_payments(card, Tokens(gold=3), Tokens()) == []
