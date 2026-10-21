"""Immutable game state and deterministic setup.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup" and
"Hidden information". Setup is fully reproducible from a seed: the RNG is
consumed in a pinned order so a future Rust engine can be fuzzed against this
reference.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.cards import Ability, Card, RoyalCard, load_cards
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.phase import Phase

if TYPE_CHECKING:
    from splendor_duel_engine.engine.actions import BuyCard, ReserveCard

#: ``(row_length, deck_index)`` for the ``pyramid`` rows in order (level 3,
#: level 2, level 1). ``decks`` is stored in the same order — index 0/1/2 is
#: level 3/2/1 — so a row always refills from ``decks[row]``. The brief's setup
#: assertion ``[len(d) for d in decks] == [10, 20, 25]`` pins this order
#: (level 3 minus its 3 pyramid cards, etc.), matching the pyramid ordering.
_PYRAMID_LAYOUT: tuple[tuple[int, int], ...] = ((3, 0), (4, 1), (5, 2))

#: Total privilege scrolls in the game (spec §Privileges); the second player
#: starts with one, leaving the rest in the supply.
_TOTAL_PRIVILEGES: int = 3

#: The 25-token supply in the order it is shuffled at setup (spec: 4 each of
#: the five gems, 2 pearls, 3 gold). Pinned so the deal is reproducible.
_TOKEN_SUPPLY: tuple[Color, ...] = (
    tuple(color for color in GEM_COLORS for _ in range(4))
    + (Color.PEARL,) * 2
    + (Color.GOLD,) * 3
)


@dataclass(frozen=True, slots=True)
class PurchasedCard:
    """A card a player has bought, plus its multicolor choice if any.

    ``chosen_color`` is set when a multicolor card is purchased; it is ``None``
    for ordinary purchases.
    """

    card: Card
    chosen_color: Color | None


@dataclass(frozen=True, slots=True)
class ReservedCard:
    """A card a player holds in reserve.

    ``from_deck`` is ``True`` when reserved from a deck top (its identity is
    hidden from the opponent) and ``False`` when reserved from the pyramid
    (public). Spec §Hidden information.
    """

    card: Card
    from_deck: bool


@dataclass(frozen=True, slots=True)
class PlayerState:
    """One player's full state. Spec §Hidden information (public by deduction)."""

    tokens: Tokens
    #: Colour bonuses. Reuses :class:`Tokens`, but only gem counts are allowed:
    #: ``bonus.pearl`` and ``bonus.gold`` must stay 0. Task 6 must preserve this.
    bonus: Tokens
    prestige: int
    crowns: int
    reserved: tuple[ReservedCard, ...]
    purchased: tuple[PurchasedCard, ...]
    privileges: int

    def color_prestige(self, color: Color) -> int:
        """Return total prestige points in the given color.

        Includes points from purchased cards whose bonus matches the color,
        and the bonus counts themselves (each bonus counts as 1 point in that color).
        For multicolor cards, the chosen_color determines which color gets the points.
        """
        total = 0
        for pc in self.purchased:
            card = pc.card
            # Determine the effective bonus color for this card
            effective_bonus = pc.chosen_color if card.is_multicolor else card.bonus
            if effective_bonus == color:
                # Card points count toward that color's prestige
                total += card.points
                # Each bonus also counts as 1 point in that color
                total += card.bonus_count
        return total


@dataclass(frozen=True, slots=True)
class GameState:
    """The complete, immutable state of a game.

    ``board`` is 25 row-major entries (``None`` only ever marks an empty token
    space). ``decks`` is indexed 0/1/2 for levels 1/2/3 with the top card last
    (dealt by popping the end). ``pyramid`` rows are levels 3, 2, 1 (lengths
    3, 4, 5); a slot is ``None`` only when its deck is exhausted.
    """

    players: tuple[PlayerState, PlayerState]
    board: tuple[Color | None, ...]
    bag: Tokens
    decks: tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]]
    pyramid: tuple[tuple[Card | None, ...], ...]
    royals_available: tuple[RoyalCard, ...]
    privileges_supply: int
    current_player: int
    winner: int | None
    phase: Phase
    pending_buy: BuyCard | None
    pending_reserve: ReserveCard | None
    #: Excluded from equality/repr: two games from the same seed compare equal
    #: even though their RNG streams are separate objects.
    rng: random.Random = field(compare=False, repr=False)
    #: True when the current player has earned an extra turn (via EXTRA_TURN
    #: ability or royal). Cleared when the extra turn is consumed.
    extra_turn: bool = False
    #: Stores the ability being resolved during a decision point phase
    #: (STEAL_TOKEN). None otherwise.
    pending_ability: Ability | None = None
    #: True when a purchase crossed a crown threshold but the royal pick was
    #: deferred because the card was multicolor (its color must be chosen
    #: first). Cleared when the royal step runs in ``_end_of_turn``.
    pending_royal: bool = False


def new_game(seed: int) -> GameState:
    """Return a fresh game set up deterministically from ``seed``.

    RNG consumption is pinned for reproducibility: (a) shuffle decks level 1,
    then 2, then 3; (b) deal the pyramid; (c) shuffle the 25-token supply and
    deal it along :data:`SPIRAL`; (d) choose the first player.
    """
    rng = random.Random(seed)
    jewels, royals = load_cards()

    # (a) Shuffle each deck separately, level 1 then 2 then 3 (pinned RNG
    # order). Each shuffled list is stored so decks[0/1/2] is level 3/2/1,
    # matching the pyramid rows; the deck top is the last element.
    shuffled: dict[int, list[Card]] = {}
    for level in (1, 2, 3):
        level_cards = [card for card in jewels if card.level == level]
        rng.shuffle(level_cards)
        shuffled[level] = level_cards
    decks = [shuffled[3], shuffled[2], shuffled[1]]

    # (b) Deal the pyramid, each row left-to-right from its deck's top.
    pyramid = tuple(
        tuple(decks[deck_index].pop() for _ in range(row_length))
        for row_length, deck_index in _PYRAMID_LAYOUT
    )

    # (c) Shuffle the token supply once and deal it along the spiral.
    supply = list(_TOKEN_SUPPLY)
    rng.shuffle(supply)
    board: list[Color | None] = [None] * len(SPIRAL)
    for index, color in zip(SPIRAL, supply, strict=True):
        board[index] = color

    # (d) Pick the first player.
    current_player = rng.randrange(2)

    players = (
        _fresh_player(0 if current_player == 0 else 1),
        _fresh_player(0 if current_player == 1 else 1),
    )

    return GameState(
        players=players,
        board=tuple(board),
        bag=Tokens(),
        decks=(tuple(decks[0]), tuple(decks[1]), tuple(decks[2])),
        pyramid=pyramid,
        royals_available=royals,
        privileges_supply=_TOTAL_PRIVILEGES - 1,  # second player took one
        current_player=current_player,
        winner=None,
        # First player opens in USE_PRIVILEGES (plan pre-flight ruling,
        # conflict-1). They hold 0 privileges and the bag is empty, so both
        # opening steps are no-ops, but the phase matches the plan interface.
        phase=Phase.USE_PRIVILEGES,
        pending_buy=None,
        pending_reserve=None,
        rng=rng,
        extra_turn=False,
        pending_ability=None,
    )


def _fresh_player(privileges: int) -> PlayerState:
    return PlayerState(
        tokens=Tokens(),
        # Bonus holds gem counts only; pearl/gold bonuses are impossible
        # in the card data, so they stay 0 (invariant for Task 6).
        bonus=Tokens(),
        prestige=0,
        crowns=0,
        reserved=(),
        purchased=(),
        privileges=privileges,
    )
