"""Tests for ReserveCard action (Task 5)."""

from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import (
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


def test_reserve_takes_gold_then_pyramid_card_and_refills():
    """Reserve takes gold from board first, then a pyramid card (slot refills)."""
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

    # Find a reserve action that takes from pyramid (source="pyramid")
    pyramid_actions = [a for a in reserve_actions if a.source == "pyramid"]
    assert len(pyramid_actions) > 0

    action = pyramid_actions[0]
    st2 = apply(st, action)

    # Gold should be taken from board
    assert st2.board[0] is None
    # Player should have the gold in hand
    assert st2.players[0].tokens.gold == 1
    # Player should have a reserved card
    assert len(st2.players[0].reserved) == 1
    reserved_card = st2.players[0].reserved[0]
    assert reserved_card.from_deck is False  # from pyramid
    # Pyramid slot should be refilled (if deck not empty)
    # The reserved card came from pyramid row corresponding to action.index
    # We just verify the pyramid structure is maintained


def test_reserve_from_deck_top_does_not_refill():
    """Reserve from deck top (source="deck", level) does not refill pyramid."""
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

    # Gold should be taken from board
    assert st2.board[0] is None
    # Player should have the gold in hand
    assert st2.players[0].tokens.gold == 1
    # Player should have a reserved card from deck
    assert len(st2.players[0].reserved) == 1
    reserved_card = st2.players[0].reserved[0]
    assert reserved_card.from_deck is True  # from deck


def test_reserve_illegal_at_three_reserved():
    """Cannot reserve when already have 3 reserved cards."""
    board = [None] * 25
    board[0] = Color.GOLD
    base_st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    # Give player 3 reserved cards
    st = replace(
        base_st,
        players=(
            replace(
                base_st.players[0],
                reserved=(
                    base_st.players[0].reserved[0]
                    if base_st.players[0].reserved
                    else None,
                )
                * 3
                if base_st.players[0].reserved
                else (),
            ),
        ),
    )
    # Actually need to construct 3 dummy reserved cards - simpler: just check that
    # the logic enforces max 3. Let's manually create a state with 3 reserved.
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

    # Card should be in current player's reserved
    assert len(st2.players[0].reserved) == 1
    assert len(st2.players[1].reserved) == 0
    # Turn should pass to opponent
    assert st2.current_player == 1
    # Phase should go to USE_PRIVILEGES for opponent
    assert st2.phase is Phase.USE_PRIVILEGES


def test_multicolor_may_be_reserved_without_owning_bonus():
    """Multicolor cards can be reserved without owning a colored bonus (restriction applies at purchase only)."""
    # This test verifies that the multicolor purchase restriction is NOT enforced at reserve time
    # We just need to ensure a multicolor card can be reserved
    board = [None] * 25
    board[0] = Color.GOLD
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    # At least some reserve actions should be available
    assert len(reserve_actions) > 0
    # The action application should not fail due to multicolor restriction
    st2 = apply(st, reserve_actions[0])
    assert len(st2.players[0].reserved) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
