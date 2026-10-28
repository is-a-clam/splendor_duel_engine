"""Observation API for hidden information.

Provides a read-only view of the game state from a specific player's
perspective, hiding information not visible to that player (deck-reserved
card identities from opponents, deck order).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from splendor_duel_engine.engine.actions import BuyCard, ReserveCard
    from splendor_duel_engine.engine.cards import Card, RoyalCard
    from splendor_duel_engine.engine.colors import Color, Tokens
    from splendor_duel_engine.engine.phase import Phase
    from splendor_duel_engine.engine.cards import Ability
    from splendor_duel_engine.engine.state import GameState, PurchasedCard


@dataclass(frozen=True, slots=True)
class PlayerView:
    """Everything public about a player."""

    tokens: Tokens
    bonus: Tokens
    prestige: int
    crowns: int
    reserved_public: tuple[Card, ...]  # pyramid-reserved cards (public)
    reserved_deck_count: int  # number of deck-reserved cards (hidden identities)
    purchased: tuple[PurchasedCard, ...]
    privileges: int


@dataclass(frozen=True, slots=True)
class Observation:
    """Observation of the game from the active player's perspective.

    **Invariant:** an observation handed to an agent is always taken from the
    active player's perspective.
    `you` is the player to move (active player).
    `current_player` is that player's seat index.
    """

    you: PlayerView
    opponent: PlayerView
    board: tuple[Color | None, ...]
    pyramid: tuple[tuple[Card | None, ...], ...]
    royals_available: tuple[RoyalCard, ...]
    privileges_supply: int
    deck_counts: tuple[int, int, int]
    bag: Tokens
    current_player: int
    winner: int | None
    your_reserved_deck: tuple[Card, ...]
    phase: Phase
    # Pending action fields for sub-decision phases
    pending_buy: BuyCard | None = None
    pending_reserve: ReserveCard | None = None
    pending_ability: Ability | None = None
    pending_royal: bool = False
    extra_turn: bool = False


def get_observation(state: GameState, player: int) -> Observation:
    """Create an observation of the state from the given player's perspective.

    Production callers pass `state.current_player`; the function accepts any
    seat so that tests can inspect a position from either side.
    """
    if player not in (0, 1):
        raise ValueError("player must be 0 or 1")

    you = state.players[player]
    opp = state.players[1 - player]

    # Build your view
    your_reserved_public = tuple(r.card for r in you.reserved if not r.from_deck)
    your_reserved_deck = tuple(r.card for r in you.reserved if r.from_deck)
    you_view = PlayerView(
        tokens=you.tokens,
        bonus=you.bonus,
        prestige=you.prestige,
        crowns=you.crowns,
        reserved_public=your_reserved_public,
        reserved_deck_count=sum(1 for r in you.reserved if r.from_deck),
        purchased=you.purchased,
        privileges=you.privileges,
    )

    # Build opponent view
    opp_reserved_public = tuple(r.card for r in opp.reserved if not r.from_deck)
    opp_reserved_deck_count = sum(1 for r in opp.reserved if r.from_deck)
    opp_view = PlayerView(
        tokens=opp.tokens,
        bonus=opp.bonus,
        prestige=opp.prestige,
        crowns=opp.crowns,
        reserved_public=opp_reserved_public,
        reserved_deck_count=opp_reserved_deck_count,
        purchased=opp.purchased,
        privileges=opp.privileges,
    )

    return Observation(
        you=you_view,
        opponent=opp_view,
        board=state.board,
        pyramid=state.pyramid,
        royals_available=state.royals_available,
        privileges_supply=state.privileges_supply,
        deck_counts=(len(state.decks[0]), len(state.decks[1]), len(state.decks[2])),
        bag=state.bag,
        current_player=state.current_player,
        winner=state.winner,
        your_reserved_deck=your_reserved_deck,
        phase=state.phase,
        pending_buy=state.pending_buy,
        pending_reserve=state.pending_reserve,
        pending_ability=state.pending_ability,
        pending_royal=state.pending_royal,
        extra_turn=state.extra_turn,
    )
