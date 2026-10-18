"""Game actions and decision logic (Step API).

Spec: docs/specs/splendor-duel-rules.md — Turn structure (A. Take tokens) and
Privileges (penalty source when supply empty).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.phase import Phase

# Board size
_BOARD_SIZE = 25

#: 8 directions (row-major steps) for straight lines on 5x5.
_DIRECTIONS_8 = (
    (1, 0),  # right
    (1, 1),  # down-right
    (0, 1),  # down
    (-1, 1),  # down-left
    (-1, 0),  # left
    (-1, -1),  # up-left
    (0, -1),  # up
    (1, -1),  # up-right
)


@dataclass(frozen=True, slots=True)
class UsePrivilege:
    color: Color


@dataclass(frozen=True, slots=True)
class DoneWithPrivileges:
    pass


@dataclass(frozen=True, slots=True)
class Replenish:
    pass


@dataclass(frozen=True, slots=True)
class DoneWithReplenish:
    pass


@dataclass(frozen=True, slots=True)
class TakeTokens:
    line: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.line, tuple):
            raise TypeError("line must be a tuple")
        for i in self.line:
            if not isinstance(i, int) or i < 0 or i >= _BOARD_SIZE:
                raise ValueError(f"invalid board index {i}")


@dataclass(frozen=True, slots=True)
class BuyCard:
    card_id: str


@dataclass(frozen=True, slots=True)
class PayTokens:
    payment: Tokens


@dataclass(frozen=True, slots=True)
class ReserveCard:
    source: str
    index: int


@dataclass(frozen=True, slots=True)
class ChooseMulticolor:
    color: Color


@dataclass(frozen=True, slots=True)
class ChooseStealToken:
    color: Color


@dataclass(frozen=True, slots=True)
class ChooseRoyal:
    royal_id: str


@dataclass(frozen=True, slots=True)
class DiscardTokens:
    tokens: Tokens


Action = (
    UsePrivilege
    | DoneWithPrivileges
    | Replenish
    | DoneWithReplenish
    | TakeTokens
    | BuyCard
    | PayTokens
    | ReserveCard
    | ChooseMulticolor
    | ChooseStealToken
    | ChooseRoyal
    | DiscardTokens
)


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    phase: Phase
    legal_actions: tuple[Action, ...]


def _index_to_rc(idx: int) -> tuple[int, int]:
    return idx // 5, idx % 5


def _rc_to_index(r: int, c: int) -> int | None:
    if r < 0 or r > 4 or c < 0 or c > 4:
        return None
    return r * 5 + c


def _is_straight_line(line: tuple[int, ...]) -> bool:
    if len(line) < 1 or len(line) > 3:
        return False
    if len(set(line)) != len(line):
        return False
    if len(line) == 1:
        return True
    dr0 = _index_to_rc(line[1])[0] - _index_to_rc(line[0])[0]
    dc0 = _index_to_rc(line[1])[1] - _index_to_rc(line[0])[1]
    if (dr0, dc0) not in _DIRECTIONS_8:
        return False
    for i in range(1, len(line)):
        dr = _index_to_rc(line[i])[0] - _index_to_rc(line[i - 1])[0]
        dc = _index_to_rc(line[i])[1] - _index_to_rc(line[i - 1])[1]
        if (dr, dc) != (dr0, dc0):
            return False
    return True


def _legal_take_token_lines(board: tuple[Color | None, ...]) -> list[tuple[int, ...]]:
    result: set[tuple[int, ...]] = set()
    for start in range(_BOARD_SIZE):
        if board[start] is None or board[start] == Color.GOLD:
            continue
        result.add((start,))
        for dr, dc in _DIRECTIONS_8:
            r, c = _index_to_rc(start)
            r2, c2 = r + dr, c + dc
            idx2 = _rc_to_index(r2, c2)
            if idx2 is None:
                continue
            if board[idx2] is not None and board[idx2] != Color.GOLD:
                line2 = (start, idx2)
                if _is_straight_line(line2):
                    result.add(line2)
                r3, c3 = r + dr * 2, c + dc * 2
                idx3 = _rc_to_index(r3, c3)
                if (
                    idx3 is not None
                    and board[idx3] is not None
                    and board[idx3] != Color.GOLD
                ):
                    line3 = (start, idx2, idx3)
                    if _is_straight_line(line3):
                        result.add(line3)
    return sorted(result, key=lambda x: (len(x), x))


def _has_penalty(taken_colors: list[Color]) -> bool:
    if taken_colors.count(Color.PEARL) >= 2:
        return True
    for c in set(taken_colors):
        if c == Color.GOLD:
            continue
        if taken_colors.count(c) == 3:
            return True
    return False


def _transfer_privilege_to_opponent(state):
    op = 1 - state.current_player
    players = list(state.players)
    supply = state.privileges_supply
    if supply > 0:
        supply = supply - 1
        players[op] = dataclasses.replace(
            players[op], privileges=players[op].privileges + 1
        )
    else:
        # take from active player if possible
        ap = state.current_player
        if players[ap].privileges > 0:
            players[ap] = dataclasses.replace(
                players[ap], privileges=players[ap].privileges - 1
            )
            players[op] = dataclasses.replace(
                players[op], privileges=players[op].privileges + 1
            )
    return dataclasses.replace(state, players=tuple(players), privileges_supply=supply)


def _apply_take_tokens(state, action: TakeTokens):
    cp = state.current_player
    players = list(state.players)
    new_board = list(state.board)
    taken: list[Color] = []
    gained = Tokens()
    for idx in action.line:
        c = new_board[idx]
        if c is None or c == Color.GOLD:
            raise ValueError
        taken.append(c)
        gained = gained + Tokens(
            white=1 if c == Color.WHITE else 0,
            blue=1 if c == Color.BLUE else 0,
            green=1 if c == Color.GREEN else 0,
            red=1 if c == Color.RED else 0,
            black=1 if c == Color.BLACK else 0,
            pearl=1 if c == Color.PEARL else 0,
            gold=1 if c == Color.GOLD else 0,
        )
        new_board[idx] = None
    players[cp] = dataclasses.replace(players[cp], tokens=players[cp].tokens + gained)
    st = dataclasses.replace(state, board=tuple(new_board), players=tuple(players))
    if _has_penalty(taken):
        st = _transfer_privilege_to_opponent(st)
    op = 1 - cp
    return dataclasses.replace(
        st, current_player=op, phase=Phase.USE_PRIVILEGES, pending=None
    )


def decide(state) -> DecisionPoint:
    if state.winner is not None:
        raise ValueError("game is over")
    if state.phase == Phase.MANDATORY:
        actions_list: list[Action] = []
        lines = _legal_take_token_lines(state.board)
        for line in lines:
            actions_list.append(TakeTokens(line))
        return DecisionPoint(phase=state.phase, legal_actions=tuple(actions_list))
    return DecisionPoint(phase=state.phase, legal_actions=())


def apply(state, action: Action):
    dp = decide(state)
    # check legal
    # check membership
    if action not in dp.legal_actions:
        raise ValueError("illegal action")
    if isinstance(action, TakeTokens):
        return _apply_take_tokens(state, action)
    return state
