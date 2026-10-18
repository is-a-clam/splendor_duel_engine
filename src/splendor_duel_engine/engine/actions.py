"""Game actions and decision logic (Step API)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.phase import Phase

if TYPE_CHECKING:
    from splendor_duel_engine.engine.state import GameState


_BOARD_SIZE = 25
_DIRECTIONS_8 = (
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
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


def _index_to_rc(index: int) -> tuple[int, int]:
    return index // 5, index % 5


def _rc_to_index(r: int, c: int) -> int | None:
    if r < 0 or r >= 5 or c < 0 or c >= 5:
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
            if idx2 is not None and board[idx2] is not None and board[idx2] != Color.GOLD:
                result.add((start, idx2))
                r3, c3 = r + dr * 2, c + dc * 2
                idx3 = _rc_to_index(r3, c3)
                if idx3 is not None and board[idx3] is not None and board[idx3] != Color.GOLD:
                    result.add((start, idx2, idx3))
    return sorted(result, key=lambda x: (len(x), x))


def _count_color_in_tokens(tokens_taken: list[Color]) -> dict[Color, int]:
    counts: dict[Color, int] = {}
    for c in tokens_taken:
        counts[c] = counts.get(c, 0) + 1
    return counts


def _grant_privilege(players: tuple, recipient: int, supply: int) -> tuple[tuple, int]:
    """Grant 1 privilege to recipient from supply, or steal from other player."""
    other = 1 - recipient
    new_players = list(players)
    new_supply = supply
    if new_supply > 0:
        new_supply = supply - 1
        new_players[recipient] = dataclasses.replace(
            players[recipient], privileges=players[recipient].privileges + 1
        )
    else:
        # Steal from other player
        if players[other].privileges > 0:
            new_players[other] = dataclasses.replace(
                players[other], privileges=players[other].privileges - 1
            )
            new_players[recipient] = dataclasses.replace(
                players[recipient], privileges=players[recipient].privileges + 1
            )
    return tuple(new_players), new_supply


def _apply_use_privilege(state: GameState, color: Color) -> GameState:
    active = state.current_player
    ap = state.players[active]

    # Find a token of the chosen color on the board (non-gold guaranteed by decide)
    board = list(state.board)
    try:
        idx = next(i for i, c in enumerate(board) if c == color)
    except StopIteration:
        raise ValueError(f"no token of color {color} on board")

    new_board_list = list(board)
    new_board_list[idx] = None
    new_board = tuple(new_board_list)

    # Add token to player's hand
    taken_tokens = Tokens(**{color.value: 1})
    new_ap = dataclasses.replace(ap, tokens=ap.tokens + taken_tokens, privileges=ap.privileges - 1)

    new_players_list = list(state.players)
    new_players_list[active] = new_ap

    # Determine next phase: stay in USE_PRIVILEGES if more privileges, else REPLENISH
    next_phase = Phase.USE_PRIVILEGES if new_ap.privileges > 0 else Phase.REPLENISH

    return dataclasses.replace(
        state,
        players=tuple(new_players_list),
        board=new_board,
        current_player=active,  # same player continues
        phase=next_phase,
    )


def _apply_replenish(state: GameState) -> GameState:
    active = state.current_player
    opp = 1 - active

    # Draw from bag onto empty spaces in SPIRAL order
    board = list(state.board)
    bag = state.bag

    # Collect available tokens from bag in a deterministic order
    token_colors: list[Color] = []
    for color in (
        Color.WHITE,
        Color.BLUE,
        Color.GREEN,
        Color.RED,
        Color.BLACK,
        Color.PEARL,
        Color.GOLD,
    ):
        count = bag.count(color)
        token_colors.extend([color] * count)

    # Fill empty slots along SPIRAL
    filled_count = 0
    for spiral_idx in SPIRAL:
        if filled_count >= len(token_colors):
            break
        if board[spiral_idx] is None:
            board[spiral_idx] = token_colors[filled_count]
            filled_count += 1

    # Update bag: remove the tokens that were placed
    new_bag_dict = {color.value: bag.count(color) for color in Color}
    for i in range(filled_count):
        color = token_colors[i]
        new_bag_dict[color.value] -= 1
    new_bag = Tokens(**new_bag_dict)

    # Grant opponent 1 privilege
    new_players, new_priv_supply = _grant_privilege(state.players, opp, state.privileges_supply)

    return dataclasses.replace(
        state,
        players=new_players,
        board=tuple(board),
        bag=new_bag,
        privileges_supply=new_priv_supply,
        current_player=active,  # same player continues to MANDATORY
        phase=Phase.MANDATORY,
    )


def _apply_take_tokens(state: GameState, line: tuple[int, ...]) -> GameState:
    if not _is_straight_line(line) or len(line) < 1 or len(line) > 3:
        raise ValueError("line must be contiguous straight of length 1-3")

    board = list(state.board)
    taken_colors: list[Color] = []
    for idx in line:
        c = board[idx]
        if c is None or c == Color.GOLD:
            raise ValueError("cannot take gold or empty cell")
        taken_colors.append(c)
    new_board_list = list(board)
    for idx in line:
        new_board_list[idx] = None
    new_board = tuple(new_board_list)

    active = state.current_player
    ap = state.players[active]
    taken_tokens = Tokens(
        white=sum(1 for c in taken_colors if c == Color.WHITE),
        blue=sum(1 for c in taken_colors if c == Color.BLUE),
        green=sum(1 for c in taken_colors if c == Color.GREEN),
        red=sum(1 for c in taken_colors if c == Color.RED),
        black=sum(1 for c in taken_colors if c == Color.BLACK),
        pearl=sum(1 for c in taken_colors if c == Color.PEARL),
        gold=sum(1 for c in taken_colors if c == Color.GOLD),
    )
    new_ap = dataclasses.replace(ap, tokens=ap.tokens + taken_tokens)

    penalty = False
    color_counts = _count_color_in_tokens(taken_colors)
    for cnt in color_counts.values():
        if cnt >= 3:
            penalty = True
            break
    if color_counts.get(Color.PEARL, 0) >= 2:
        penalty = True

    new_players_list = list(state.players)
    new_players_list[active] = new_ap

    new_priv_supply = state.privileges_supply
    if penalty:
        opp = 1 - active
        opp_state = state.players[opp]
        if state.privileges_supply > 0:
            new_priv_supply = state.privileges_supply - 1
            new_opp = dataclasses.replace(opp_state, privileges=opp_state.privileges + 1)
            new_players_list[opp] = new_opp
        else:
            if new_ap.privileges > 0:
                new_ap_pen = dataclasses.replace(new_ap, privileges=new_ap.privileges - 1)
                new_opp = dataclasses.replace(opp_state, privileges=opp_state.privileges + 1)
                new_players_list[active] = new_ap_pen
                new_players_list[opp] = new_opp

    return dataclasses.replace(
        state,
        players=tuple(new_players_list),
        board=new_board,
        privileges_supply=new_priv_supply,
        current_player=1 - state.current_player,
        phase=Phase.USE_PRIVILEGES,
    )


def decide(state: GameState) -> DecisionPoint:
    if state.winner is not None:
        raise ValueError("game is over")

    if state.phase == Phase.USE_PRIVILEGES:
        ap = state.players[state.current_player]
        actions: list[Action] = []
        if ap.privileges > 0:
            # Can use privilege to take any non-gold, non-empty token from board
            seen_colors: set[Color] = set()
            for idx, color in enumerate(state.board):
                if color is not None and color != Color.GOLD and color not in seen_colors:
                    actions.append(UsePrivilege(color))
                    seen_colors.add(color)
        actions.append(DoneWithPrivileges())
        return DecisionPoint(phase=Phase.USE_PRIVILEGES, legal_actions=tuple(actions))

    if state.phase == Phase.REPLENISH:
        actions: list[Action] = []
        if state.bag.total() > 0:
            actions.append(Replenish())
        actions.append(DoneWithReplenish())
        return DecisionPoint(phase=Phase.REPLENISH, legal_actions=tuple(actions))

    if state.phase == Phase.MANDATORY:
        actions: list[Action] = []
        for line in _legal_take_token_lines(state.board):
            actions.append(TakeTokens(line))

        # Forced replenish: if no legal take actions and bag non-empty, go to REPLENISH
        if not actions and state.bag.total() > 0:
            return DecisionPoint(phase=Phase.REPLENISH, legal_actions=(Replenish(),))

        actions.sort(key=lambda a: (len(a.line), a.line) if isinstance(a, TakeTokens) else (0, ()))
        return DecisionPoint(phase=Phase.MANDATORY, legal_actions=tuple(actions))

    return DecisionPoint(phase=state.phase, legal_actions=())


def apply(state: GameState, action: Action) -> GameState:
    dp = decide(state)
    if action not in dp.legal_actions:
        raise ValueError("illegal action")

    if isinstance(action, UsePrivilege):
        return _apply_use_privilege(state, action.color)
    if isinstance(action, DoneWithPrivileges):
        # Advance to REPLENISH
        return dataclasses.replace(state, phase=Phase.REPLENISH)
    if isinstance(action, Replenish):
        return _apply_replenish(state)
    if isinstance(action, DoneWithReplenish):
        return dataclasses.replace(state, phase=Phase.MANDATORY)
    if isinstance(action, TakeTokens):
        return _apply_take_tokens(state, action.line)
    return state