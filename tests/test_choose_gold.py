"""Tests for CHOOSE_GOLD phase (Task 5 - new phase for reserve gold selection)."""

from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import (
    ChooseGold,
    ReserveCard,
    apply,
    decide,
)
from splendor_duel_engine.engine.colors import Color
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, new_game


def board_state(**kwargs) -> GameState:
    st = new_game(0)
    return replace(st, **kwargs)


def test_choose_gold_enumerates_all_gold_indices():
    """CHOOSE_GOLD phase enumerates ChooseGold(index) for each gold token on board."""
    # Set up board with multiple gold tokens
    board = [None] * 25
    board[0] = Color.GOLD
    board[5] = Color.GOLD
    board[10] = Color.GOLD
    board[15] = Color.RED  # Non-gold
    st = board_state(
        current_player=0,
        phase=Phase.CHOOSE_GOLD,
        board=tuple(board),
        # Need a pending_reserve action
        pending_reserve=ReserveCard(source="pyramid", index=0),
    )

    dp = decide(st)
    assert dp.phase is Phase.CHOOSE_GOLD

    choose_gold_actions = [a for a in dp.legal_actions if isinstance(a, ChooseGold)]
    assert len(choose_gold_actions) == 3

    # Actions should be for indices 0, 5, 10
    action_indices = {a.index for a in choose_gold_actions}
    assert action_indices == {0, 5, 10}


def test_choose_gold_takes_specific_gold_token():
    """ChooseGold(index) takes the specific gold token at that index."""
    board = [None] * 25
    board[0] = Color.GOLD
    board[5] = Color.GOLD
    board[10] = Color.GOLD
    st = board_state(
        current_player=0,
        phase=Phase.CHOOSE_GOLD,
        board=tuple(board),
        pending_reserve=ReserveCard(source="pyramid", index=0),
    )

    dp = decide(st)
    choose_gold_actions = [a for a in dp.legal_actions if isinstance(a, ChooseGold)]

    # Choose the gold at index 5
    action = next(a for a in choose_gold_actions if a.index == 5)
    st2 = apply(st, action)

    # Gold at index 5 should be gone
    assert st2.board[5] is None
    # Other golds should remain
    assert st2.board[0] == Color.GOLD
    assert st2.board[10] == Color.GOLD
    # Player should have 1 gold in hand
    assert st2.players[0].tokens.gold == 1


def test_choose_gold_completes_reserve_and_passes_turn():
    """After ChooseGold, reserve completes and turn passes to opponent."""
    board = [None] * 25
    board[0] = Color.GOLD
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )

    # First, do a ReserveCard action to enter CHOOSE_GOLD
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    pyramid_actions = [a for a in reserve_actions if a.source == "pyramid"]
    assert len(pyramid_actions) > 0

    st2 = apply(st, pyramid_actions[0])
    assert st2.phase is Phase.CHOOSE_GOLD
    assert st2.pending_reserve is not None

    # Now choose gold
    dp2 = decide(st2)
    choose_gold_actions = [a for a in dp2.legal_actions if isinstance(a, ChooseGold)]
    assert len(choose_gold_actions) == 1

    st3 = apply(st2, choose_gold_actions[0])

    # Gold should be taken
    assert st3.board[0] is None
    # Player should have gold in hand
    assert st3.players[0].tokens.gold == 1
    # Player should have reserved card
    assert len(st3.players[0].reserved) == 1
    # Turn should pass to opponent
    assert st3.current_player == 1
    # Phase should be USE_PRIVILEGES for opponent
    assert st3.phase is Phase.USE_PRIVILEGES
    # pending_reserve should be cleared
    assert st3.pending_reserve is None


def test_choose_gold_invalid_index_raises():
    """Choosing an index without gold raises ValueError."""
    board = [None] * 25
    board[0] = Color.GOLD
    board[5] = Color.RED  # Not gold
    st = board_state(
        current_player=0,
        phase=Phase.CHOOSE_GOLD,
        board=tuple(board),
        pending_reserve=ReserveCard(source="pyramid", index=0),
    )

    dp = decide(st)
    # Only index 0 should be legal
    choose_gold_actions = [a for a in dp.legal_actions if isinstance(a, ChooseGold)]
    assert len(choose_gold_actions) == 1
    assert choose_gold_actions[0].index == 0

    # Applying an action with index 5 should fail (not in legal_actions)
    with pytest.raises(ValueError, match="illegal action"):
        apply(st, ChooseGold(index=5))


def test_choose_gold_pyramid_refills():
    """After completing reserve from pyramid, the slot refills from deck."""
    base_st = new_game(0)
    # Ensure gold on board
    board = list(base_st.board)
    board[0] = Color.GOLD
    st = replace(base_st, board=tuple(board), current_player=0, phase=Phase.MANDATORY)

    # Reserve from pyramid level 3 (row 0)
    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    pyramid_l3_actions = [
        a for a in reserve_actions if a.source == "pyramid" and a.index // 10 == 0
    ]
    assert len(pyramid_l3_actions) > 0

    action = pyramid_l3_actions[0]
    row_idx = action.index // 10
    col_idx = action.index % 10
    original_card = st.pyramid[row_idx][col_idx]
    assert original_card is not None

    st2 = apply(st, action)
    st3 = apply(st2, decide(st2).legal_actions[0])  # ChooseGold

    # Pyramid slot should be refilled (deck not empty)
    assert st3.pyramid[row_idx][col_idx] is not None
    # New card should be different from original (since deck was shuffled)
    # Actually it could be the same by chance, but we just check it's not None


def test_choose_gold_deck_reserve_does_not_refill():
    """After completing reserve from deck, pyramid is unchanged."""
    base_st = new_game(0)
    board = list(base_st.board)
    board[0] = Color.GOLD
    st = replace(base_st, board=tuple(board), current_player=0, phase=Phase.MANDATORY)

    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    deck_actions = [a for a in reserve_actions if a.source.startswith("deck_")]
    assert len(deck_actions) > 0

    action = deck_actions[0]
    old_pyramid = st.pyramid

    st2 = apply(st, action)
    st3 = apply(st2, decide(st2).legal_actions[0])  # ChooseGold

    # Pyramid should be unchanged
    assert st3.pyramid == old_pyramid
    # Player should have a reserved card from deck
    assert len(st3.players[0].reserved) == 1
    assert st3.players[0].reserved[0].from_deck is True


def test_choose_gold_with_multiple_gold_allows_choice():
    """Player can choose which gold token to take when multiple are available."""
    board = [None] * 25
    board[0] = Color.GOLD
    board[1] = Color.GOLD
    board[2] = Color.GOLD
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
    )

    dp = decide(st)
    reserve_actions = [a for a in dp.legal_actions if isinstance(a, ReserveCard)]
    assert len(reserve_actions) > 0

    st2 = apply(st, reserve_actions[0])
    assert st2.phase is Phase.CHOOSE_GOLD

    dp2 = decide(st2)
    choose_gold_actions = [a for a in dp2.legal_actions if isinstance(a, ChooseGold)]
    assert len(choose_gold_actions) == 3

    # Player can choose any of the three
    for action in choose_gold_actions:
        st3 = apply(st2, action)
        assert st3.board[action.index] is None
        assert st3.players[0].tokens.gold == 1
        # Other golds remain
        for other_idx in [0, 1, 2]:
            if other_idx != action.index:
                assert st3.board[other_idx] == Color.GOLD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
