"""Engine rule helpers.

These are the engine's mechanical rule queries. They contain no heuristics and
answer "what does the rule say", never "what is good". They are free functions
over state *fragments* so a caller can ask about a hypothetical hand.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens

if TYPE_CHECKING:
    from splendor_duel_engine.engine.cards import Card
    from splendor_duel_engine.engine.state import PlayerState, PurchasedCard

#: Token limit at end of turn (spec §End of turn and victory).
TOKEN_LIMIT: int = 10
#: Maximum reserved cards (spec §Privileges).
MAX_RESERVED: int = 3
#: Prestige win threshold (spec §End of turn and victory).
PRESTIGE_WIN: int = 20
#: Crowns win threshold (spec §End of turn and victory).
CROWNS_WIN: int = 10
#: Color-based prestige win threshold (spec §End of turn and victory).
COLOR_WIN_POINTS: int = 10


def count(tokens: Tokens, color: Color) -> int:
    """Return the number of tokens of ``color`` in ``tokens``."""
    return getattr(tokens, color.name.lower())


def total(tokens: Tokens) -> int:
    """Return the total number of tokens in ``tokens``."""
    return (
        tokens.white + tokens.blue + tokens.green + tokens.red +
        tokens.black + tokens.pearl + tokens.gold
    )


def add(t1: Tokens, t2: Tokens) -> Tokens:
    """Return the sum of two Tokens."""
    return Tokens(
        white=t1.white + t2.white,
        blue=t1.blue + t2.blue,
        green=t1.green + t2.green,
        red=t1.red + t2.red,
        black=t1.black + t2.black,
        pearl=t1.pearl + t2.pearl,
        gold=t1.gold + t2.gold,
    )


def sub(t1: Tokens, t2: Tokens) -> Tokens:
    """Return the difference of two Tokens (t1 - t2)."""
    return Tokens(
        white=t1.white - t2.white,
        blue=t1.blue - t2.blue,
        green=t1.green - t2.green,
        red=t1.red - t2.red,
        black=t1.black - t2.black,
        pearl=t1.pearl - t2.pearl,
        gold=t1.gold - t2.gold,
    )


def _remaining_cost(cost: Tokens, bonus: Tokens) -> Tokens:
    """Compute remaining cost after applying bonuses (min 0 per color, pearls never reduced).

    Gold is never a card cost per the rules; it is only a wild payment token.
    """
    return Tokens(
        white=max(0, cost.white - bonus.white),
        blue=max(0, cost.blue - bonus.blue),
        green=max(0, cost.green - bonus.green),
        red=max(0, cost.red - bonus.red),
        black=max(0, cost.black - bonus.black),
        pearl=cost.pearl,  # pearls never reduced
        gold=0,  # gold is never a card cost
    )


def cost_deficits(cost: Tokens, bonus: Tokens, paid: Tokens) -> dict[Color, int]:
    """Report missing tokens per colour after bonuses and payment.

    For each gem colour: max(0, max(0, cost - bonus) - paid). Pearls are never
    reduced by a bonus. Gold is ignored entirely (gold is never a card cost).
    Only colours with deficit > 0 are included. Ordered as GEM_COLORS then pearl.
    """
    deficits: dict[Color, int] = {}
    for colour in GEM_COLORS:
        missing = max(
            0, max(0, count(cost, colour) - count(bonus, colour)) - count(paid, colour)
        )
        if missing > 0:
            deficits[colour] = missing
    pearl_missing = max(0, cost.pearl - paid.pearl)
    if pearl_missing > 0:
        deficits[Color.PEARL] = pearl_missing
    return deficits


def can_afford_card(card: Card, tokens: Tokens, bonus: Tokens) -> bool:
    """Return whether the player may buy this card right now.

    Gold is wild and covers any shortfall. The multicolor rule is folded into
    this answer: a multicolor card may not be bought unless the player holds a
    bonus token in some gem colour. Pearls are never discounted by a bonus.
    This is the single affordability question for "may this player buy this
    card right now".
    """
    if card.is_multicolor and not any(count(bonus, colour) > 0 for colour in GEM_COLORS):
        return False
    deficits = cost_deficits(card.cost, bonus, tokens)
    shortfall = sum(deficits.values())
    return shortfall <= tokens.gold


def legal_payments(card: Card, tokens: Tokens, bonus: Tokens) -> list[Tokens]:
    """Enumerate legal payments for buying ``card``.

    Returns every legal way to pay for ``card``. For each combination of
    coloured tokens and pearls the player may spend, only the *minimum* gold
    needed to cover that combination's shortfall is yielded. The shortfall of
    a combination is taken from :func:`cost_deficits` -- the same public rule
    :func:`can_afford_card` uses -- so the gate and the enumeration can never
    disagree about what a colour is short.

    Spending gold beyond the shortfall is redundant rather than illegal:
    ``apply()`` accepts excess gold, but the enumeration never proposes it,
    because the extra gold buys nothing.

    The result is empty exactly when :func:`can_afford_card` is false, so
    ``decide()`` and ``apply()`` agree: a payment is offered exactly when it
    would be accepted.

    The enumeration order is the white, blue, green, red, black, pearl loop
    order.
    """
    if not can_afford_card(card, tokens, bonus):
        return []
    remaining = _remaining_cost(card.cost, bonus)
    legal: list[Tokens] = []

    for w in range(min(tokens.white, remaining.white) + 1):
        for b in range(min(tokens.blue, remaining.blue) + 1):
            for g in range(min(tokens.green, remaining.green) + 1):
                for r in range(min(tokens.red, remaining.red) + 1):
                    for bl in range(min(tokens.black, remaining.black) + 1):
                        for p in range(min(tokens.pearl, remaining.pearl) + 1):
                            paid = Tokens(
                                white=w,
                                blue=b,
                                green=g,
                                red=r,
                                black=bl,
                                pearl=p,
                            )
                            # One definition of the shortfall rule: cost_deficits.
                            deficit = sum(
                                cost_deficits(card.cost, bonus, paid).values()
                            )
                            if deficit <= tokens.gold:
                                legal.append(
                                    Tokens(
                                        white=w,
                                        blue=b,
                                        green=g,
                                        red=r,
                                        black=bl,
                                        pearl=p,
                                        gold=deficit,
                                    )
                                )

    # Deduplicate if necessary (enumeration shouldn't produce duplicates)
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


def take_penalty(colors: Iterable[Color]) -> bool:
    """Return True if taking these colours triggers a penalty.

    True when any colour appears three or more times, or when pearl appears
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
    """Sum card points for purchased cards of effective colour ``color``.

    For a multicolor card the effective colour is ``purchased_card.chosen_color``,
    for any other card it is ``card.bonus``. Cards with ``bonus is None``
    (colourless) contribute nothing. Card points only: bonus tokens are not
    points in a colour.
    """
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
    """Enumerate distinct discard subsets of ``tokens`` summing to ``excess``.

    Any colours count, including gold and pearls. The result excludes the
    empty subset (``excess`` is always >= 1 when called) and is deduplicated.
    """
    colors = tuple(Color)
    results: list[Tokens] = []
    seen: set[tuple[int, ...]] = set()

    def recurse(idx: int, counts: list[int], remaining: int) -> None:
        if remaining == 0:
            key = tuple(counts)
            if key not in seen:
                seen.add(key)
                results.append(Tokens(**{c.value: n for c, n in zip(colors, counts)}))
            return
        if idx == len(colors):
            return
        color = colors[idx]
        held = count(tokens, color)
        # Greedily cap this colour, but never below what the rest can absorb.
        for take in range(min(held, remaining), -1, -1):
            counts[idx] = take
            recurse(idx + 1, counts, remaining - take)
        counts[idx] = 0

    recurse(0, [0] * len(colors), excess)
    return results


def can_reserve(board: tuple[Color | None, ...], reserved_count: int) -> bool:
    """Return True if the player may reserve.

    Requires gold on board and fewer than MAX_RESERVED reserved cards.
    """
    has_gold = any(colour == Color.GOLD for colour in board)
    return has_gold and reserved_count < MAX_RESERVED


def visible_cards(
    pyramid: tuple[tuple[Card | None, ...], ...],
    reserved_public: tuple[Card, ...],
    reserved_deck: tuple[Card, ...],
) -> list[Card]:
    """Return all visible cards in contract order.

    Order is pyramid row order (skipping None slots), then own public
    reservations, then own hidden deck reservations. This order is part of the
    contract.
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
