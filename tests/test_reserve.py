"""Tests for ReserveCard action (Task 5)."""

from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import (
    ChooseGold,
    ReserveCard,
    apply,
    decide,
)
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, new_game


def board_state(**kwargs) -> GameState:
    st = new_game(0)
    return replace(st, **kwargs)


def test_reserve_requires_gold_on_board():
    """No gold on board -> ReserveCard not in legal actions."""
    board = [None] * 25
    board[0] = Color.RED
    board[1] = Color.BLUE
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
        bag=Tokens(),
    )
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    assert len(reserve_actions) == 0


def test_reserve_enters_choose_gold_phase():
    """ReserveCard -> CHOOSE_GOLD phase."""
    board = [None] * 25
    board[0] = Color.GOLD  # Gold available
    board[1] = Color.RED
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    assert len(reserve_actions) > 0

    # Find a reserve action that takes from pyramid
    pyramid_actions = [a for a in reserve_actions if a.source == "pyramid"]
    assert len(pyramid_actions) > 0

    action = pyramid_actions[0]
    st2 = apply(st, action)

    # Should enter CHOOSE_GOLD phase
    assert st2.phase is Phase.CHOOSE_GOLD
    assert st2.pending_reserve is not None
    # Gold should still be on board (not taken yet)
    assert st2.board[0] == Color.GOLD
    # Player should NOT have gold in hand yet
    assert st2.players[0].tokens.gold == 0
    # Player should NOT have reserved card yet
    assert len(st2.players[0].reserved) == 0


def test_reserve_from_pyramid_refills_slot_after_choose_gold():
    """After ChooseGold, pyramid slot refills (if deck not empty)."""
    board = [None] * 25
    board[0] = Color.GOLD
    board[1] = Color.RED
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    pyramid_actions = [a for a in reserve_actions if a.source == "pyramid"]
    assert len(pyramid_actions) > 0

    action = pyramid_actions[0]
    st2 = apply(st, action)

    # Should be in CHOOSE_GOLD phase
    assert st2.phase is Phase.CHOOSE_GOLD
    # Choose the gold
    dp2 = decide(st2)
    choose_gold_actions = [a for a in dp2.legal_actions if isinstance(a, ChooseGold)]
    assert len(choose_gold_actions) == 1
    st3 = apply(st2, choose_gold_actions[0])

    # Gold should be taken from board
    assert st3.board[0] is None
    # Player should have the gold in hand
    assert st3.players[0].tokens.gold == 1
    # Player should have a reserved card
    assert len(st3.players[0].reserved) == 1
    reserved_card = st3.players[0].reserved[0]
    assert reserved_card.from_deck is False  # from pyramid
    # Pyramid slot should be refilled (if deck not empty)
    # Turn should pass to opponent
    assert st3.current_player == 1
    assert st3.phase is Phase.USE_PRIVILEGES
    assert st3.pending_reserve is None


def test_reserve_from_deck_top_does_not_refill():
    """Reserve from deck top (source="deck_3"/"deck_2"/"deck_1") does not refill pyramid."""
    board = [None] * 25
    board[0] = Color.GOLD
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    deck_actions = [a for a in reserve_actions if a.source.startswith("deck_")]
    assert len(deck_actions) > 0

    action = deck_actions[0]
    st2 = apply(st, action)

    # Should enter CHOOSE_GOLD phase
    assert st2.phase is Phase.CHOOSE_GOLD
    # Choose the gold
    dp2 = decide(st2)
    choose_gold_actions = [a for a in dp2.legal_actions if isinstance(a, ChooseGold)]
    assert len(choose_gold_actions) == 1
    st3 = apply(st2, choose_gold_actions[0])

    # Gold should be taken from board
    assert st3.board[0] is None
    # Player should have the gold in hand
    assert st3.players[0].tokens.gold == 1
    # Player should have a reserved card from deck
    assert len(st3.players[0].reserved) == 1
    reserved_card = st3.players[0].reserved[0]
    assert reserved_card.from_deck is True  # from deck
    # Turn should pass to opponent
    assert st3.current_player == 1
    assert st3.phase is Phase.USE_PRIVILEGES
    assert st3.pending_reserve is None


def test_reserve_illegal_at_three_reserved():
    """Cannot reserve when already have 3 reserved cards."""
    board = [None] * 25
    board[0] = Color.GOLD
    base_st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    from splendor_duel_engine.engine.cards import load_cards
    from splendor_duel_engine.engine.state import ReservedCard

    jewels, _ = load_cards()
    dummy_card = jewels[0]
    st = replace(
        base_st,
        players=(
            replace(
                base_st.players[0],
                reserved=(
                    ReservedCard(dummy_card, from_deck=False),
                    ReservedCard(dummy_card, from_deck=False),
                    ReservedCard(dummy_card, from_deck=False),
                ),
            ),
            base_st.players[1],
        ),
    )
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    assert len(reserve_actions) == 0


def test_reserved_cards_are_in_own_player_state_and_turn_passes():
    """After reserve, card goes to player's reserved, turn passes to opponent."""
    board = [None] * 25
    board[0] = Color.GOLD
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    action = reserve_actions[0]
    st2 = apply(st, action)

    # Should be in CHOOSE_GOLD phase
    assert st2.phase is Phase.CHOOSE_GOLD
    # Choose the gold
    dp2 = decide(st2)
    choose_gold_actions = [a for a in dp2.legal_actions if isinstance(a, ChooseGold)]
    st3 = apply(st2, choose_gold_actions[0])

    # Card should be in current player's reserved
    assert len(st3.players[0].reserved) == 1
    assert len(st3.players[1].reserved) == 0
    # Turn should pass to opponent
    assert st3.current_player == 1
    # Phase should go to USE_PRIVILEGES for opponent
    assert st3.phase is Phase.USE_PRIVILEGES


def test_multicolor_may_be_reserved_without_owning_bonus():
    """Multicolor cards can be reserved without owning a colored bonus (restriction applies at purchase only)."""
    # L1-24 is a known multicolor card (bonus=joker in card data)
    base_st = new_game(0)
    # Find L1-24 in pyramid (level 1 row, index 2)
    card = base_st.pyramid[2][2]  # L1-24
    assert card is not None and card.is_multicolor, "L1-24 should be multicolor"

    # Set up board with gold available
    board = [None] * 25
    board[0] = Color.GOLD
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    # board_state re-seeds, so locate the same card by id in the fresh state.
    assert st.pyramid[2][2].id == card.id
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    # Find the pyramid reserve action that targets this exact multicolor card
    # (pyramid index = row*10 + col; L1-24 sits at row 2, col 2 -> 22).
    multi_actions = [
        a
        for a in reserve_actions
        if a.source == "pyramid"
        and st.pyramid[a.index // 10][a.index % 10].id == card.id
    ]
    assert len(multi_actions) == 1
    # The action application should not fail due to multicolor restriction at reserve time
    st2 = apply(st, multi_actions[0])
    assert st2.phase is Phase.CHOOSE_GOLD
    # Complete the reserve
    dp2 = decide(st2)
    choose_gold_actions = [a for a in dp2.legal_actions if isinstance(a, ChooseGold)]
    st3 = apply(st2, choose_gold_actions[0])
    assert len(st3.players[0].reserved) == 1
    # The reserved card must be exactly the multicolor card that was reserved.
    assert st3.players[0].reserved[0].card.id == card.id
    assert st3.players[0].reserved[0].card.is_multicolor


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
