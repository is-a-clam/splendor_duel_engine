"""Tests for the public rule helpers in :mod:`splendor_duel_engine.engine.helpers`.

Each helper is a mechanical rule query with no heuristics: these tests pin the
rule, not a preference.
"""

from __future__ import annotations

from collections import Counter

from splendor_duel_engine.engine.cards import Card
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.helpers import (
    can_afford_card,
    can_reserve,
    color_points,
    cost_deficits,
    discard_subsets,
    is_penalty_triggered,
    is_winner,
    legal_payments,
    visible_cards,
)
from splendor_duel_engine.engine.state import PlayerState, PurchasedCard


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


def test_cost_deficits_reports_missing_tokens_per_color():
    cost = Tokens(white=3, blue=2, pearl=1)
    bonus = Tokens(white=1)
    paid = Tokens(white=1, blue=1)
    assert cost_deficits(cost, bonus, paid) == Tokens(
        white=1,
        blue=1,
        green=0,
        red=0,
        black=0,
        pearl=1,
        gold=0,
    )


def test_cost_deficits_omits_colors_that_are_covered():
    cost = Tokens(white=2, blue=1)
    assert cost_deficits(cost, Tokens(), Tokens(white=2, blue=1)) == Tokens()


def test_cost_deficits_orders_gem_colors_then_pearl():
    cost = Tokens(white=1, blue=1, green=1, red=1, black=1, pearl=1)
    deficits = cost_deficits(cost, Tokens(), Tokens())
    assert deficits == cost


# --- take_penalty --------------------------------------------------------


def test_take_penalty_for_three_of_a_color():
    assert is_penalty_triggered([Color.WHITE, Color.WHITE, Color.WHITE])


def test_take_penalty_for_two_pearls():
    assert is_penalty_triggered([Color.PEARL, Color.PEARL])


def test_take_penalty_false_for_a_safe_line():
    assert not is_penalty_triggered([Color.WHITE, Color.BLUE])
    assert not is_penalty_triggered([Color.WHITE, Color.WHITE])


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


def test_color_points_uses_the_chosen_color_for_multicolor_cards():
    purchased = (
        PurchasedCard(
            card=make_card("M1", points=4, is_multicolor=True, bonus_count=1),
            chosen_color=Color.RED,
        ),
    )
    assert color_points(purchased, Color.RED) == 4
    assert color_points(purchased, Color.WHITE) == 0


def test_color_points_ignores_colorless_cards():
    purchased = (PurchasedCard(card=make_card("X1", points=5), chosen_color=None),)
    assert color_points(purchased, Color.WHITE) == 0


# --- discard_subsets -----------------------------------------------------


def test_discard_subsets_enumerates_distinct_subsets():
    tokens = Tokens(white=2, blue=1)
    assert Counter(discard_subsets(tokens, 1)) == Counter(
        [Tokens(white=1), Tokens(blue=1)]
    )
    assert Counter(discard_subsets(tokens, 2)) == Counter(
        [
            Tokens(white=2),
            Tokens(white=1, blue=1),
        ]
    )


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
    assert can_afford_card(card, Tokens(), Tokens(gold=4))
    assert not can_afford_card(card, Tokens(), Tokens(gold=3))


def test_can_afford_card_applies_bonuses():
    card = make_card(cost=Tokens(white=3))
    assert can_afford_card(card, Tokens(white=3), Tokens())
    assert can_afford_card(card, Tokens(white=1), Tokens(white=2))
    assert not can_afford_card(card, Tokens(white=1), Tokens(white=1))


def test_can_afford_card_rejects_multicolor_without_a_colored_bonus():
    card = make_card(cost=Tokens(white=3), is_multicolor=True, bonus_count=1)
    assert not can_afford_card(card, Tokens(), Tokens(gold=3))
    assert can_afford_card(card, Tokens(white=1), Tokens(gold=3))


def test_can_afford_card_does_not_require_a_bonus_for_ordinary_cards():
    card = make_card(cost=Tokens(white=1))
    assert can_afford_card(card, Tokens(), Tokens(white=1))


# --- legal_payments ------------------------------------------------------


def test_legal_payments_uses_minimum_gold_per_combination():
    card = make_card(cost=Tokens(white=2))
    result = legal_payments(card, Tokens(), Tokens(white=2, gold=3))
    assert Counter(result) == Counter(
        [
            Tokens(gold=2),
            Tokens(white=1, gold=1),
            Tokens(white=2),
        ]
    )


def test_legal_payments_covers_a_shortfall_with_gold():
    card = make_card(cost=Tokens(white=3))
    assert legal_payments(card, Tokens(), Tokens(white=2, gold=1)) == [
        Tokens(white=2, gold=1)
    ]


def test_legal_payments_is_empty_when_the_card_is_unaffordable():
    card = make_card(cost=Tokens(white=5))
    assert legal_payments(card, Tokens(), Tokens(white=1, gold=1)) == []


def test_legal_payments_applies_a_bonus_to_the_cost():
    card = make_card(cost=Tokens(white=3))
    assert legal_payments(card, Tokens(white=1), Tokens(gold=2)) == [Tokens(gold=2)]


def test_legal_payments_covers_a_pearl_cost_partly_with_gold():
    card = make_card(cost=Tokens(pearl=2))
    assert legal_payments(card, Tokens(), Tokens(pearl=1, gold=1)) == [
        Tokens(pearl=1, gold=1)
    ]


def test_legal_payments_gold_always_equals_the_cost_deficits_it_leaves_open():
    positions = [
        # (cost, bonus, tokens, is_multicolor)
        (Tokens(white=2), Tokens(), Tokens(white=2, gold=3), False),
        (Tokens(white=3), Tokens(), Tokens(white=2, gold=1), False),
        (Tokens(white=5), Tokens(), Tokens(white=1, gold=1), False),
        (Tokens(white=3), Tokens(white=1), Tokens(gold=2), False),
        (Tokens(white=3), Tokens(white=1), Tokens(gold=3), True),
        (Tokens(pearl=2), Tokens(), Tokens(pearl=1, gold=1), False),
        (
            Tokens(white=2, blue=2, pearl=1),
            Tokens(),
            Tokens(white=3, blue=1, pearl=2, gold=4),
            False,
        ),
        (
            Tokens(white=1, red=2, black=1),
            Tokens(red=1),
            Tokens(white=2, red=3, black=1, pearl=1, gold=2),
            False,
        ),
    ]
    for cost, bonus, tokens, is_multicolor in positions:
        card = make_card(
            cost=cost,
            is_multicolor=is_multicolor,
            bonus_count=1 if is_multicolor else 0,
        )
        payments = legal_payments(card, bonus, tokens)
        assert bool(payments) == can_afford_card(card, bonus, tokens)
        for payment in payments:
            assert payment.gold == cost_deficits(card.cost, bonus, payment).total()


# --- is_winner -----------------------------------------------------------


def _make_player(
    prestige: int = 0,
    crowns: int = 0,
    purchased: tuple[PurchasedCard, ...] = (),
    tokens: Tokens | None = None,
) -> PlayerState:
    """Build a minimal player state for winner tests."""
    return PlayerState(
        tokens=tokens if tokens is not None else Tokens(),
        bonus=Tokens(),
        prestige=prestige,
        crowns=crowns,
        reserved=(),
        purchased=purchased,
        privileges=0,
    )


def test_is_winner_prestige_win():
    player = _make_player(prestige=20)
    assert is_winner(player) is True

    player = _make_player(prestige=19)
    assert is_winner(player) is False


def test_is_winner_crowns_win():
    player = _make_player(crowns=10)
    assert is_winner(player) is True

    player = _make_player(crowns=9)
    assert is_winner(player) is False


def test_is_winner_color_win():
    purchased = (
        PurchasedCard(
            card=make_card("C1", points=5, bonus=Color.WHITE), chosen_color=None
        ),
        PurchasedCard(
            card=make_card("C2", points=5, bonus=Color.WHITE), chosen_color=None
        ),
    )
    player = _make_player(purchased=purchased)
    assert is_winner(player) is True


def test_is_winner_color_win_with_multicolor():
    purchased = (
        PurchasedCard(
            card=make_card("M1", points=5, is_multicolor=True, bonus_count=1),
            chosen_color=Color.WHITE,
        ),
        PurchasedCard(
            card=make_card("C2", points=5, bonus=Color.WHITE), chosen_color=None
        ),
    )
    player = _make_player(purchased=purchased)
    assert is_winner(player) is True


def test_is_winner_multicolor_not_counted_without_chosen_color():
    purchased = (
        PurchasedCard(
            card=make_card("M1", points=5, is_multicolor=True, bonus_count=1),
            chosen_color=None,  # Not chosen yet
        ),
    )
    player = _make_player(purchased=purchased)
    assert is_winner(player) is False


def test_is_winner_color_win_only_counts_card_points_not_bonus():
    purchased = (
        PurchasedCard(
            card=make_card("C1", points=5, bonus=Color.WHITE), chosen_color=None
        ),
    )
    # Player has bonus tokens (from other cards), but only card points count
    player = PlayerState(
        tokens=Tokens(),
        bonus=Tokens(white=5),  # 5 bonus tokens in white
        prestige=5,
        crowns=0,
        reserved=(),
        purchased=purchased,
        privileges=0,
    )
    # Only 5 card points in white, not 10 (bonus tokens don't count)
    assert is_winner(player) is False


def test_is_winner_no_win():
    player = _make_player(prestige=15, crowns=5)
    assert is_winner(player) is False
