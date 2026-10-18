"""Game actions and decision logic (Step API)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.cards import Ability, Card
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import (
    GameState,
    PlayerState,
    PurchasedCard,
    ReservedCard,
)

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
            if (
                idx2 is not None
                and board[idx2] is not None
                and board[idx2] != Color.GOLD
            ):
                result.add((start, idx2))
                r3, c3 = r + dr * 2, c + dc * 2
                idx3 = _rc_to_index(r3, c3)
                if (
                    idx3 is not None
                    and board[idx3] is not None
                    and board[idx3] != Color.GOLD
                ):
                    result.add((start, idx2, idx3))
    return sorted(result, key=lambda x: (len(x), x))


def _count_color_in_tokens(tokens_taken: list[Color]) -> dict[Color, int]:
    counts: dict[Color, int] = {}
    for c in tokens_taken:
        counts[c] = counts.get(c, 0) + 1
    return counts


def _remaining_cost_after_bonuses(card_cost: Tokens, bonus: Tokens) -> Tokens:
    """Compute remaining cost after applying bonuses (min 0 per color, pearls never reduced).

    Gold is never a card cost per the rules; it is only a wild payment token.
    """
    return Tokens(
        white=max(0, card_cost.white - bonus.white),
        blue=max(0, card_cost.blue - bonus.blue),
        green=max(0, card_cost.green - bonus.green),
        red=max(0, card_cost.red - bonus.red),
        black=max(0, card_cost.black - bonus.black),
        pearl=card_cost.pearl,  # pearls never reduced
        gold=0,  # gold is never a card cost
    )


def _can_afford(remaining_cost: Tokens, payment: Tokens) -> bool:
    """Check if payment covers remaining cost. Gold is wild."""
    # Calculate deficit after using colored tokens and pearls from payment
    deficit = 0
    for color in GEM_COLORS:
        paid = payment.count(color)
        needed = remaining_cost.count(color)
        deficit += max(0, needed - paid)
    # Pearl deficit
    deficit += max(0, remaining_cost.pearl - payment.pearl)
    # Gold in payment must cover total deficit
    return payment.gold >= deficit


def _enumerate_legal_payments(
    remaining_cost: Tokens, player_tokens: Tokens
) -> list[Tokens]:
    """Enumerate all legal payment combinations from player's tokens.

    For each combination of colored tokens and pearls, only the minimum gold
    needed to cover the deficit is yielded. Using excess gold is never beneficial
    and would bloat the action space. Complexity: O(prod(remaining_cost[c]+1))
    for colored tokens, which is small since costs are bounded (max ~6 per color).
    """
    legal: list[Tokens] = []

    # Iterate over possible colored token and pearl spending
    for w in range(min(player_tokens.white, remaining_cost.white) + 1):
        for b in range(min(player_tokens.blue, remaining_cost.blue) + 1):
            for g in range(min(player_tokens.green, remaining_cost.green) + 1):
                for r in range(min(player_tokens.red, remaining_cost.red) + 1):
                    for bl in range(min(player_tokens.black, remaining_cost.black) + 1):
                        for p in range(
                            min(player_tokens.pearl, remaining_cost.pearl) + 1
                        ):
                            # Compute minimum gold needed for this colored combination
                            deficit = 0
                            for color, paid in (
                                (Color.WHITE, w),
                                (Color.BLUE, b),
                                (Color.GREEN, g),
                                (Color.RED, r),
                                (Color.BLACK, bl),
                            ):
                                needed = remaining_cost.count(color)
                                deficit += max(0, needed - paid)
                            deficit += max(0, remaining_cost.pearl - p)

                            # Only yield if we have enough gold and it's within player's gold
                            if deficit <= player_tokens.gold:
                                payment = Tokens(
                                    white=w,
                                    blue=b,
                                    green=g,
                                    red=r,
                                    black=bl,
                                    pearl=p,
                                    gold=deficit,
                                )
                                legal.append(payment)

    # Deduplicate (should not be needed now, but kept for safety)
    unique = []
    seen = set()
    for payment in legal:
        key = (
            payment.white,
            payment.blue,
            payment.green,
            payment.red,
            payment.black,
            payment.pearl,
            payment.gold,
        )
        if key not in seen:
            seen.add(key)
            unique.append(payment)
    return unique


def _find_gold_on_board(board: tuple[Color | None, ...]) -> int | None:
    """Return index of a gold token on board, or None."""
    for idx, color in enumerate(board):
        if color == Color.GOLD:
            return idx
    return None


def _get_reserve_actions(state: GameState) -> list[ReserveCard]:
    """Enumerate all legal ReserveCard actions for the current player."""
    active = state.current_player
    ap = state.players[active]

    # Must have gold on board
    gold_idx = _find_gold_on_board(state.board)
    if gold_idx is None:
        return []

    # Must have fewer than 3 reserved cards
    if len(ap.reserved) >= 3:
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
        remaining = _remaining_cost_after_bonuses(card.cost, bonus)
        if _can_afford(remaining, ap.tokens):
            if card.is_multicolor:
                has_colored_bonus = any(bonus.count(c) > 0 for c in GEM_COLORS)
                if not has_colored_bonus:
                    continue
            buyable[card.id] = (card, "reserved")

    # Pyramid cards
    for row_idx, row in enumerate(state.pyramid):
        for col_idx, card in enumerate(row):
            if card is not None and card.id not in buyable:
                remaining = _remaining_cost_after_bonuses(card.cost, bonus)
                if _can_afford(remaining, ap.tokens):
                    if card.is_multicolor:
                        has_colored_bonus = any(bonus.count(c) > 0 for c in GEM_COLORS)
                        if not has_colored_bonus:
                            continue
                    source = f"pyramid_{row_idx}_{col_idx}"
                    buyable[card.id] = (card, source)

    return [BuyCard(card=card, source=source) for card, source in buyable.values()]


def _grant_privilege(
    players: tuple[PlayerState, PlayerState], recipient: int, supply: int
) -> tuple[tuple[PlayerState, PlayerState], int]:
    """Grant 1 privilege to recipient from supply, or steal from other player."""
    other = 1 - recipient
    new_players = [players[0], players[1]]
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
    return (new_players[0], new_players[1]), new_supply


def _apply_use_privilege(state: GameState, index: int) -> GameState:
    active = state.current_player
    ap = state.players[active]

    # Validate the index
    if index < 0 or index >= _BOARD_SIZE:
        raise ValueError(f"invalid board index {index}")
    color = state.board[index]
    if color is None or color == Color.GOLD:
        raise ValueError(f"no non-gold token at index {index}")

    new_board_list = list(state.board)
    new_board_list[index] = None
    new_board = tuple(new_board_list)

    # Add token to player's hand
    taken_tokens = Tokens(**{color.value: 1})
    new_ap = dataclasses.replace(
        ap, tokens=ap.tokens + taken_tokens, privileges=ap.privileges - 1
    )

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

    # Collect all tokens from bag into a list
    token_colors: list[Color] = []
    for color in Color:
        count = state.bag.count(color)
        token_colors.extend([color] * count)

    # Shuffle the tokens using state.rng
    state.rng.shuffle(token_colors)

    # Collect all empty board indices in SPIRAL order
    empty_indices = [idx for idx in SPIRAL if state.board[idx] is None]

    # Place tokens from shuffled list onto empty slots in SPIRAL order
    # (up to min(len(tokens), len(empty_slots)))
    board = list(state.board)
    placed_count = min(len(token_colors), len(empty_indices))
    for i in range(placed_count):
        board[empty_indices[i]] = token_colors[i]

    # New bag is empty (all tokens placed since total = 25)
    new_bag = Tokens()

    # Grant opponent 1 privilege
    new_players, new_priv_supply = _grant_privilege(
        state.players, opp, state.privileges_supply
    )

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
        new_players_list, new_priv_supply = _grant_privilege(
            tuple(new_players_list), opp, state.privileges_supply
        )

    return dataclasses.replace(
        state,
        players=tuple(new_players_list),
        board=new_board,
        privileges_supply=new_priv_supply,
        current_player=1 - state.current_player,
        phase=Phase.USE_PRIVILEGES,
    )


def _apply_reserve_card(state: GameState, action: ReserveCard) -> GameState:
    """Set pending_reserve and enter CHOOSE_GOLD phase."""
    # Validate gold is available on board
    gold_indices = [i for i, c in enumerate(state.board) if c == Color.GOLD]
    if not gold_indices:
        raise ValueError("no gold on board to reserve")

    # Validate source and card exist
    card: Card | None = None

    if action.source == "pyramid":
        row_idx = action.index // 10
        col_idx = action.index % 10
        if row_idx >= len(state.pyramid) or col_idx >= len(state.pyramid[row_idx]):
            raise ValueError("invalid pyramid index")
        card = state.pyramid[row_idx][col_idx]
        if card is None:
            raise ValueError("empty pyramid slot")
    elif action.source.startswith("deck_"):
        level = int(action.source.split("_")[1])
        deck_idx = 3 - level  # level 3->0, 2->1, 1->2
        if deck_idx < 0 or deck_idx >= len(state.decks):
            raise ValueError(f"invalid deck index {deck_idx}")
        deck = state.decks[deck_idx]
        if not deck:
            raise ValueError(f"deck level {level} empty")
        card = deck[-1]  # top card
    else:
        raise ValueError(f"unknown reserve source: {action.source}")

    # Check player has fewer than 3 reserved cards
    active = state.current_player
    ap = state.players[active]
    if len(ap.reserved) >= 3:
        raise ValueError("player already has 3 reserved cards")

    return dataclasses.replace(
        state,
        pending_reserve=action,
        phase=Phase.CHOOSE_GOLD,
    )


def _apply_choose_gold(state: GameState, index: int) -> GameState:
    """Take the chosen gold token and complete the reserve."""
    active = state.current_player
    ap = state.players[active]
    opp = 1 - active

    pending_action = state.pending_reserve
    if pending_action is None:
        raise ValueError("no pending reserve action")

    # Validate the index has a gold token
    if index < 0 or index >= _BOARD_SIZE:
        raise ValueError(f"invalid board index {index}")
    if state.board[index] != Color.GOLD:
        raise ValueError(f"no gold token at index {index}")

    # Take gold from board
    board = list(state.board)
    board[index] = None
    new_board = tuple(board)

    # Add gold to player's hand
    gold_tokens = Tokens(gold=1)
    new_ap = dataclasses.replace(ap, tokens=ap.tokens + gold_tokens)

    # Take the card from source (same logic as before, but card is known to exist)
    new_pyramid = [list(row) for row in state.pyramid]
    new_decks = [list(d) for d in state.decks]

    card: Card | None = None
    from_deck: bool = False

    if pending_action.source == "pyramid":
        row_idx = pending_action.index // 10
        col_idx = pending_action.index % 10
        card = state.pyramid[row_idx][col_idx]
        from_deck = False
        # Remove from pyramid
        new_pyramid[row_idx][col_idx] = None
        # Refill from corresponding deck
        deck = new_decks[row_idx]
        if deck:
            new_pyramid[row_idx][col_idx] = deck.pop()
    elif pending_action.source.startswith("deck_"):
        level = int(pending_action.source.split("_")[1])
        deck_idx = 3 - level
        deck = new_decks[deck_idx]
        card = deck.pop()
        from_deck = True
    else:
        raise ValueError(f"unknown reserve source: {pending_action.source}")

    # Add card to player's reserved
    reserved_card = ReservedCard(card=card, from_deck=from_deck)
    new_reserved = new_ap.reserved + (reserved_card,)
    new_ap = dataclasses.replace(new_ap, reserved=new_reserved)

    new_players_list = list(state.players)
    new_players_list[active] = new_ap

    return dataclasses.replace(
        state,
        players=tuple(new_players_list),
        board=new_board,
        pyramid=tuple(tuple(row) for row in new_pyramid),
        decks=tuple(tuple(d) for d in new_decks),
        pending_reserve=None,
        current_player=opp,
        phase=Phase.USE_PRIVILEGES,
    )


# ===== Ability resolution chain (Task 6) =====


def _resolve_multicolor(state: GameState, card: Card, active: int) -> GameState:
    """Enter MULTICOLOR_COLOR phase for a multicolor card."""
    ap = state.players[active]
    # Determine which colors are available (bonus.count > 0)
    available_colors = [c for c in GEM_COLORS if ap.bonus.count(c) > 0]
    if not available_colors:
        # Should not happen if buy was validated, but skip if so
        return _resolve_abilities(state, card, active)

    tuple(ChooseMulticolor(color=c) for c in available_colors)
    # Keep pending_buy so we know which card to update after color choice
    return dataclasses.replace(
        state,
        phase=Phase.MULTICOLOR_COLOR,
        pending_ability=None,
    )


def _resolve_steal_token(state: GameState, card: Card, active: int) -> GameState:
    """Enter STEAL_TOKEN phase if opponent has stealable tokens."""
    opp = 1 - active
    opp_tokens = state.players[opp].tokens
    # Non-gold colors opponent has
    stealable_colors = [c for c in GEM_COLORS if opp_tokens.count(c) > 0]
    if not stealable_colors:
        # No tokens to steal, continue to next ability
        return _resolve_take_matching_token(state, card, active)

    tuple(ChooseStealToken(color=c) for c in stealable_colors)
    return dataclasses.replace(
        state,
        phase=Phase.STEAL_TOKEN,
        pending_ability=Ability.STEAL_TOKEN,
    )


def _resolve_take_matching_token(
    state: GameState, card: Card, active: int
) -> GameState:
    """TAKE_MATCHING_TOKEN: auto-take 1 board token of card's bonus color if present."""
    if card.ability != Ability.TAKE_MATCHING_TOKEN:
        return _resolve_privilege(state, card, active)

    if card.bonus is None:
        return _resolve_privilege(state, card, active)

    # Find first token of card's bonus color on board
    bonus_color = card.bonus
    board = list(state.board)
    for idx, color in enumerate(board):
        if color == bonus_color:
            # Take it
            board[idx] = None
            new_board = tuple(board)
            taken = Tokens(**{bonus_color.value: 1})
            new_players = list(state.players)
            new_players[active] = dataclasses.replace(
                state.players[active], tokens=state.players[active].tokens + taken
            )
            state = dataclasses.replace(
                state,
                players=tuple(new_players),
                board=new_board,
            )
            break
    return _resolve_privilege(state, card, active)


def _resolve_privilege(state: GameState, card: Card, active: int) -> GameState:
    """PRIVILEGE: grant privilege via _grant_privilege."""
    if card.ability != Ability.PRIVILEGE:
        return _resolve_extra_turn(state, card, active)

    new_players, new_priv_supply = _grant_privilege(
        state.players, active, state.privileges_supply
    )
    return dataclasses.replace(
        state,
        players=new_players,
        privileges_supply=new_priv_supply,
    )


def _resolve_extra_turn(state: GameState, card: Card, active: int) -> GameState:
    """EXTRA_TURN: set extra_turn=True."""
    if card.ability != Ability.EXTRA_TURN:
        # No more abilities, go to USE_PRIVILEGES
        return dataclasses.replace(
            state,
            current_player=active,
            phase=Phase.USE_PRIVILEGES,
            extra_turn=False,
        )

    # Set extra_turn flag, stay in USE_PRIVILEGES for same player
    return dataclasses.replace(
        state,
        current_player=active,
        phase=Phase.USE_PRIVILEGES,
        extra_turn=True,
    )


def _resolve_abilities(state: GameState, card: Card, active: int) -> GameState:
    """Resolve abilities in fixed order after a card purchase."""
    # Order: multicolor -> steal_token -> take_matching_token -> privilege -> extra_turn
    if card.is_multicolor:
        return _resolve_multicolor(state, card, active)
    return _resolve_steal_token(state, card, active)


def _apply_buy_card(state: GameState, action: BuyCard) -> GameState:
    """Set pending_buy and enter CHOOSE_PAYMENT phase."""
    # The action already contains the card and source, just validate it's buyable
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

    # Verify affordability
    remaining = _remaining_cost_after_bonuses(card.cost, bonus)
    if not _can_afford(remaining, ap.tokens):
        raise ValueError("cannot afford card")

    # Multicolor restriction
    if card.is_multicolor:
        has_colored_bonus = any(bonus.count(c) > 0 for c in GEM_COLORS)
        if not has_colored_bonus:
            raise ValueError("cannot buy multicolor card without colored bonus")

    return dataclasses.replace(
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

    # Determine source and remove card from there
    new_players_list = list(state.players)
    new_pyramid = [list(row) for row in state.pyramid]
    new_decks = [list(d) for d in state.decks]

    if source == "reserved":
        # Remove from reserved
        for i, reserved in enumerate(ap.reserved):
            if reserved.card.id == card.id:
                new_reserved = ap.reserved[:i] + ap.reserved[i + 1 :]
                new_ap = dataclasses.replace(ap, reserved=new_reserved)
                new_players_list[active] = new_ap
                break
    elif source.startswith("pyramid_"):
        parts = source.split("_")
        row_idx = int(parts[1])
        col_idx = int(parts[2])
        new_pyramid[row_idx][col_idx] = None
        # Refill from corresponding deck
        deck = new_decks[row_idx]
        if deck:
            new_pyramid[row_idx][col_idx] = deck.pop()
    else:
        raise ValueError(f"unknown buy source: {source}")

    # Validate payment
    bonus = ap.bonus
    remaining = _remaining_cost_after_bonuses(card.cost, bonus)
    if not _can_afford(remaining, action.payment):
        raise ValueError("insufficient payment")
    # Also verify payment doesn't exceed player's tokens
    for color in Color:
        if action.payment.count(color) > ap.tokens.count(color):
            raise ValueError(f"payment exceeds tokens for {color}")

    # Move spent tokens to bag
    new_bag_dict = {color.value: state.bag.count(color) for color in Color}
    for color in Color:
        new_bag_dict[color.value] += action.payment.count(color)
    new_bag = Tokens(**new_bag_dict)

    # Remove tokens from player
    new_tokens = ap.tokens - action.payment
    new_ap = new_players_list[active]
    new_ap = dataclasses.replace(new_ap, tokens=new_tokens)
    new_players_list[active] = new_ap

    # Add card to purchased
    purchased_card = PurchasedCard(card=card, chosen_color=None)
    new_purchased = new_ap.purchased + (purchased_card,)
    new_ap = dataclasses.replace(new_ap, purchased=new_purchased)

    # Grant bonus, prestige, crowns
    new_bonus = Tokens(
        white=bonus.white + (1 if card.bonus == Color.WHITE else 0),
        blue=bonus.blue + (1 if card.bonus == Color.BLUE else 0),
        green=bonus.green + (1 if card.bonus == Color.GREEN else 0),
        red=bonus.red + (1 if card.bonus == Color.RED else 0),
        black=bonus.black + (1 if card.bonus == Color.BLACK else 0),
        pearl=0,
        gold=0,
    )
    # Multicolor cards have bonus=None, so no bonus granted
    if card.bonus is not None:
        new_ap = dataclasses.replace(new_ap, bonus=new_bonus)
    new_ap = dataclasses.replace(
        new_ap,
        prestige=new_ap.prestige + card.points,
        crowns=new_ap.crowns + card.crowns,
    )
    new_players_list[active] = new_ap

    # Check win conditions
    winner = None
    if new_ap.prestige >= 20 or new_ap.crowns >= 10:
        winner = active
    # 10 points in a single color (spec: multicolor cards count as their chosen color;
    # colorless no-bonus cards and royals do not count)
    for color in GEM_COLORS:
        color_points = 0
        for pc in new_ap.purchased:
            if pc.card.is_multicolor:
                if pc.chosen_color == color:
                    color_points += pc.card.points
            elif pc.card.bonus == color:
                color_points += pc.card.points
        if color_points >= 10:
            winner = active
            break

    # Start ability resolution chain
    if winner is not None:
        # Game over, no abilities resolve
        return dataclasses.replace(
            state,
            players=tuple(new_players_list),
            bag=new_bag,
            pyramid=tuple(tuple(row) for row in new_pyramid),
            decks=tuple(tuple(d) for d in new_decks),
            pending_buy=None,
            winner=winner,
            current_player=active,
            phase=Phase.GAME_OVER,
        )

    return _resolve_abilities(
        dataclasses.replace(
            state,
            players=tuple(new_players_list),
            bag=new_bag,
            pyramid=tuple(tuple(row) for row in new_pyramid),
            decks=tuple(tuple(d) for d in new_decks),
            pending_buy=pending_action,  # Keep for multicolor resolution
            winner=None,
            current_player=active,
            phase=Phase.USE_PRIVILEGES,  # Will be overridden by resolution
            extra_turn=False,
            pending_ability=None,
        ),
        card,
        active,
    )


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
        if state.bag.total() > 0:
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
        if not actions and state.bag.total() > 0:
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
        remaining = _remaining_cost_after_bonuses(pending_action.card.cost, bonus)
        legal_payments = _enumerate_legal_payments(remaining, ap.tokens)
        actions: list[Action] = [PayTokens(payment=p) for p in legal_payments]
        return DecisionPoint(phase=Phase.CHOOSE_PAYMENT, legal_actions=tuple(actions))

    if state.phase == Phase.MULTICOLOR_COLOR:
        pending_action = state.pending_buy
        if pending_action is None:
            return DecisionPoint(phase=Phase.MULTICOLOR_COLOR, legal_actions=())
        ap = state.players[state.current_player]
        available_colors = [c for c in GEM_COLORS if ap.bonus.count(c) > 0]
        actions: list[Action] = [ChooseMulticolor(color=c) for c in available_colors]
        return DecisionPoint(phase=Phase.MULTICOLOR_COLOR, legal_actions=tuple(actions))

    if state.phase == Phase.STEAL_TOKEN:
        if state.pending_ability != Ability.STEAL_TOKEN:
            return DecisionPoint(phase=Phase.STEAL_TOKEN, legal_actions=())
        opp = 1 - state.current_player
        opp_tokens = state.players[opp].tokens
        stealable_colors = [c for c in GEM_COLORS if opp_tokens.count(c) > 0]
        actions: list[Action] = [ChooseStealToken(color=c) for c in stealable_colors]
        return DecisionPoint(phase=Phase.STEAL_TOKEN, legal_actions=tuple(actions))

    return DecisionPoint(phase=state.phase, legal_actions=())


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
    # The last purchased card is the multicolor one
    last_pc = purchased_list[-1]
    if last_pc.card.id != card.id:
        raise ValueError("purchased card mismatch")
    updated_pc = PurchasedCard(card=card, chosen_color=color)
    purchased_list[-1] = updated_pc

    # Add bonus_count of chosen color to player's bonus
    new_bonus = Tokens(
        white=ap.bonus.white + (card.bonus_count if color == Color.WHITE else 0),
        blue=ap.bonus.blue + (card.bonus_count if color == Color.BLUE else 0),
        green=ap.bonus.green + (card.bonus_count if color == Color.GREEN else 0),
        red=ap.bonus.red + (card.bonus_count if color == Color.RED else 0),
        black=ap.bonus.black + (card.bonus_count if color == Color.BLACK else 0),
        pearl=0,
        gold=0,
    )
    new_ap = dataclasses.replace(ap, bonus=new_bonus, purchased=tuple(purchased_list))
    new_players = list(state.players)
    new_players[active] = new_ap

    # Continue with remaining abilities (steal_token -> take_matching_token -> privilege -> extra_turn)
    return _resolve_steal_token(
        dataclasses.replace(
            state,
            players=tuple(new_players),
            pending_buy=None,
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

    if opp_tokens.count(color) == 0:
        raise ValueError(f"opponent has no {color} tokens to steal")

    # Remove token from opponent
    opp_lost = Tokens(**{color.value: -1})
    new_opp = dataclasses.replace(
        state.players[opp], tokens=state.players[opp].tokens + opp_lost
    )

    # Add token to active player
    active_gained = Tokens(**{color.value: 1})
    new_active = dataclasses.replace(
        state.players[active], tokens=state.players[active].tokens + active_gained
    )

    new_players = list(state.players)
    new_players[active] = new_active
    new_players[opp] = new_opp

    # Continue with remaining abilities
    pending_action = state.pending_buy
    card = pending_action.card if pending_action else None
    if card is None:
        # Should not happen, but fallback
        return dataclasses.replace(
            state,
            players=tuple(new_players),
            pending_ability=None,
            phase=Phase.USE_PRIVILEGES,
        )

    return _resolve_take_matching_token(
        dataclasses.replace(
            state,
            players=tuple(new_players),
            pending_ability=None,
        ),
        card,
        active,
    )


def apply(state: GameState, action: Action) -> GameState:
    dp = decide(state)
    if action not in dp.legal_actions:
        raise ValueError("illegal action")

    if isinstance(action, UsePrivilege):
        return _apply_use_privilege(state, action.index)
    if isinstance(action, DoneWithPrivileges):
        # Advance to REPLENISH
        return dataclasses.replace(state, phase=Phase.REPLENISH)
    if isinstance(action, Replenish):
        return _apply_replenish(state)
    if isinstance(action, DoneWithReplenish):
        # If extra_turn flag is set, consume it and stay with same player
        if state.extra_turn:
            return dataclasses.replace(state, phase=Phase.MANDATORY, extra_turn=False)
        return dataclasses.replace(state, phase=Phase.MANDATORY)
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
    return state
