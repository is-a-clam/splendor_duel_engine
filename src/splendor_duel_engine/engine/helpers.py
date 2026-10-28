"""Engine rule helpers.

These are the engine's mechanical rule queries. They contain no heuristics and
answer "what does the rule say", never "what is good". They are free functions
over state *fragments* so a caller can ask about a hypothetical hand.
"""

from __future__ import annotations

from itertools import product, combinations
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.colors import GEM_COLORS, PAY_COLORS, ALL_COLORS, Tokens, Color

if TYPE_CHECKING:
    from collections.abc import Iterable
    from splendor_duel_engine.engine.cards import Card
    from splendor_duel_engine.engine.state import PlayerState, PurchasedCard


TOKEN_LIMIT: int = 10
MAX_RESERVED: int = 3
PRESTIGE_WIN: int = 20
CROWNS_WIN: int = 10
COLOR_WIN_POINTS: int = 10


def _remaining_cost(cost: Tokens, bonus: Tokens) -> Tokens:
    """Compute remaining cost after applying bonuses (min 0 per color, pearls never reduced)."""
    return Tokens(
        white=max(0, cost.white - bonus.white),
        blue=max(0, cost.blue - bonus.blue),
        green=max(0, cost.green - bonus.green),
        red=max(0, cost.red - bonus.red),
        black=max(0, cost.black - bonus.black),
        pearl=max(0, cost.pearl - bonus.pearl),
        gold=0,
    )


def cost_deficits(cost: Tokens, bonus: Tokens, tokens: Tokens) -> Tokens:
    """Report missing tokens per color after bonuses and payment."""
    remaining = _remaining_cost(cost, bonus)
    deficits = _remaining_cost(remaining, tokens)
    return deficits


def can_afford_card(card: Card, bonus: Tokens, tokens: Tokens) -> bool:
    """Return whether the player may buy this card right now.

    A multicolor card may not be bought unless the player holds a bonus token
    in some gem color.
    """
    if card.is_multicolor and not any(get_tokens(bonus, color) > 0 for color in GEM_COLORS):
        return False
    deficits = cost_deficits(card.cost, bonus, tokens)
    shortfall = total_tokens(deficits)
    return shortfall <= tokens.gold


def legal_payments(card: Card, bonus: Tokens, tokens: Tokens) -> list[Tokens]:
    """Enumerate legal payments for buying ``card``.

    Returns every legal way to pay for ``card``.
    The result is empty exactly when :func:`can_afford_card` is false.
    The enumeration order is the white, blue, green, red, black, pearl loop
    order.
    """
    remaining = _remaining_cost(card.cost, bonus)
    deficits = _remaining_cost(remaining, tokens)
    total_gold_required = total_tokens(deficits)

    if total_gold_required > tokens.gold:
        return []

    gold_ranges: list[range] = []
    for color in PAY_COLORS:
        required_gold = get_tokens(deficits, color)
        extra_gold = tokens.gold - total_gold_required
        color_cost = get_tokens(remaining, color)
        gold_range = range(required_gold, min(required_gold + extra_gold, color_cost) + 1)
        gold_ranges.append(gold_range)

    return [
        Tokens(**({
            color.value: get_tokens(remaining, color) - substitution
            for color, substitution, in zip(PAY_COLORS, substitutions)
        } | {
            color.GOLD.value: sum(substitutions)
        }))
        for substitutions in product(*gold_ranges)
        if sum(substitutions) <= tokens.gold
    ]

def is_penalty_triggered(colors: Iterable[Color]) -> bool:
    """Return True if taking these colors triggers a penalty.

    True when any color appears three or more times, or when pearl appears
    two or more times.
    """
    counts: dict[Color, int] = {}
    for c in colors:
        counts[c] = counts.get(c, 0) + 1
    for color, cnt in counts.items():
        if color == Color.PEARL:
            if cnt >= 2:
                return True
        else:
            if cnt >= 3:
                return True
    return False


def color_points(purchased: Iterable[PurchasedCard], color: Color) -> int:
    """Sum card points for purchased cards of effective color ``color``."""
    points = 0
    for purchased_card in purchased:
        card = purchased_card.card
        if card.is_multicolor:
            effective_bonus = purchased_card.chosen_color
        else:
            effective_bonus = card.bonus
        if effective_bonus == color:
            points += card.points
    return points


def discard_subsets(tokens: Tokens, excess: int) -> list[Tokens]:
    """Enumerate distinct discard subsets of ``tokens`` summing to ``excess``."""
    token_list: list[Color] = []
    for color in ALL_COLORS:
        token_list.extend([color] * get_tokens(tokens, color))
    subsets = combinations(token_list, excess)
    return [Tokens(**{token.value: subset.count(token) for token in set(subset)}) for subset in subsets]


def can_reserve(board: tuple[Color | None, ...], reserved_count: int) -> bool:
    """Return True if the player may reserve.

    Requires gold on board and fewer than MAX_RESERVED reserved cards.
    """
    has_gold = any(color == Color.GOLD for color in board)
    return has_gold and reserved_count < MAX_RESERVED


def visible_cards(
    pyramid: tuple[tuple[Card | None, ...], ...],
    reserved_public: tuple[Card, ...],
    reserved_deck: tuple[Card, ...],
) -> list[Card]:
    """Return all visible cards in contract order.

    Order is pyramid row order (skipping None slots), then own public
    reservations, then own hidden deck reservations.
    """
    result: list[Card] = []
    for row in pyramid:
        for card in row:
            if card is not None:
                result.append(card)
    result.extend(reserved_public)
    result.extend(reserved_deck)
    return result


def is_winner(player: PlayerState) -> bool:
    """Return True if this player meets any win condition.

    Checked at end of their turn. Any one of:
      - prestige >= PRESTIGE_WIN (20)
      - crowns >= CROWNS_WIN (10)
      - >= COLOR_WIN_POINTS (10) prestige in a single gem color
    """
    if player.prestige >= PRESTIGE_WIN or player.crowns >= CROWNS_WIN:
        return True
    for color in GEM_COLORS:
        if color_points(player.purchased, color) >= COLOR_WIN_POINTS:
            return True
    return False
