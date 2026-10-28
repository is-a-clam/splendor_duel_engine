"""Game actions and decision logic (Step API)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from splendor_duel_engine.engine import helpers
from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.cards import Ability
from splendor_duel_engine.engine.colors import ALL_COLORS, GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import ReservedCard, PurchasedCard

if TYPE_CHECKING:
    from splendor_duel_engine.engine.cards import Card
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
    index: int


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
    card: Card
    source: str


@dataclass(frozen=True, slots=True)
class PayTokens:
    payment: Tokens


@dataclass(frozen=True, slots=True)
class ReserveCard:
    source: str
    index: int


@dataclass(frozen=True, slots=True)
class ChooseGold:
    index: int


@dataclass(frozen=True, slots=True)
class ChooseMulticolor:
    color: Color


@dataclass(frozen=True, slots=True)
class ChooseStealToken:
    color: Color


@dataclass(frozen=True, slots=True)
class ChooseMatchingToken:
    index: int


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
    | ChooseGold
    | ChooseMulticolor
    | ChooseStealToken
    | ChooseMatchingToken
    | ChooseRoyal
    | DiscardTokens
)


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    phase: Phase
    legal_actions: tuple[Action, ...]


def decide(state: GameState) -> DecisionPoint:
    if state.winner is not None:
        raise ValueError("game is over")

    if state.phase == Phase.USE_PRIVILEGES:
        ap = state.players[state.current_player]
        actions: list[Action] = []
        if ap.privileges > 0:
            # Can use privilege to take any non-gold, non-empty token from board
            for idx, color in enumerate(state.board):
                if color is not None and color != Color.GOLD:
                    actions.append(UsePrivilege(index=idx))
        actions.append(DoneWithPrivileges())
        return DecisionPoint(phase=Phase.USE_PRIVILEGES, legal_actions=tuple(actions))

    if state.phase == Phase.REPLENISH:
        actions: list[Action] = []
        if helpers.total_tokens(state.bag) > 0:
            actions.append(Replenish())
        actions.append(DoneWithReplenish())
        return DecisionPoint(phase=Phase.REPLENISH, legal_actions=tuple(actions))

    if state.phase == Phase.CHOOSE_GOLD:
        actions: list[Action] = []
        for idx, color in enumerate(state.board):
            if color == Color.GOLD:
                actions.append(ChooseGold(index=idx))
        return DecisionPoint(phase=Phase.CHOOSE_GOLD, legal_actions=tuple(actions))

    if state.phase == Phase.MANDATORY:
        actions: list[Action] = []
        for line in _legal_take_token_lines(state.board):
            actions.append(TakeTokens(line))

        # Reserve actions
        actions.extend(_get_reserve_actions(state))

        # Buy actions (own reserved + pyramid)
        for buy_action in _get_buyable_cards(state):
            actions.append(buy_action)

        # Forced replenish: if no legal take actions and bag non-empty, go to REPLENISH
        # But only if no reserve/buy actions either
        if not actions and helpers.total_tokens(state.bag) > 0:
            return DecisionPoint(phase=Phase.REPLENISH, legal_actions=(Replenish(),))

        actions.sort(
            key=lambda a: (
                (len(a.line), a.line) if isinstance(a, TakeTokens) else (0, ())
            )
        )
        return DecisionPoint(phase=Phase.MANDATORY, legal_actions=tuple(actions))

    if state.phase == Phase.CHOOSE_PAYMENT:
        pending_action = state.pending_buy
        if pending_action is None:
            return DecisionPoint(phase=Phase.CHOOSE_PAYMENT, legal_actions=())
        ap = state.players[state.current_player]
        bonus = ap.bonus
        legal_payments = helpers.legal_payments(pending_action.card, bonus, ap.tokens)
        actions: list[Action] = [PayTokens(payment=p) for p in legal_payments]
        return DecisionPoint(phase=Phase.CHOOSE_PAYMENT, legal_actions=tuple(actions))

    if state.phase == Phase.MULTICOLOR_COLOR:
        pending_action = state.pending_buy
        if pending_action is None:
            return DecisionPoint(phase=Phase.MULTICOLOR_COLOR, legal_actions=())
        ap = state.players[state.current_player]
        available_colors = [c for c in GEM_COLORS if helpers.get_tokens(ap.bonus, c) > 0]
        actions: list[Action] = [ChooseMulticolor(color=c) for c in available_colors]
        return DecisionPoint(phase=Phase.MULTICOLOR_COLOR, legal_actions=tuple(actions))

    if state.phase == Phase.STEAL_TOKEN:
        if state.pending_ability != Ability.STEAL_TOKEN:
            return DecisionPoint(phase=Phase.STEAL_TOKEN, legal_actions=())
        opp = 1 - state.current_player
        opp_tokens = state.players[opp].tokens
        stealable_colors = [c for c in GEM_COLORS if helpers.get_tokens(opp_tokens, c) > 0]
        actions: list[Action] = [ChooseStealToken(color=c) for c in stealable_colors]
        return DecisionPoint(phase=Phase.STEAL_TOKEN, legal_actions=tuple(actions))

    if state.phase == Phase.TAKE_MATCHING_TOKEN:
        if state.pending_ability != Ability.TAKE_MATCHING_TOKEN:
            return DecisionPoint(phase=Phase.TAKE_MATCHING_TOKEN, legal_actions=())
        # Find all board indices with the matching color
        # The card is stored in pending_buy from the ability resolution
        pending_action = state.pending_buy
        if pending_action is None:
            return DecisionPoint(phase=Phase.TAKE_MATCHING_TOKEN, legal_actions=())
        card = pending_action.card
        if card.bonus is None:
            return DecisionPoint(phase=Phase.TAKE_MATCHING_TOKEN, legal_actions=())
        bonus_color = card.bonus
        matching_indices = [
            idx for idx, color in enumerate(state.board) if color == bonus_color
        ]
        actions: list[Action] = [
            ChooseMatchingToken(index=idx) for idx in matching_indices
        ]
        return DecisionPoint(
            phase=Phase.TAKE_MATCHING_TOKEN, legal_actions=tuple(actions)
        )

    if state.phase == Phase.CHOOSE_ROYAL:
        actions: list[Action] = [
            ChooseRoyal(royal_id=r.id) for r in state.royals_available
        ]
        return DecisionPoint(phase=Phase.CHOOSE_ROYAL, legal_actions=tuple(actions))

    if state.phase == Phase.DISCARD:
        ap = state.players[state.current_player]
        excess = helpers.total_tokens(ap.tokens) - helpers.TOKEN_LIMIT
        actions: list[Action] = [
            DiscardTokens(tokens=subset)
            for subset in helpers.discard_subsets(ap.tokens, excess)
        ]
        return DecisionPoint(phase=Phase.DISCARD, legal_actions=tuple(actions))

    return DecisionPoint(phase=state.phase, legal_actions=())


def apply(state: GameState, action: Action) -> GameState:
    dp = decide(state)
    if action not in dp.legal_actions:
        raise ValueError("illegal action")

    if isinstance(action, UsePrivilege):
        return _apply_use_privilege(state, action.index)
    if isinstance(action, DoneWithPrivileges):
        # Advance to REPLENISH
        return replace(state, phase=Phase.REPLENISH)
    if isinstance(action, Replenish):
        return _apply_replenish(state)
    if isinstance(action, DoneWithReplenish):
        # If extra_turn flag is set, consume it and stay with same player
        if state.extra_turn:
            return replace(state, phase=Phase.MANDATORY, extra_turn=False)
        return replace(state, phase=Phase.MANDATORY)
    if isinstance(action, TakeTokens):
        return _apply_take_tokens(state, action.line)
    if isinstance(action, ReserveCard):
        return _apply_reserve_card(state, action)
    if isinstance(action, ChooseGold):
        return _apply_choose_gold(state, action.index)
    if isinstance(action, BuyCard):
        return _apply_buy_card(state, action)
    if isinstance(action, PayTokens):
        return _apply_pay_tokens(state, action)
    if isinstance(action, ChooseMulticolor):
        return _apply_choose_multicolor(state, action.color)
    if isinstance(action, ChooseStealToken):
        return _apply_choose_steal_token(state, action.color)
    if isinstance(action, ChooseMatchingToken):
        return _apply_choose_matching_token(state, action.index)
    if isinstance(action, ChooseRoyal):
        return _apply_choose_royal(state, action.royal_id)
    if isinstance(action, DiscardTokens):
        return _apply_discard_tokens(state, action.tokens)
    return state


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


# ===== Decision space functions =====


def _legal_take_token_lines(board: tuple[Color | None, ...]) -> list[tuple[int, ...]]:
    """Enumerate each distinct straight line of 1-3 non-gold tokens once.

    A line is scanned from every start cell in all 8 directions, so the same
    physical line is produced twice — once per traversal direction (``(A, B)``
    from A and ``(B, A)`` from B). Canonicalise each candidate to the
    lexicographic minimum of the line and its reverse so the legal-action mask
    offers exactly one action per distinct line (length-1 lines are unaffected).
    """
    result: set[tuple[int, ...]] = set()
    for start in range(_BOARD_SIZE):
        if board[start] is None or board[start] == Color.GOLD:
            continue
        result.add((start,))
        for dr, dc in _DIRECTIONS_8:
            r, c = _index_to_rc(start)
            r2, c2 = r + dr, c + dc
            idx2 = _rc_to_index(r2, c2)
            if (
                idx2 is not None
                and board[idx2] is not None
                and board[idx2] != Color.GOLD
            ):
                result.add(min((start, idx2), (idx2, start)))
                r3, c3 = r + dr * 2, c + dc * 2
                idx3 = _rc_to_index(r3, c3)
                if (
                    idx3 is not None
                    and board[idx3] is not None
                    and board[idx3] != Color.GOLD
                ):
                    line = (start, idx2, idx3)
                    result.add(min(line, line[::-1]))
    return sorted(result, key=lambda x: (len(x), x))


def _get_reserve_actions(state: GameState) -> list[ReserveCard]:
    """Enumerate all legal ReserveCard actions for the current player."""
    active = state.current_player
    ap = state.players[active]

    if not helpers.can_reserve(state.board, len(ap.reserved)):
        return []

    actions: list[ReserveCard] = []

    # Reserve from pyramid (public cards)
    for row_idx, row in enumerate(state.pyramid):
        for col_idx, card in enumerate(row):
            if card is not None:
                actions.append(
                    ReserveCard(source="pyramid", index=row_idx * 10 + col_idx)
                )

    # Reserve from deck tops (hidden cards)
    for deck_idx, deck in enumerate(state.decks):
        if deck:  # deck not empty
            level = 3 - deck_idx  # deck 0=level3, 1=level2, 2=level1
            actions.append(ReserveCard(source=f"deck_{level}", index=0))

    return actions


def _get_buyable_cards(state: GameState) -> list[BuyCard]:
    """Return list of BuyCard actions for cards the active player can buy.

    Source is "reserved" or "pyramid_r_c" (e.g., "pyramid_0_2").
    Deduplicates by card_id, preferring reserved source (since a card cannot
    be in both places simultaneously in a valid state, but we guard anyway).
    """
    active = state.current_player
    ap = state.players[active]
    bonus = ap.bonus

    buyable: dict[str, tuple[Card, str]] = {}  # card_id -> (card, source)

    # Own reserved cards (checked first, so they take precedence)
    for reserved in ap.reserved:
        card = reserved.card
        if helpers.can_afford_card(card, bonus, ap.tokens):
            buyable[card.id] = (card, "reserved")

    # Pyramid cards
    for row_idx, row in enumerate(state.pyramid):
        for col_idx, card in enumerate(row):
            if (
                card is not None
                and card.id not in buyable
                and helpers.can_afford_card(card, bonus, ap.tokens)
            ):
                source = f"pyramid_{row_idx}_{col_idx}"
                buyable[card.id] = (card, source)

    return [BuyCard(card=card, source=source) for card, source in buyable.values()]


# ===== Apply action functions =====


def _apply_use_privilege(state: GameState, index: int) -> GameState:
    active = state.current_player
    ap = state.players[active]

    # Validate the player has privilege
    if ap.privileges <= 0:
        raise ValueError("player does not have privilege")

    # Validate the index
    if index < 0 or index >= _BOARD_SIZE:
        raise ValueError(f"invalid board index {index}")
    color = state.board[index]
    if color is None or color == Color.GOLD:
        raise ValueError(f"no non-gold token at index {index}")

    # Use helper to remove token from board
    state = state.remove_from_board(index)

    # Add token to player's hand
    taken_tokens = Tokens(**{color.value: 1})
    new_ap = replace(
        ap, tokens=helpers.add_tokens(ap.tokens, taken_tokens), privileges=ap.privileges - 1
    )

    # Determine next phase: stay in USE_PRIVILEGES if more privileges, else REPLENISH
    next_phase = Phase.USE_PRIVILEGES if new_ap.privileges > 0 else Phase.REPLENISH

    return replace(
        state.update_player(active, new_ap),
        current_player=active,
        phase=next_phase,
    )


def _apply_replenish(state: GameState) -> GameState:
    active = state.current_player
    opp = 1 - active

    # Collect all tokens from bag into a list
    token_colors: list[Color] = []
    for color in ALL_COLORS:
        count = helpers.get_tokens(state.bag, color)
        token_colors.extend([color] * count)

    # Shuffle the tokens with a *copy* of the state's RNG. ``apply`` must never
    # mutate its input, and ``random.Random`` is shared by reference, so drawing
    # from ``state.rng`` directly would advance the caller's RNG in place. The
    # copy is stored into the returned state, so replaying the same action
    # sequence from the same state still yields the same draws.
    local_rng = copy.deepcopy(state.rng)
    local_rng.shuffle(token_colors)

    # Collect all empty board indices in SPIRAL order
    empty_indices = [idx for idx in SPIRAL if state.board[idx] is None]

    # Place tokens from shuffled list onto empty slots in SPIRAL order
    placed_count = min(len(token_colors), len(empty_indices))
    for i in range(placed_count):
        state = state.update_board(empty_indices[i], token_colors[i])

    # New bag is empty (all tokens placed since total = 25)
    state = replace(state, bag=Tokens())

    # Grant opponent 1 privilege
    state = state.grant_privilege(opp)

    return replace(
        state,
        current_player=active,
        phase=Phase.MANDATORY,
        rng=local_rng,
    )


def _apply_take_tokens(state: GameState, line: tuple[int, ...]) -> GameState:
    if not _is_straight_line(line) or len(line) < 1 or len(line) > 3:
        raise ValueError("line must be contiguous straight of length 1-3")

    taken_colors: list[Color] = []
    for idx in line:
        c = state.board[idx]
        if c is None or c == Color.GOLD:
            raise ValueError("cannot take gold or empty cell")
        taken_colors.append(c)
        state = state.remove_from_board(idx)

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
    new_ap = replace(ap, tokens=helpers.add_tokens(ap.tokens, taken_tokens))
    state = state.update_player(active, new_ap)

    if helpers.is_penalty_triggered(taken_colors):
        opp = 1 - active
        state = state.grant_privilege(opp)

    return _end_of_turn(state, active)


def _apply_reserve_card(state: GameState, action: ReserveCard) -> GameState:
    """Validate preconditions and enter CHOOSE_GOLD phase."""
    active = state.current_player
    ap = state.players[active]

    # Minimal validation only
    if not helpers.can_reserve(state.board, len(ap.reserved)):
        raise ValueError("cannot reserve card")

    # Validate source exists and has a card (but don't extract yet)
    if action.source == "pyramid":
        row_idx = action.index // 10
        col_idx = action.index % 10
        if row_idx >= len(state.pyramid) or col_idx >= len(state.pyramid[row_idx]):
            raise ValueError("invalid pyramid index")
        if state.pyramid[row_idx][col_idx] is None:
            raise ValueError("empty pyramid slot")
    elif action.source.startswith("deck_"):
        level = int(action.source.split("_")[1])
        deck_idx = 3 - level
        if deck_idx < 0 or deck_idx >= len(state.decks):
            raise ValueError(f"invalid deck index {deck_idx}")
        if not state.decks[deck_idx]:
            raise ValueError(f"deck level {level} empty")
    else:
        raise ValueError(f"unknown reserve source: {action.source}")

    return replace(
        state,
        pending_reserve=action,
        phase=Phase.CHOOSE_GOLD,
    )


def _apply_choose_gold(state: GameState, index: int) -> GameState:
    """Take the chosen gold token and complete the reserve (all execution in one step)."""
    active = state.current_player
    ap = state.players[active]

    pending_action = state.pending_reserve
    if pending_action is None:
        raise ValueError("no pending reserve action")

    # Validate the index has a gold token
    if index < 0 or index >= _BOARD_SIZE:
        raise ValueError(f"invalid board index {index}")
    if state.board[index] != Color.GOLD:
        raise ValueError(f"no gold token at index {index}")

    # Take gold from board
    state = state.remove_from_board(index)

    # Add gold to player's hand
    gold_tokens = Tokens(gold=1)
    new_ap = replace(ap, tokens=helpers.add_tokens(ap.tokens, gold_tokens))
    state = state.update_player(active, new_ap)

    # Extract card from source and update pyramid/decks in one unified logic
    card: Card | None
    from_deck: bool = False

    if pending_action.source == "pyramid":
        row_idx = pending_action.index // 10
        col_idx = pending_action.index % 10
        # Take card and refill from deck in one atomic operation
        card, state = state.take_pyramid_card(row_idx, col_idx)
        from_deck = False
    elif pending_action.source.startswith("deck_"):
        level = int(pending_action.source.split("_")[1])
        deck_idx = 3 - level
        card, state = state.pop_deck(deck_idx)
        from_deck = True
    else:
        raise ValueError(f"unknown reserve source: {pending_action.source}")

    if card is None:
        raise ValueError("card not found")

    # Add card to player's reserved
    reserved_card = ReservedCard(card=card, from_deck=from_deck)
    new_ap = replace(new_ap, reserved=new_ap.reserved + (reserved_card,))
    state = state.update_player(active, new_ap)

    # Reserving takes a gold token, so route through the end-of-turn sequence
    # (discard/win) before the turn passes to the opponent.
    return _end_of_turn(
        replace(state, pending_reserve=None), active, extra_turn=False
    )


def _apply_buy_card(state: GameState, action: BuyCard) -> GameState:
    """Validate preconditions and enter CHOOSE_PAYMENT phase."""
    active = state.current_player
    ap = state.players[active]
    bonus = ap.bonus

    # Verify the card is buyable (affordable and in the right place)
    card = action.card
    source = action.source

    if source == "reserved":
        # Check the card is in player's reserved
        found = False
        for reserved in ap.reserved:
            if reserved.card.id == card.id:
                found = True
                break
        if not found:
            raise ValueError(f"card {card.id} not in reserved")
    elif source.startswith("pyramid_"):
        # Parse pyramid coordinates
        parts = source.split("_")
        if len(parts) != 3:
            raise ValueError(f"invalid pyramid source: {source}")
        row_idx = int(parts[1])
        col_idx = int(parts[2])
        if row_idx >= len(state.pyramid) or col_idx >= len(state.pyramid[row_idx]):
            raise ValueError("invalid pyramid index")
        pyr_card = state.pyramid[row_idx][col_idx]
        if pyr_card is None or pyr_card.id != card.id:
            raise ValueError(f"card {card.id} not at pyramid source")
    else:
        raise ValueError(f"unknown buy source: {source}")

    # Verify affordability (the multicolor rule is folded into can_afford_card)
    if not helpers.can_afford_card(card, bonus, ap.tokens):
        raise ValueError("cannot afford card")

    return replace(
        state,
        pending_buy=action,
        phase=Phase.CHOOSE_PAYMENT,
    )


def _apply_pay_tokens(state: GameState, action: PayTokens) -> GameState:
    active = state.current_player
    ap = state.players[active]

    pending_action = state.pending_buy
    if pending_action is None:
        raise ValueError("no pending card to pay for")

    card = pending_action.card
    source = pending_action.source

    # Validate payment
    bonus = ap.bonus
    if not helpers.can_afford_card(card, bonus, action.payment):
        raise ValueError("insufficient payment")
    # Also verify payment doesn't exceed player's tokens
    for color in ALL_COLORS:
        if helpers.get_tokens(action.payment, color) > helpers.get_tokens(ap.tokens, color):
            raise ValueError(f"payment exceeds tokens for {color}")

    # Move spent tokens to bag (use helper)
    state = state.add_to_bag(action.payment)

    # Remove tokens from player
    new_tokens = helpers.sub_tokens(ap.tokens, action.payment)
    new_ap = replace(ap, tokens=new_tokens)

    # Remove card from source and update pyramid/decks
    if source == "reserved":
        # Remove from reserved
        for i, reserved in enumerate(ap.reserved):
            if reserved.card.id == card.id:
                new_reserved = ap.reserved[:i] + ap.reserved[i + 1 :]
                new_ap = replace(new_ap, reserved=new_reserved)
                break
    elif source.startswith("pyramid_"):
        parts = source.split("_")
        row_idx = int(parts[1])
        col_idx = int(parts[2])
        # Use helper to take pyramid card and refill from deck in one atomic operation
        card_from_pyramid, state = state.take_pyramid_card(row_idx, col_idx)
        if card_from_pyramid is None:
            raise ValueError("card not found")
        if card_from_pyramid.id != card.id:
            raise ValueError(f"card {card.id} not at pyramid source")
    else:
        raise ValueError(f"unknown buy source: {source}")

    # Add card to purchased
    purchased_card = PurchasedCard(card=card, chosen_color=None)
    new_purchased = new_ap.purchased + (purchased_card,)
    new_ap = replace(new_ap, purchased=new_purchased)

    # Grant bonus, prestige, crowns
    old_crowns = new_ap.crowns
    if card.bonus is not None:
        bonus_increment = Tokens(**{card.bonus.value: 1})
        new_bonus = helpers.add_tokens(bonus, bonus_increment)
        new_ap = replace(new_ap, bonus=new_bonus)

    new_ap = replace(
        new_ap,
        prestige=new_ap.prestige + card.points,
        crowns=new_ap.crowns + card.crowns,
    )
    new_crowns = new_ap.crowns

    # Update player state
    state = state.update_player(active, new_ap)

    # Royal trigger: crossing the 3rd or 6th crown threshold (from below) grants
    # one royal pick each. A multicolor card cannot pick its royal yet — the
    # color choice comes first — so defer via pending_royal.
    crossed_royal = old_crowns < 3 <= new_crowns or old_crowns < 6 <= new_crowns

    if crossed_royal and state.royals_available:
        royal_phase_state = replace(
            state,
            pending_buy=pending_action,
            winner=None,
            current_player=active,
            phase=Phase.CHOOSE_ROYAL,
            extra_turn=False,
            pending_ability=None,
        )
        if card.is_multicolor:
            return replace(
                royal_phase_state,
                phase=Phase.MULTICOLOR_COLOR,
                pending_royal=True,
            )
        return royal_phase_state

    # Handle multicolor first (separate from abilities)
    if card.is_multicolor:
        return replace(
            state,
            pending_buy=pending_action,
            winner=None,
            current_player=active,
            phase=Phase.MULTICOLOR_COLOR,
            extra_turn=False,
            pending_ability=None,
        )

    # Not multicolor: resolve abilities directly
    return _resolve_abilities(
        replace(
            state,
            pending_buy=pending_action,
            winner=None,
            current_player=active,
            phase=Phase.USE_PRIVILEGES,
            extra_turn=False,
            pending_ability=None,
        ),
        card,
        active,
    )


def _resolve_abilities(state: GameState, card: Card, active: int) -> GameState:
    """Resolve the card's single ability (if any). Returns final state."""
    match card.ability:
        case Ability.STEAL_TOKEN:
            opp = 1 - active
            opp_tokens = state.players[opp].tokens
            stealable_colors = [c for c in GEM_COLORS if helpers.get_tokens(opp_tokens, c) > 0]
            if stealable_colors:
                return replace(
                    state,
                    phase=Phase.STEAL_TOKEN,
                    pending_ability=Ability.STEAL_TOKEN,
                )
            # No tokens to steal → normal turn end
            return _end_of_turn(state, active)

        case Ability.TAKE_MATCHING_TOKEN:
            # Keep pending_buy for the decision phase to access card's bonus color
            return _run_take_matching_token(state, card, active)

        case Ability.PRIVILEGE:
            # Clear pending_buy as this ability completes immediately
            return _run_privilege(
                replace(state, pending_buy=None), card, active
            )

        case Ability.EXTRA_TURN:
            # Clear pending_buy as this ability completes immediately
            return _run_extra_turn(
                replace(state, pending_buy=None), card, active
            )

        case None:
            # Clear pending_buy as no ability
            return _end_of_turn(replace(state, pending_buy=None), active)


def _run_take_matching_token(state: GameState, card: Card, active: int) -> GameState:
    if card.bonus is not None:
        bonus_color = card.bonus
        matching_indices = [
            idx for idx, color in enumerate(state.board) if color == bonus_color
        ]
        if matching_indices:
            # Keep pending_buy for the decision phase
            return replace(
                state,
                phase=Phase.TAKE_MATCHING_TOKEN,
                pending_ability=Ability.TAKE_MATCHING_TOKEN,
            )
    return _end_of_turn(state, active)


def _run_privilege(state: GameState, card: Card, active: int) -> GameState:
    state = state.grant_privilege(active)
    return _end_of_turn(
        state,
        active,
    )


def _run_extra_turn(state: GameState, card: Card, active: int) -> GameState:
    """Resolve an EXTRA_TURN ability: the turn still ends (discard + win check)."""
    return _end_of_turn(state, active, extra_turn=True)


def _apply_discard_tokens(state: GameState, tokens: Tokens) -> GameState:
    """Move chosen excess tokens from the active player's hand to the bag."""
    active = state.current_player
    ap = state.players[active]
    excess = helpers.total_tokens(ap.tokens) - helpers.TOKEN_LIMIT

    for color in ALL_COLORS:
        if helpers.get_tokens(tokens, color) < 0:
            raise ValueError("discard counts must be non-negative")
        if helpers.get_tokens(tokens, color) > helpers.get_tokens(ap.tokens, color):
            raise ValueError(f"cannot discard more {color} than held")
    if helpers.total_tokens(tokens) != excess:
        raise ValueError("discard must remove exactly the excess tokens")

    # Tokens go to the bag (spec: excess goes to the bag).
    state = state.add_to_bag(tokens)
    new_ap = replace(ap, tokens=helpers.sub_tokens(ap.tokens, tokens))
    state = state.update_player(active, new_ap)

    # The pending seat decision was stashed in ``extra_turn`` by _end_of_turn.
    pending_extra_turn = state.extra_turn
    return _finish_turn(state, active, extra_turn=pending_extra_turn)


def _apply_choose_multicolor(state: GameState, color: Color) -> GameState:
    """Resolve the chosen color for a multicolor card."""
    active = state.current_player
    pending_action = state.pending_buy
    if pending_action is None:
        raise ValueError("no pending card for multicolor resolution")
    card = pending_action.card
    if not card.is_multicolor:
        raise ValueError("card is not multicolor")

    # Update the purchased card's chosen_color
    ap = state.players[active]
    purchased_list = list(ap.purchased)
    last_pc = purchased_list[-1]
    if last_pc.card.id != card.id:
        raise ValueError("purchased card mismatch")
    updated_pc = PurchasedCard(card=card, chosen_color=color)
    purchased_list[-1] = updated_pc

    # Add bonus_count of chosen color to player's bonus
    bonus_increment = Tokens(**{color.value: card.bonus_count})
    new_bonus = helpers.add_tokens(ap.bonus, bonus_increment)
    new_ap = replace(ap, bonus=new_bonus, purchased=tuple(purchased_list))
    new_players = list(state.players)
    new_players[active] = new_ap

    # After multicolor: resolve abilities directly
    return _resolve_abilities(
        replace(
            state,
            players=tuple(new_players),
            pending_ability=None,
        ),
        card,
        active,
    )


def _apply_choose_steal_token(state: GameState, color: Color) -> GameState:
    """Resolve stealing a token from opponent."""
    if state.pending_ability != Ability.STEAL_TOKEN:
        raise ValueError("not in steal token phase")

    active = state.current_player
    opp = 1 - active
    opp_tokens = state.players[opp].tokens

    if helpers.get_tokens(opp_tokens, color) == 0:
        raise ValueError(f"opponent has no {color} tokens to steal")

    # Remove token from opponent
    opp_lost = Tokens(**{color.value: -1})
    new_opp = replace(
        state.players[opp], tokens=helpers.add_tokens(state.players[opp].tokens, opp_lost)
    )

    # Add token to active player
    active_gained = Tokens(**{color.value: 1})
    new_active = replace(
        state.players[active], tokens=helpers.add_tokens(state.players[active].tokens, active_gained)
    )

    new_players = list(state.players)
    new_players[active] = new_active
    new_players[opp] = new_opp

    # After steal: normal turn end (no other abilities on steal cards)
    return _end_of_turn(
        replace(
            state,
            players=tuple(new_players),
            pending_ability=None,
        ),
        active,
    )


def _apply_choose_matching_token(state: GameState, index: int) -> GameState:
    """Resolve taking a matching token from the board."""
    if state.pending_ability != Ability.TAKE_MATCHING_TOKEN:
        raise ValueError("not in take matching token phase")

    active = state.current_player
    pending_action = state.pending_buy
    if pending_action is None:
        raise ValueError("no pending card for take matching token")

    card = pending_action.card
    if card.bonus is None:
        raise ValueError("card has no bonus color")

    bonus_color = card.bonus
    if index < 0 or index >= _BOARD_SIZE:
        raise ValueError(f"invalid board index {index}")
    if state.board[index] != bonus_color:
        raise ValueError(f"no {bonus_color} token at index {index}")

    # Take the token from board
    board = list(state.board)
    board[index] = None
    new_board = tuple(board)

    # Add token to player's hand
    taken = Tokens(**{bonus_color.value: 1})
    new_players = list(state.players)
    new_players[active] = replace(
        state.players[active], tokens=helpers.add_tokens(state.players[active].tokens, taken)
    )

    # Normal turn end
    return _end_of_turn(
        replace(
            state,
            players=tuple(new_players),
            board=new_board,
            pending_ability=None,
            pending_buy=None,
        ),
        active,
    )


def _apply_choose_royal(state: GameState, royal_id: str) -> GameState:
    """Grant the chosen royal, then resolve its ability and end the turn.

    Called at the royal step of the end-of-turn sequence (after the purchased
    card's ability, before discard). The royal adds prestige only.
    """
    active = state.current_player
    # Find the royal
    royal = None
    new_royals = []
    for r in state.royals_available:
        if r.id == royal_id:
            royal = r
        else:
            new_royals.append(r)
    if royal is None:
        raise ValueError(f"royal {royal_id} not available")

    ap = state.players[active]
    # Add royal: gives prestige, no crowns, no bonus
    new_ap = replace(
        ap,
        prestige=ap.prestige + royal.points,
    )
    new_players = list(state.players)
    new_players[active] = new_ap
    state = replace(
        state,
        players=tuple(new_players),
        royals_available=tuple(new_royals),
    )

    # Resolve royal's ability if any (reuse Task 6 machinery)
    if royal.ability is not None:
        match royal.ability:
            case Ability.STEAL_TOKEN:
                opp = 1 - active
                opp_tokens = state.players[opp].tokens
                stealable_colors = [c for c in GEM_COLORS if helpers.get_tokens(opp_tokens, c) > 0]
                if stealable_colors:
                    return replace(
                        state,
                        phase=Phase.STEAL_TOKEN,
                        pending_ability=Ability.STEAL_TOKEN,
                    )
                return _end_of_turn(state, active)
            case Ability.PRIVILEGE:
                state = state.grant_privilege(active)
                return _end_of_turn(
                    state,
                    active,
                )
            case Ability.EXTRA_TURN:
                return _end_of_turn(state, active, extra_turn=True)
            case _:
                return _end_of_turn(state, active)
    return _end_of_turn(state, active)


def _end_of_turn(
    state: GameState, active: int, *, extra_turn: bool = False
) -> GameState:
    """Run the end-of-turn sequence for ``active`` (spec §End of turn and victory).

    Order: abilities/royals have already resolved by the time this is called,
    so this performs discard (if the player holds more than 10 tokens) then the
    win check, then hands the turn over (or keeps it on an extra turn).
    """
    state = replace(
        state,
        current_player=active,
        pending_buy=None,
        pending_reserve=None,
        pending_ability=None,
    )
    # Deferred royal pick (multicolor purchase that crossed a crown threshold):
    # abilities have resolved by now, so run the royal step before discard. The
    # flag is one-shot; clear it whether or not royals remain available.
    if state.pending_royal:
        state = replace(state, pending_royal=False)
        if state.royals_available:
            return replace(state, phase=Phase.CHOOSE_ROYAL)
    if helpers.total_tokens(state.players[active].tokens) > helpers.TOKEN_LIMIT:
        # Defer the win check until after the player discards. ``extra_turn``
        # carries the pending-seat decision across the DISCARD decision point.
        return replace(
            state,
            phase=Phase.DISCARD,
            extra_turn=extra_turn,
        )
    return _finish_turn(state, active, extra_turn=extra_turn)


def _finish_turn(state: GameState, active: int, *, extra_turn: bool) -> GameState:
    """Check victory, then end the turn (extra turn keeps the seat).

    Spec §End of turn and victory: the win check happens only here, at the very
    end of the active player's turn, and an extra turn does not defer it.
    """
    if helpers.is_winner(state.players[active]):
        return replace(
            state,
            winner=active,
            current_player=active,
            phase=Phase.GAME_OVER,
            extra_turn=False,
        )
    if extra_turn:
        return replace(
            state,
            current_player=active,
            phase=Phase.USE_PRIVILEGES,
            extra_turn=True,
        )
    return replace(
        state,
        current_player=1 - active,
        phase=Phase.USE_PRIVILEGES,
        extra_turn=False,
    )
