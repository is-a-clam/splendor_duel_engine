"""Tests for privilege usage, replenish, and forced replenish (Task 4)."""

from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import (
    DoneWithPrivileges,
    DoneWithReplenish,
    Replenish,
    TakeTokens,
    UsePrivilege,
    apply,
    decide,
)
from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, new_game


def board_state(**kwargs) -> GameState:
    st = new_game(0)
    return replace(st, **kwargs)


def test_use_privilege_takes_one_chosen_non_gold_board_token():
    # Player holds 1 privilege
    st = board_state(current_player=0, phase=Phase.USE_PRIVILEGES)
    # Find a non-gold token on board
    non_gold_idx = next(i for i, c in enumerate(st.board) if c is not None and c != Color.GOLD)
    token_color = st.board[non_gold_idx]
    assert token_color is not None

    dp = decide(st)
    assert dp.phase is Phase.USE_PRIVILEGES
    take_actions = [a for a in dp.legal_actions if isinstance(a, UsePrivilege)]
    assert len(take_actions) > 0
    assert Color.GOLD not in {a.color for a in take_actions}

    # Take the token
    chosen_action = next(a for a in take_actions if a.color == token_color)
    st2 = apply(st, chosen_action)
    assert st2.players[0].privileges == 0
    assert st2.players[0].tokens.count(token_color) == 1
    assert st2.board[non_gold_idx] is None
    # Should advance to REPLENISH phase
    assert st2.phase is Phase.REPLENISH


def test_multiple_privileges_used_one_at_a_time():
    # Player with 2 privileges
    base_st = board_state(current_player=0, phase=Phase.USE_PRIVILEGES)
    st = board_state(
        current_player=0,
        phase=Phase.USE_PRIVILEGES,
        players=(
            replace(base_st.players[0], privileges=2),
            base_st.players[1],
        ),
    )
    # Find two non-gold tokens
    non_gold_indices = [i for i, c in enumerate(st.board) if c is not None and c != Color.GOLD]
    assert len(non_gold_indices) >= 2

    # First privilege use
    dp1 = decide(st)
    take1 = next(a for a in dp1.legal_actions if isinstance(a, UsePrivilege) and a.color == st.board[non_gold_indices[0]])
    st2 = apply(st, take1)
    assert st2.players[0].privileges == 1
    assert st2.phase is Phase.USE_PRIVILEGES  # Still in USE_PRIVILEGES

    # Second privilege use
    dp2 = decide(st2)
    take2 = next(a for a in dp2.legal_actions if isinstance(a, UsePrivilege) and a.color == st2.board[non_gold_indices[1]])
    st3 = apply(st2, take2)
    assert st3.players[0].privileges == 0
    assert st3.phase is Phase.REPLENISH


def test_done_with_privileges_advances_to_replenish():
    # Bag non-empty -> REPLENISH phase with both Replenish and DoneWithReplenish legal
    st = board_state(current_player=0, phase=Phase.USE_PRIVILEGES, bag=Tokens(white=1))
    dp = decide(st)
    assert dp.phase is Phase.USE_PRIVILEGES

    st2 = apply(st, DoneWithPrivileges())
    dp2 = decide(st2)
    assert dp2.phase is Phase.REPLENISH
    action_types = {type(a) for a in dp2.legal_actions}
    assert Replenish in action_types
    assert DoneWithReplenish in action_types


def test_replenish_fills_from_bag_along_spiral_and_grants_opponent_privilege():
    # Board with 3 empty slots, bag with 3 tokens
    # We need to create a specific board state
    empty_board = [None] * 25
    # Fill some slots
    for i, idx in enumerate(SPIRAL[:22]):  # First 22 filled
        empty_board[idx] = list(GEM_COLORS)[i % 5]
    # Last 3 empty (along spiral: indices SPIRAL[22], SPIRAL[23], SPIRAL[24])
    bag = Tokens(white=1, blue=1, green=1)

    st = board_state(
        current_player=0,
        phase=Phase.REPLENISH,
        board=tuple(empty_board),
        bag=bag,
    )
    old_opp_priv = st.players[1].privileges

    st2 = apply(st, Replenish())
    filled = [i for i in SPIRAL if st.board[i] is None][:3]
    assert all(st2.board[i] is not None for i in filled)
    assert st2.bag.total() == 0
    assert st2.players[1].privileges == old_opp_priv + 1
    # After replenish, should advance to MANDATORY
    assert st2.phase is Phase.MANDATORY


def test_replenish_illegal_when_bag_empty():
    st = board_state(
        current_player=0,
        phase=Phase.REPLENISH,
        bag=Tokens(),
    )
    dp = decide(st)
    assert not any(isinstance(a, Replenish) for a in dp.legal_actions)
    # Only DoneWithReplenish should be legal
    action_types = {type(a) for a in dp.legal_actions}
    assert action_types == {DoneWithReplenish}


def test_forced_replenish_when_no_mandatory_action():
    # Construct: nothing affordable, no gold on board, bag non-empty, board almost empty
    # We need a state in MANDATORY phase with no legal take actions (gold blocks or empty)
    # and bag non-empty -> should be forced to REPLENISH
    board = [None] * 25
    board[0] = Color.GOLD  # Gold blocks
    board[1] = Color.GOLD
    bag = Tokens(white=1)
    base_st = board_state(current_player=0, phase=Phase.MANDATORY, board=tuple(board), bag=bag)
    st = replace(base_st, players=(replace(base_st.players[0], tokens=Tokens()), base_st.players[1]))
    dp = decide(st)
    assert dp.phase is Phase.REPLENISH
    assert [type(a) for a in dp.legal_actions] == [Replenish]


def test_forced_replenish_not_triggered_when_take_available():
    # If there's a legal take action, we should be in MANDATORY not REPLENISH
    board = [None] * 25
    board[0] = Color.RED
    bag = Tokens(white=1)
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
        bag=bag,
    )
    dp = decide(st)
    assert dp.phase is Phase.MANDATORY
    assert any(isinstance(a, TakeTokens) for a in dp.legal_actions)


def test_done_with_replenish_advances_to_mandatory():
    # After choosing not to replenish (or bag empty), should go to MANDATORY
    st = board_state(
        current_player=0,
        phase=Phase.REPLENISH,
        bag=Tokens(),
    )
    st2 = apply(st, DoneWithReplenish())
    assert st2.phase is Phase.MANDATORY


def test_privilege_penalty_from_take_tokens_grants_opponent_privilege():
    # Test that taking 3 same-color or 2 pearls grants opponent privilege
    board = [None] * 25
    board[0] = Color.RED
    board[1] = Color.RED
    board[2] = Color.RED
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
        bag=Tokens(),
        privileges_supply=1,
    )
    opp = 1 - st.current_player
    old_opp_priv = st.players[opp].privileges

    st2 = apply(st, TakeTokens((0, 1, 2)))
    assert st2.players[opp].privileges == old_opp_priv + 1
    # Supply should be decremented
    assert st2.privileges_supply == 0


def test_privilege_penalty_steals_from_taker_when_supply_empty():
    # When supply is empty, penalty steals from the taker
    board = [None] * 25
    board[0] = Color.RED
    board[1] = Color.RED
    board[2] = Color.RED
    base_st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        board=tuple(board),
        bag=Tokens(),
        privileges_supply=0,
    )
    st = replace(
        base_st,
        players=(
            replace(base_st.players[0], privileges=1),  # Taker has 1 privilege
            replace(base_st.players[1], privileges=0),
        ),
    )
    opp = 1 - st.current_player

    st2 = apply(st, TakeTokens((0, 1, 2)))
    assert st2.players[opp].privileges == 1
    assert st2.players[st.current_player].privileges == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])