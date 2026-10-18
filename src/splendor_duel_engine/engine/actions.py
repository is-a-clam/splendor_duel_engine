"""Game actions and decision logic (Step API)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.cards import Card
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
    """Compute remaining cost after applying bonuses (min 0 per color, pearls never reduced)."""
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
    """Enumerate all legal payment combinations from player's tokens."""
    legal: list[Tokens] = []

    # For each possible amount of gold to use (0 to player_tokens.gold)
    for gold_used in range(player_tokens.gold + 1):
        # Let's iterate over possible colored token spending
        for w in range(min(player_tokens.white, remaining_cost.white) + 1):
            for b in range(min(player_tokens.blue, remaining_cost.blue) + 1):
                for g in range(min(player_tokens.green, remaining_cost.green) + 1):
                    for r in range(min(player_tokens.red, remaining_cost.red) + 1):
                        for bl in range(
                            min(player_tokens.black, remaining_cost.black) + 1
                        ):
                            for p in range(
                                min(player_tokens.pearl, remaining_cost.pearl) + 1
                            ):
                                payment = Tokens(
                                    white=w,
                                    blue=b,
                                    green=g,
                                    red=r,
                                    black=bl,
                                    pearl=p,
                                    gold=gold_used,
                                )
                                if _can_afford(remaining_cost, payment):
                                    legal.append(payment)

    # Deduplicate
    unique = []
    seen = set()
    for p in legal:
        key = (p.white, p.blue, p.green, p.red, p.black, p.pearl, p.gold)
        if key not in seen:
            seen.add(key)
            unique.append(p)
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


def _get_buyable_cards(state: GameState) -> list[tuple[str, Card, str]]:
    """Return list of (card_id, card, source) for cards the active player can buy.

    Source is "reserved" or "pyramid" with row/col encoded.
    """
    active = state.current_player
    ap = state.players[active]
    bonus = ap.bonus

    buyable: list[tuple[str, Card, str]] = []

    # Own reserved cards
    for reserved in ap.reserved:
        card = reserved.card
        remaining = _remaining_cost_after_bonuses(card.cost, bonus)
        # Check if affordable with current tokens + gold
        if _can_afford(remaining, ap.tokens):
            # Multicolor restriction: must have at least one colored bonus
            if card.is_multicolor:
                has_colored_bonus = any(bonus.count(c) > 0 for c in GEM_COLORS)
                if not has_colored_bonus:
                    continue
            buyable.append((card.id, card, "reserved"))

    # Pyramid cards
    for row_idx, row in enumerate(state.pyramid):
        for col_idx, card in enumerate(row):
            if card is not None:
                remaining = _remaining_cost_after_bonuses(card.cost, bonus)
                if _can_afford(remaining, ap.tokens):
                    if card.is_multicolor:
                        has_colored_bonus = any(bonus.count(c) > 0 for c in GEM_COLORS)
                        if not has_colored_bonus:
                            continue
                    source = f"pyramid_{row_idx}_{col_idx}"
                    buyable.append((card.id, card, source))

    return buyable


def _grant_privilege(
    players: tuple[PlayerState, PlayerState], recipient: int, supply: int
) -> tuple[tuple[PlayerState, PlayerState], int]:
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

    # Draw from bag onto empty spaces in SPIRAL order
    board = list(state.board)
    bag = state.bag

    # Collect available tokens from bag in a deterministic order.
    # This fixed order (WHITE, BLUE, GREEN, RED, BLACK, PEARL, GOLD) is arbitrary but
    # ensures reproducibility; the spec does not prescribe a bag-draw order.
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
        opp_state = state.players[opp]
        if state.privileges_supply > 0:
            new_priv_supply = state.privileges_supply - 1
            new_opp = dataclasses.replace(
                opp_state, privileges=opp_state.privileges + 1
            )
            new_players_list[opp] = new_opp
        else:
            if new_ap.privileges > 0:
                new_ap_pen = dataclasses.replace(
                    new_ap, privileges=new_ap.privileges - 1
                )
                new_opp = dataclasses.replace(
                    opp_state, privileges=opp_state.privileges + 1
                )
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


def _apply_reserve_card(state: GameState, action: ReserveCard) -> GameState:
    active = state.current_player
    ap = state.players[active]
    opp = 1 - active

    # Take gold from board (first gold found)
    board = list(state.board)
    gold_idx = _find_gold_on_board(state.board)
    if gold_idx is None:
        raise ValueError("no gold on board to reserve")
    board[gold_idx] = None
    new_board = tuple(board)

    # Add gold to player's hand
    gold_tokens = Tokens(gold=1)
    new_ap = dataclasses.replace(ap, tokens=ap.tokens + gold_tokens)

    # Take the card from source
    card: Card
    from_deck: bool
    new_pyramid = [list(row) for row in state.pyramid]
    new_decks = [list(d) for d in state.decks]

    if action.source == "pyramid":
        row_idx = action.index // 10
        col_idx = action.index % 10
        card = state.pyramid[row_idx][col_idx]
        if card is None:
            raise ValueError("empty pyramid slot")
        from_deck = False
        # Remove from pyramid
        new_pyramid[row_idx][col_idx] = None
        # Refill from corresponding deck (same row index)
        deck = new_decks[row_idx]
        if deck:
            new_pyramid[row_idx][col_idx] = deck.pop()
    elif action.source.startswith("deck_"):
        level = int(action.source.split("_")[1])
        deck_idx = 3 - level  # level 3->0, 2->1, 1->2
        deck = new_decks[deck_idx]
        if not deck:
            raise ValueError(f"deck level {level} empty")
        card = deck.pop()
        from_deck = True
    else:
        raise ValueError(f"unknown reserve source: {action.source}")

    # Add card to player's reserved
    reserved_card = ReservedCard(card=card, from_deck=from_deck)
    new_reserved = ap.reserved + (reserved_card,)
    new_ap = dataclasses.replace(new_ap, reserved=new_reserved)

    new_players_list = list(state.players)
    new_players_list[active] = new_ap

    return dataclasses.replace(
        state,
        players=tuple(new_players_list),
        board=new_board,
        pyramid=tuple(tuple(row) for row in new_pyramid),
        decks=tuple(tuple(d) for d in new_decks),
        current_player=opp,
        phase=Phase.USE_PRIVILEGES,
    )


def _apply_buy_card(state: GameState, action: BuyCard) -> GameState:
    """Set pending card and enter CHOOSE_PAYMENT phase."""
    active = state.current_player
    ap = state.players[active]

    # Find the card being bought
    card: Card | None = None
    source_type: str | None = None

    # Check reserved cards
    for reserved in ap.reserved:
        if reserved.card.id == action.card_id:
            card = reserved.card
            source_type = "reserved"
            break

    # Check pyramid
    if card is None:
        for r_idx, row in enumerate(state.pyramid):
            for c_idx, pyr_card in enumerate(row):
                if pyr_card is not None and pyr_card.id == action.card_id:
                    card = pyr_card
                    source_type = "pyramid"
                    break
            if card is not None:
                break

    if card is None or source_type is None:
        raise ValueError(f"card {action.card_id} not found in buyable cards")

    return dataclasses.replace(
        state,
        pending=card,
        phase=Phase.CHOOSE_PAYMENT,
    )


def _apply_pay_tokens(state: GameState, action: PayTokens) -> GameState:
    active = state.current_player
    ap = state.players[active]

    pending_card = state.pending
    if pending_card is None:
        raise ValueError("no pending card to pay for")

    # Determine source and remove card from there
    new_players_list = list(state.players)
    new_pyramid = [list(row) for row in state.pyramid]
    new_decks = [list(d) for d in state.decks]

    source_type: str | None = None

    # Check reserved
    for i, reserved in enumerate(ap.reserved):
        if reserved.card.id == pending_card.id:
            source_type = "reserved"
            # Remove from reserved
            new_reserved = ap.reserved[:i] + ap.reserved[i + 1 :]
            new_ap = dataclasses.replace(ap, reserved=new_reserved)
            new_players_list[active] = new_ap
            break

    # Check pyramid
    if source_type is None:
        for r_idx, row in enumerate(state.pyramid):
            for c_idx, pyr_card in enumerate(row):
                if pyr_card is not None and pyr_card.id == pending_card.id:
                    source_type = "pyramid"
                    new_pyramid[r_idx][c_idx] = None
                    # Refill from corresponding deck
                    deck = new_decks[r_idx]
                    if deck:
                        new_pyramid[r_idx][c_idx] = deck.pop()
                    break
            if source_type is not None:
                break

    if source_type is None:
        raise ValueError("pending card not found in reserved or pyramid")

    # Validate payment
    bonus = ap.bonus
    remaining = _remaining_cost_after_bonuses(pending_card.cost, bonus)
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
    purchased_card = PurchasedCard(card=pending_card, chosen_color=None)
    new_purchased = new_ap.purchased + (purchased_card,)
    new_ap = dataclasses.replace(new_ap, purchased=new_purchased)

    # Grant bonus, prestige, crowns
    new_bonus = Tokens(
        white=bonus.white + (1 if pending_card.bonus == Color.WHITE else 0),
        blue=bonus.blue + (1 if pending_card.bonus == Color.BLUE else 0),
        green=bonus.green + (1 if pending_card.bonus == Color.GREEN else 0),
        red=bonus.red + (1 if pending_card.bonus == Color.RED else 0),
        black=bonus.black + (1 if pending_card.bonus == Color.BLACK else 0),
        pearl=0,
        gold=0,
    )
    # Multicolor cards have bonus=None, so no bonus granted
    if pending_card.bonus is not None:
        new_ap = dataclasses.replace(new_ap, bonus=new_bonus)
    new_ap = dataclasses.replace(
        new_ap,
        prestige=new_ap.prestige + pending_card.points,
        crowns=new_ap.crowns + pending_card.crowns,
    )
    new_players_list[active] = new_ap

    # Check win conditions
    winner = None
    if new_ap.prestige >= 20 or new_ap.crowns >= 10:
        winner = active
    # 10 points in a single color
    for color in GEM_COLORS:
        # Count points from cards with this bonus color
        color_points = sum(
            pc.card.points for pc in new_ap.purchased if pc.card.bonus == color
        )
        if color_points >= 10:
            winner = active
            break

    return dataclasses.replace(
        state,
        players=tuple(new_players_list),
        bag=new_bag,
        pyramid=tuple(tuple(row) for row in new_pyramid),
        decks=tuple(tuple(d) for d in new_decks),
        pending=None,
        winner=winner,
        current_player=active,  # Same player continues (Task 6: ability resolution here)
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
                if (
                    color is not None
                    and color != Color.GOLD
                    and color not in seen_colors
                ):
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

        # Reserve actions
        actions.extend(_get_reserve_actions(state))

        # Buy actions (own reserved + pyramid)
        for card_id, card, source in _get_buyable_cards(state):
            actions.append(BuyCard(card_id=card_id))

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
        pending_card = state.pending
        if pending_card is None:
            return DecisionPoint(phase=Phase.CHOOSE_PAYMENT, legal_actions=())
        ap = state.players[state.current_player]
        bonus = ap.bonus
        remaining = _remaining_cost_after_bonuses(pending_card.cost, bonus)
        legal_payments = _enumerate_legal_payments(remaining, ap.tokens)
        actions: list[Action] = [PayTokens(payment=p) for p in legal_payments]
        return DecisionPoint(phase=Phase.CHOOSE_PAYMENT, legal_actions=tuple(actions))

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
    if isinstance(action, ReserveCard):
        return _apply_reserve_card(state, action)
    if isinstance(action, BuyCard):
        return _apply_buy_card(state, action)
    if isinstance(action, PayTokens):
        return _apply_pay_tokens(state, action)
    return state
