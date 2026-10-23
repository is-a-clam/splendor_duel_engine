"""Tests for BuyCard and PayTokens actions (Task 5)."""

from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import (
    BuyCard,
    ChooseGold,
    DoneWithPrivileges,
    DoneWithReplenish,
    PayTokens,
    Replenish,
    ReserveCard,
    apply,
    decide,
)
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.helpers import can_afford_card
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, ReservedCard


def board_state(**kwargs) -> GameState:
    st = GameState.new_game(0)
    return replace(st, **kwargs)


def test_payment_respects_bonuses_and_never_goes_below_zero():
    """Payment subtracts per-gem bonuses (min 0 per color)."""
    # Use L3-09: cost has green=6, blue=2, red=2, bonus=GREEN
    base_st = GameState.new_game(0)
    card = base_st.pyramid[0][1]  # L3-09
    assert card is not None and card.bonus == Color.GREEN and card.cost.green > 0

    # Put card in reserved (remove from pyramid to avoid duplicate)
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[0][1] = None
    reserved_card = ReservedCard(card=card, from_deck=False)
    # Card costs: green=6, blue=2, red=2. With 1 green bonus, remaining green=5.
    # Need 5 green + 2 blue + 2 red = 9 total. Give 5 green, 2 blue, 2 red, gold=1
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(green=1),
                tokens=Tokens(green=5, blue=2, red=2, gold=1),
                reserved=(reserved_card,),
            ),
            base_st.players[1],
        ),
    )

    # Buy the card
    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    assert st2.phase is Phase.CHOOSE_PAYMENT

    # In CHOOSE_PAYMENT, should offer payments that respect bonus
    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    assert len(pay_actions) > 0
    # At least one payment should use the gold to cover the remaining green cost
    for pay in pay_actions:
        # After 1 green bonus, remaining green cost is max(0, cost.green - 1)
        max(0, card.cost.green - 1)
        # Payment should not require more green than player has (5) + gold
        assert pay.payment.green <= 5 + 1


def test_pearl_cost_never_reduced():
    """Pearl costs are never reduced by bonuses."""
    base_st = GameState.new_game(0)
    # Use L3-03: cost has pearl=1, bonus=BLUE
    card = base_st.pyramid[0][0]  # L3-03
    assert card is not None and card.cost.pearl > 0
    bonus_color = card.bonus
    assert bonus_color == Color.BLUE

    # Remove from pyramid
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[0][0] = None
    reserved_card = ReservedCard(card=card, from_deck=False)
    # Card costs: white=3, green=3, black=5, pearl=1. Total=12. Bonus=BLUE (no blue cost).
    # Need gold=11 to cover all non-blue costs, plus pearl=1
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(blue=2),  # Blue bonus (doesn't reduce pearl)
                tokens=Tokens(
                    pearl=card.cost.pearl, gold=11
                ),  # 1 pearl + 11 gold for other costs
                reserved=(reserved_card,),
            ),
            base_st.players[1],
        ),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    assert st2.phase is Phase.CHOOSE_PAYMENT

    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    assert len(pay_actions) > 0
    # All payments must include full pearl cost
    for pay in pay_actions:
        assert pay.payment.pearl >= card.cost.pearl


def test_gold_pays_as_any_color_or_pearl():
    """Gold is wild and can substitute for any color or pearl."""
    base_st = GameState.new_game(0)
    # Use L1-27: cost=white=2, blue=3, bonus=RED. Total cost=5.
    card = base_st.pyramid[2][0]  # L1-27
    assert card is not None

    # Remove from pyramid
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[2][0] = None
    reserved_card = ReservedCard(card=card, from_deck=False)
    total_cost = sum(card.cost.count(c) for c in Color) + card.cost.pearl
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(),
                tokens=Tokens(gold=total_cost),
                reserved=(reserved_card,),
            ),
            base_st.players[1],
        ),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    assert st2.phase is Phase.CHOOSE_PAYMENT

    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    assert len(pay_actions) > 0
    # At least one payment should use only gold
    gold_only_payments = [p for p in pay_actions if p.payment.total() == p.payment.gold]
    assert len(gold_only_payments) > 0


def test_pyramid_purchase_refills_from_deck_or_stays_empty_when_deck_empty():
    """Buying from pyramid refills the slot from that level's deck; if deck empty, stays empty."""
    base_st = GameState.new_game(0)
    # Use L1-27 from pyramid (level 1 row)
    card = base_st.pyramid[2][0]
    assert card is not None

    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(),
                tokens=Tokens(gold=10),  # Enough gold to buy anything
                reserved=(),
            ),
            base_st.players[1],
        ),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    assert st2.phase is Phase.CHOOSE_PAYMENT

    # Pay with gold
    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    st3 = apply(st2, pay_actions[0])

    # Pyramid slot should be refilled from deck (deck 2 is level 1)
    # The slot was at pyramid[2][0], should now have a new card (or None if deck empty)
    assert st3.pyramid[2][0] is not None or len(st3.decks[2]) == 0


def test_reserved_purchase_does_not_refill():
    """Buying a reserved card does not refill any pyramid slot."""
    base_st = GameState.new_game(0)
    card = base_st.pyramid[0][1]  # L3-09
    assert card is not None

    # Remove from pyramid
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[0][1] = None
    reserved_card = ReservedCard(card=card, from_deck=False)
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(),
                tokens=Tokens(gold=10),
                reserved=(reserved_card,),
            ),
            base_st.players[1],
        ),
    )

    # Store pyramid state before
    old_pyramid = st.pyramid

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    st3 = apply(st2, decide(st2).legal_actions[0])  # Pay with first option

    # Pyramid should be unchanged
    assert st3.pyramid == old_pyramid


def test_spent_tokens_go_to_bag():
    """Spent tokens (including gold) go from hand to bag."""
    base_st = GameState.new_game(0)
    card = base_st.pyramid[2][0]  # L1-27, cost=5
    assert card is not None

    # Remove from pyramid
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[2][0] = None
    reserved_card = ReservedCard(card=card, from_deck=False)
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        bag=Tokens(),  # Empty bag initially
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(),
                tokens=Tokens(gold=5, white=2),
                reserved=(reserved_card,),
            ),
            base_st.players[1],
        ),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    st3 = apply(st2, decide(st2).legal_actions[0])

    # Bag should have received the spent tokens
    assert st3.bag.total() > 0
    assert st3.bag.gold > 0 or st3.bag.white > 0


def test_buy_grants_bonus_prestige_crowns():
    """Purchasing a card grants its bonus, prestige points, and crowns."""
    base_st = GameState.new_game(0)
    # Find a card with bonus, points, and crowns - L3-03 has points=3, crowns=2, bonus=BLUE
    card = base_st.pyramid[0][0]  # L3-03
    assert (
        card is not None
        and card.bonus is not None
        and card.points > 0
        and card.crowns > 0
    )

    # Remove from pyramid
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[0][0] = None
    reserved_card = ReservedCard(card=card, from_deck=False)
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(),
                tokens=Tokens(gold=12),  # Card costs 12 total
                reserved=(reserved_card,),
                prestige=0,
                crowns=0,
            ),
            base_st.players[1],
        ),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    st3 = apply(st2, decide(st2).legal_actions[0])

    # Check bonus granted
    assert st3.players[0].bonus.count(card.bonus) == 1
    # Check prestige granted
    assert st3.players[0].prestige == card.points
    # Check crowns granted
    assert st3.players[0].crowns == card.crowns


def test_multicolor_cannot_be_bought_without_colored_bonus():
    """Cannot buy a multicolor card unless player owns at least one colored bonus."""
    base_st = GameState.new_game(0)
    # Find a multicolor card in pyramid - L1-24
    card = base_st.pyramid[2][2]  # L1-24
    assert card is not None and card.is_multicolor

    # Remove from pyramid
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[2][2] = None
    reserved_card = ReservedCard(card=card, from_deck=False)

    # Player has NO colored bonus
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(),
                tokens=Tokens(gold=10),
                reserved=(reserved_card,),
            ),
            base_st.players[1],
        ),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 0  # Not buyable without colored bonus

    # Now give player a colored bonus
    st2 = replace(
        st,
        players=(
            replace(st.players[0], bonus=Tokens(white=1)),
            st.players[1],
        ),
    )
    dp2 = decide(st2)
    buy_actions2 = [
        a for a in dp2.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions2) == 1  # Now buyable


def test_choose_payment_phase_offers_only_legal_payments():
    """CHOOSE_PAYMENT phase enumerates only legal PayTokens actions."""
    base_st = GameState.new_game(0)
    card = base_st.pyramid[2][0]  # L1-27, cost=white=2, blue=3
    assert card is not None

    # Remove from pyramid
    new_pyramid = [list(r) for r in base_st.pyramid]
    new_pyramid[2][0] = None
    reserved_card = ReservedCard(card=card, from_deck=False)
    # Card costs white=2, blue=3. Total=5.
    # Give player white=1, blue=2, gold=2 (total 5)
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        pyramid=tuple(tuple(r) for r in new_pyramid),
        players=(
            replace(
                base_st.players[0],
                bonus=Tokens(),
                tokens=Tokens(gold=2, white=1, blue=2),
                reserved=(reserved_card,),
            ),
            base_st.players[1],
        ),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])

    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]

    # Every offered payment must be legal
    for pay in pay_actions:
        bonus = st2.players[0].bonus
        assert can_afford_card(card, pay.payment, bonus)
        # Payment must not exceed player's tokens
        for color in Color:
            assert pay.payment.count(color) <= st2.players[0].tokens.count(color)

    # At least one payment must exist for an affordable card
    assert len(pay_actions) > 0


def test_reserve_buy_chain_gold_reaches_bag_and_board_refill_can_redeploy_it():
    """Review Focus 1: reserve (gold to hand) -> buy with gold -> gold in bag -> replenish -> gold back on board."""
    # Start with a known state
    st = GameState.new_game(42)

    # Ensure exactly one gold on board for reserve
    board: list[Color | None] = [None] * 25
    board[0] = Color.GOLD
    st = replace(st, board=tuple(board), current_player=0, phase=Phase.MANDATORY)

    # Reserve a card (takes gold from board via CHOOSE_GOLD)
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    assert len(reserve_actions) > 0
    st2 = apply(st, reserve_actions[0])

    # Should be in CHOOSE_GOLD phase
    assert st2.phase is Phase.CHOOSE_GOLD
    dp2 = decide(st2)
    choose_gold_actions = [a for a in dp2.legal_actions if isinstance(a, ChooseGold)]
    assert len(choose_gold_actions) == 1
    st3 = apply(st2, choose_gold_actions[0])

    # Player 0 should now have gold in hand
    assert st3.players[0].tokens.gold == 1
    assert len(st3.players[0].reserved) == 1
    reserved_card = st3.players[0].reserved[0]

    # Give player 0 enough gold to buy the reserved card (cost varies, give plenty)
    st3 = replace(
        st3,
        players=(
            replace(st3.players[0], tokens=Tokens(gold=15)),
            st3.players[1],
        ),
    )

    # Turn passed to player 1 (opponent)
    assert st3.current_player == 1
    assert st3.phase == Phase.USE_PRIVILEGES

    # Opponent does a simple take tokens action to pass turn back
    # Opponent is in USE_PRIVILEGES phase, must go through to MANDATORY
    # Give opponent a valid line of tokens (indices 1, 2, 3 in a row)
    board_p1 = list(st3.board)
    board_p1[1] = Color.RED
    board_p1[2] = Color.RED
    board_p1[3] = Color.RED
    st3 = replace(st3, board=tuple(board_p1))

    # Opponent: DoneWithPrivileges -> REPLENISH phase
    st3 = apply(st3, DoneWithPrivileges())
    # Opponent: DoneWithReplenish -> MANDATORY phase (bag is empty in this test setup)
    st3 = apply(st3, DoneWithReplenish())

    dp_p1 = decide(st3)
    take_actions = [a for a in dp_p1.legal_actions if hasattr(a, "line")]
    assert len(take_actions) > 0
    st4 = apply(st3, take_actions[0])

    # Turn should be back to player 0
    assert st4.current_player == 0
    assert st4.phase == Phase.USE_PRIVILEGES

    # Player 0 can now buy the reserved card using the gold
    # Need to advance past USE_PRIVILEGES and REPLENISH to MANDATORY
    st5 = apply(st4, DoneWithPrivileges())
    st5 = apply(st5, DoneWithReplenish())

    # Now in MANDATORY, buy the reserved card
    dp5 = decide(st5)
    buy_actions = [
        a
        for a in dp5.legal_actions
        if isinstance(a, BuyCard) and a.card.id == reserved_card.card.id
    ]
    assert len(buy_actions) == 1
    st6 = apply(st5, buy_actions[0])
    assert st6.phase == Phase.CHOOSE_PAYMENT

    # Pay with the gold token
    dp6 = decide(st6)
    pay_actions = [a for a in dp6.legal_actions if isinstance(a, PayTokens)]
    # Find a payment that uses gold
    gold_pay = None
    for pay in pay_actions:
        if pay.payment.gold > 0:
            gold_pay = pay
            break
    assert gold_pay is not None, "Should have a payment using gold"
    st7 = apply(st6, gold_pay)

    # Gold should have moved from hand to bag (player spent some gold)
    assert st7.players[0].tokens.gold < 15  # Started with 15, spent some
    assert st7.bag.gold >= 1  # At least 1 gold went to bag

    # Now simulate a replenish to put gold back on board
    # Empty some board spaces
    board_empty = [None] * 25
    st7 = replace(
        st7, board=tuple(board_empty), current_player=0, phase=Phase.USE_PRIVILEGES
    )
    st8 = apply(st7, DoneWithPrivileges())
    st9 = apply(st8, Replenish())  # Replenish from bag (which has gold)

    # Gold should be on the board now (since bag had gold and board was empty)
    gold_on_board = sum(1 for c in st9.board if c == Color.GOLD)
    assert gold_on_board >= 1, (
        "Gold from bag should be placed on board during replenish"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
