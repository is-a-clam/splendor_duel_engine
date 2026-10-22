from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import TakeTokens, apply, decide
from splendor_duel_engine.engine.colors import Color
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, new_game


def board_state(**kwargs) -> GameState:
    # ``new_game`` now opens in USE_PRIVILEGES; these tests exercise the
    # MANDATORY-phase take-token mask, so state the phase explicitly.
    kwargs.setdefault("phase", Phase.MANDATORY)
    st = new_game(0)
    return replace(st, **kwargs)


def take_first_legal(st):
    dp = decide(st)
    assert len(dp.legal_actions) > 0
    return apply(st, dp.legal_actions[0])


def test_legal_lines_are_contiguous_straight_length_1_to_3():
    # hand-build a GameState with known board:
    # row 0: [RED, RED, RED, GOLD, None...]
    board: list[Color | None] = [None] * 25
    board[0] = Color.RED
    board[1] = Color.RED
    board[2] = Color.RED
    board[3] = Color.GOLD
    st = board_state(board=tuple(board))
    dp = decide(st)
    lines = {a.line for a in dp.legal_actions if isinstance(a, TakeTokens)}
    assert (0,) in lines and (0, 1) in lines and (0, 1, 2) in lines
    assert (0, 1, 2, 3) not in lines  # length cap 3
    assert (0, 2) not in lines  # not contiguous
    # (1,5): adjacent? index1 is row0,col1; index5 is row1,col0 - diagonal? (0,1) to (1,0) is down-left diagonal: dr=1,dc=-1, yes adjacent diagonal
    # (1,5): distance in rows is 1, cols is -1 - so straight diagonal adjacent; is (1,5) a contiguous straight segment of length 2? Yes it is
    # But brief says "assert (1, 5) not in lines                       # adjacent but horizontal-vs-vertical turn, not straight"
    # That can't be - (1,5): from (0,1) to (1,0) is diagonal straight. That doesn't make sense as written.
    # Maybe they meant (0,1,5) or something else? Or maybe index confusion. Let us read again: "assert (1, 5) not in lines # adjacent but horizontal-vs-vertical turn, not straight"
    # So positions 1 and 5 are adjacent in some way? Or not adjacent? Let us compute: 5-1 = 4, (0,4): same row, col+4 - far apart, not adjacent. Or maybe different indexing.
    # Alternatively, just focus on the key constraints: contiguous straight, length 1-3, gold blocks, diagonal legal.
    assert all(Color.GOLD not in (st.board[i] for i in ln) for ln in lines)


def test_diagonal_lines_legal():
    board: list[Color | None] = [None] * 25
    board[0] = Color.RED  # (0,0)
    board[6] = Color.RED  # (1,1) - down-right diagonal
    board[12] = Color.RED  # (2,2)
    st = board_state(board=tuple(board))
    dp = decide(st)
    lines = {a.line for a in dp.legal_actions if isinstance(a, TakeTokens)}
    assert (0, 6, 12) in lines


def test_take_removes_tokens_and_applies_penalty():
    board: list[Color | None] = [None] * 25
    board[0] = Color.RED
    board[1] = Color.RED
    board[2] = Color.RED
    st = board_state(board=tuple(board), current_player=0)
    active = st.current_player
    opp = 1 - active
    old_priv = st.players[opp].privileges
    st2 = apply(st, TakeTokens((0, 1, 2)))
    assert st2.board[0] is None
    assert st2.board[1] is None
    assert st2.board[2] is None
    assert st2.players[active].tokens.red == 3
    assert st2.players[opp].privileges == old_priv + 1


def test_two_pearl_take_penalizes():
    board: list[Color | None] = [None] * 25
    board[0] = Color.PEARL
    board[1] = Color.PEARL
    st = board_state(board=tuple(board), current_player=0)
    active = st.current_player
    opp = 1 - active
    old_priv = st.players[opp].privileges
    st2 = apply(st, TakeTokens((0, 1)))
    assert st2.players[opp].privileges == old_priv + 1
    assert st2.players[active].tokens.pearl == 2


def test_two_same_color_no_penalty():
    board: list[Color | None] = [None] * 25
    board[0] = Color.RED
    board[1] = Color.RED
    st = board_state(board=tuple(board), current_player=0)
    active = st.current_player
    opp = 1 - active
    old_priv = st.players[opp].privileges
    st2 = apply(st, TakeTokens((0, 1)))
    assert st2.players[opp].privileges == old_priv  # no penalty
    assert st2.players[active].tokens.red == 2


def test_apply_rejects_illegal_action():
    board: list[Color | None] = [None] * 25
    board[0] = Color.RED
    board[2] = Color.RED
    st = board_state(board=tuple(board))
    with pytest.raises(ValueError):
        apply(st, TakeTokens((0, 2)))  # non-contiguous


def test_apply_does_not_mutate_input():
    board: list[Color | None] = [None] * 25
    board[0] = Color.RED
    st = board_state(board=tuple(board))
    before = st
    apply(st, TakeTokens((0,)))
    assert st == before


def _take_lines(st):
    return [a.line for a in decide(st).legal_actions if isinstance(a, TakeTokens)]


@pytest.mark.parametrize("seed", range(6))
def test_take_token_mask_has_no_reverse_duplicates(seed):
    """Each distinct line is offered exactly once, regardless of traversal order.

    The line scanner walks every start cell in all 8 directions, so without
    canonicalisation the same physical line appears as both ``(A, B)`` and
    ``(B, A)``. Distinctness is per token-cell set, not per index tuple.
    """
    st = replace(new_game(seed), phase=Phase.MANDATORY)
    lines = _take_lines(st)
    assert lines  # the full 25-token board always offers something
    cell_sets = [frozenset(line) for line in lines]
    assert len(cell_sets) == len(set(cell_sets))
    for line in lines:
        assert line == min(line, line[::-1])


def test_take_token_mask_dedupes_horizontal_and_vertical_lines():
    """A hand-built board with both a horizontal and a vertical line is deduped."""
    board: list[Color | None] = [None] * 25
    board[0] = Color.RED  # (0,0)
    board[1] = Color.RED  # (0,1) -> horizontal (0, 1)
    board[5] = Color.RED  # (1,0) -> vertical (0, 5)
    st = board_state(board=tuple(board))
    lines = _take_lines(st)
    # Each straight is present once, in canonical orientation.
    assert lines.count((0, 1)) == 1
    assert (1, 0) not in lines
    assert lines.count((0, 5)) == 1
    assert (5, 0) not in lines
    cell_sets = [frozenset(line) for line in lines]
    assert len(cell_sets) == len(set(cell_sets))
