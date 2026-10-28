"""Immutable game state and deterministic setup.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup" and
"Hidden information". Setup is fully reproducible from a seed: the RNG is
consumed in a pinned order so a future Rust engine can be fuzzed against this
reference.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.cards import load_cards
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.phase import Phase

if TYPE_CHECKING:
    from splendor_duel_engine.engine.cards import Ability, Card, RoyalCard
    from splendor_duel_engine.engine.actions import BuyCard, ReserveCard


TOTAL_PRIVILEGES: int = 3
GEM_TOTAL: int = 4
PEARL_TOTAL: int = 2
GOLD_TOTAL: int = 3
TOKEN_SUPPLY: tuple[Color, ...] = (
    tuple(color for color in GEM_COLORS for _ in range(GEM_TOTAL))
    + (Color.PEARL,) * PEARL_TOTAL
    + (Color.GOLD,) * GOLD_TOTAL
)
PYRAMID_LAYOUT: tuple[tuple[int, int], ...] = ((3, 0), (4, 1), (5, 2))


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
    hidden from the opponent) and ``False`` when reserved from the pyramid.
    """

    card: Card
    from_deck: bool


@dataclass(frozen=True, slots=True)
class PlayerState:
    """One player's full state"""

    tokens: Tokens
    bonus: Tokens
    prestige: int
    crowns: int
    reserved: tuple[ReservedCard, ...]
    purchased: tuple[PurchasedCard, ...]
    privileges: int


@dataclass(frozen=True, slots=True)
class GameState:
    """The complete, immutable state of a game.

    ``board`` is 25 row-major entries (``None`` marks an empty token space).
    ``decks`` is indexed 0/1/2 for levels 1/2/3 with the top card last.
    ``pyramid`` rows are levels 3, 2, 1 (lengths 3, 4, 5); a slot is ``None``
    only when its deck is exhausted.
    """

    rng: random.Random = field(compare=False, repr=False)

    players: tuple[PlayerState, PlayerState]
    board: tuple[Color | None, ...]
    bag: Tokens
    decks: tuple[tuple[Card, ...], ...]
    pyramid: tuple[tuple[Card | None, ...], ...]
    royals_available: tuple[RoyalCard, ...]
    privileges_supply: int
    current_player: int
    winner: int | None
    phase: Phase
    pending_buy: BuyCard | None
    pending_reserve: ReserveCard | None
    extra_turn: bool = False
    pending_ability: Ability | None = None
    pending_royal: bool = False

    # ===== State update methods =====

    def update_player(self, player_idx: int, new_player: PlayerState) -> GameState:
        """Replace one player in the players tuple."""
        players = list(self.players)
        players[player_idx] = new_player
        new_players = (players[0], players[1])
        return replace(self, players=new_players)

    def update_board(self, idx: int, new_color: Color | None) -> GameState:
        """Update a single board index."""
        board = list(self.board)
        board[idx] = new_color
        new_board = tuple(board)
        return replace(self, board=new_board)

    def remove_from_board(self, idx: int) -> GameState:
        """Set a board index to None (remove token)."""
        board = list(self.board)
        board[idx] = None
        new_board = tuple(board)
        return replace(self, board=new_board)

    def add_to_bag(self, tokens: Tokens) -> GameState:
        """Add tokens to bag."""
        new_bag = self.bag + tokens
        return replace(self, bag=new_bag)

    def pop_deck(self, deck_idx: int) -> tuple[Card, GameState]:
        """Pop top card from deck and return (card, new_state)."""
        decks = [list(d) for d in self.decks]
        card = decks[deck_idx].pop()
        new_decks = tuple(tuple(d) for d in decks)
        return card, replace(self, decks=new_decks)

    def take_pyramid_card(self, row_idx: int, col_idx: int) -> tuple[Card | None, GameState]:
        """Take card from pyramid slot and refill from corresponding deck in one atomic operation.

        Returns (card, new_state). If the corresponding deck is empty, the slot stays empty.
        """
        pyramid = [list(r) for r in self.pyramid]
        decks = [list(d) for d in self.decks]

        card = pyramid[row_idx][col_idx]
        pyramid[row_idx][col_idx] = None

        # Refill from corresponding deck
        deck = decks[row_idx]
        if deck:
            pyramid[row_idx][col_idx] = deck.pop()

        new_pyramid = tuple(tuple(r) for r in pyramid)
        new_decks = tuple(tuple(d) for d in decks)

        return card, replace(self, pyramid=new_pyramid, decks=new_decks)

    def grant_privilege(self, recipient: int) -> GameState:
        """Grant 1 privilege to recipient from supply, or steal from other player."""
        other = 1 - recipient
        players = [self.players[0], self.players[1]]
        supply = self.privileges_supply

        if supply > 0:
            supply = self.privileges_supply - 1
            players[recipient] = replace(
                players[recipient],
                privileges=players[recipient].privileges + 1,
            )
        elif self.players[other].privileges > 0:
            players[other] = replace(
                players[other],
                privileges=players[other].privileges - 1
            )
            players[recipient] = replace(
                players[recipient],
                privileges=players[recipient].privileges + 1,
            )
        
        new_players = (players[0], players[1])

        return replace(self, players=new_players, privileges_supply=supply,)

    # ===== Factory class methods =====

    @classmethod
    def new_game(cls, seed: int) -> GameState:
        """Create a fresh game state from seed (the standard entry point)."""
        rng = random.Random(seed)
        jewels, royals = load_cards()

        # Shuffle each deck separately.
        shuffled: dict[int, list[Card]] = {}
        for level in (1, 2, 3):
            level_cards = [card for card in jewels if card.level == level]
            rng.shuffle(level_cards)
            shuffled[level] = level_cards
        decks = [shuffled[3], shuffled[2], shuffled[1]]

        # Deal the pyramid, each row left-to-right from its deck's top.
        pyramid = tuple(
            tuple(decks[deck_index].pop() for _ in range(row_length))
            for row_length, deck_index in PYRAMID_LAYOUT
        )

        # Shuffle the token supply once and deal it along the spiral.
        supply = list(TOKEN_SUPPLY)
        rng.shuffle(supply)
        board: list[Color | None] = [None] * len(SPIRAL)
        for index, color in zip(SPIRAL, supply, strict=True):
            board[index] = color

        # Pick the first player.
        current_player = rng.randrange(2)

        players = (
            _fresh_player(0 if current_player == 0 else 1),
            _fresh_player(0 if current_player == 1 else 1),
        )

        return cls(
            rng=rng,
            players=players,
            board=tuple(board),
            bag=Tokens(),
            decks=tuple(tuple(deck) for deck in decks),
            pyramid=pyramid,
            royals_available=royals,
            privileges_supply=TOTAL_PRIVILEGES - 1,  # second player took one
            current_player=current_player,
            winner=None,
            phase=Phase.USE_PRIVILEGES,
            pending_buy=None,
            pending_reserve=None,
            extra_turn=False,
            pending_ability=None,
            pending_royal=False,
        )

    @classmethod
    def from_seed(cls, seed: int, **fields) -> GameState:
        """Create a state from arbitrary fields with a seeded RNG (for determinizer)."""
        return cls(rng=random.Random(seed), **fields)



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
