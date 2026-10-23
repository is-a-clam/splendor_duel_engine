"""Tests for GameState methods (moved from actions.py helpers)."""

from __future__ import annotations
from operator import is_

from splendor_duel_engine.engine.cards import Card
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.state import (
    GameState,
    PlayerState,
)


def _sample_card() -> Card:
    """Create a minimal card for testing."""
    return Card(
        id="test_card",
        level=1,
        cost=Tokens(white=2),
        points=3,
        crowns=1,
        bonus=Color.WHITE,
        bonus_count=1,
        ability=None,
        is_multicolor=False
    )


def _sample_player() -> PlayerState:
    """Create a minimal player state."""
    return PlayerState(
        tokens=Tokens(),
        bonus=Tokens(),
        prestige=0,
        crowns=0,
        reserved=(),
        purchased=(),
        privileges=0,
    )


def _fresh_state() -> GameState:
    """Create a fresh game state for testing."""
    return GameState.new_game(seed=42)


class TestReplacePlayer:
    def test_replaces_player_at_index(self):
        state = _fresh_state()
        new_player = _sample_player()
        new_state = state.replace_player(0, new_player)

        assert new_state.players[0] is new_player
        assert new_state.players[1] is state.players[1]
        # Original unchanged
        assert state.players[0] is not new_player

    def test_replaces_player_at_index_1(self):
        state = _fresh_state()
        new_player = _sample_player()
        new_state = state.replace_player(1, new_player)

        assert new_state.players[1] is new_player
        assert new_state.players[0] is state.players[0]


class TestUpdateBoard:
    def test_updates_single_index(self):
        state = _fresh_state()
        original_color = state.board[0]
        new_state = state.update_board(0, Color.GOLD)

        assert new_state.board[0] == Color.GOLD
        assert new_state.board[1] == state.board[1]
        # Original unchanged
        assert state.board[0] == original_color

    def test_updates_to_none(self):
        state = _fresh_state()
        # Find a non-None index
        idx = next(i for i, c in enumerate(state.board) if c is not None)
        new_state = state.update_board(idx, None)

        assert new_state.board[idx] is None
        assert state.board[idx] is not None


class TestRemoveFromBoard:
    def test_removes_token(self):
        state = _fresh_state()
        idx = next(i for i, c in enumerate(state.board) if c is not None)
        new_state = state.remove_from_board(idx)

        assert new_state.board[idx] is None
        assert state.board[idx] is not None


class TestAddToBag:
    def test_adds_tokens_to_bag(self):
        state = _fresh_state()
        tokens = Tokens(white=2, blue=1)
        new_state = state.add_to_bag(tokens)

        assert new_state.bag.white == state.bag.white + 2
        assert new_state.bag.blue == state.bag.blue + 1
        # Original unchanged
        assert state.bag.white == 0
        assert state.bag.blue == 0


class TestPopDeck:
    def test_pops_top_card(self):
        state = _fresh_state()
        # Deck 0 is level 3, should have cards
        original_deck_len = len(state.decks[0])
        assert original_deck_len > 0

        card, new_state = state.pop_deck(0)

        assert isinstance(card, Card)
        assert len(new_state.decks[0]) == original_deck_len - 1
        # Original unchanged
        assert len(state.decks[0]) == original_deck_len

    def test_pops_from_different_decks(self):
        state = _fresh_state()
        for deck_idx in range(3):
            if state.decks[deck_idx]:
                card, new_state = state.pop_deck(deck_idx)
                assert isinstance(card, Card)
                assert len(new_state.decks[deck_idx]) == len(state.decks[deck_idx]) - 1


class TestTakePyramidCard:
    def test_takes_card_and_refills_from_deck(self):
        state = _fresh_state()
        # Row 0 has 3 cards from deck 0 (level 3)
        card = state.pyramid[0][0]
        assert card is not None

        taken_card, new_state = state.take_pyramid_card(0, 0)

        assert taken_card is card
        # Slot refilled from deck 0
        assert new_state.pyramid[0][0] is not None
        assert new_state.pyramid[0][0] is not card
        # Deck 0 shrunk by 1
        assert len(new_state.decks[0]) == len(state.decks[0]) - 1

    def test_takes_last_card_when_deck_empty(self):
        # Create state where a deck is exhausted
        state = _fresh_state()

        # Empty the deck
        empty_deck: tuple[Card, ...] = ()
        empty_decks = (empty_deck, state.decks[1], state.decks[2])

        state = state.__class__(
            players=state.players,
            board=state.board,
            bag=state.bag,
            decks=empty_decks,
            pyramid=state.pyramid,
            royals_available=state.royals_available,
            privileges_supply=state.privileges_supply,
            current_player=state.current_player,
            winner=state.winner,
            phase=state.phase,
            pending_buy=state.pending_buy,
            pending_reserve=state.pending_reserve,
            rng=state.rng,
            extra_turn=state.extra_turn,
            pending_ability=state.pending_ability,
            pending_royal=state.pending_royal,
        )

        # Take the last card in row 0
        taken_card, new_state = state.take_pyramid_card(0, 0)

        assert taken_card is not None
        # Slot stays None (deck empty)
        assert new_state.pyramid[0][0] is None


class TestGrantPrivilege:
    def _state_with_privileges(
        self, p0_priv: int, p1_priv: int, supply: int
    ) -> GameState:
        """Create a state with specific privilege counts."""
        base = _fresh_state()
        new_players = (
            base.players[0].__class__(
                tokens=base.players[0].tokens,
                bonus=base.players[0].bonus,
                prestige=base.players[0].prestige,
                crowns=base.players[0].crowns,
                reserved=base.players[0].reserved,
                purchased=base.players[0].purchased,
                privileges=p0_priv,
            ),
            base.players[1].__class__(
                tokens=base.players[1].tokens,
                bonus=base.players[1].bonus,
                prestige=base.players[1].prestige,
                crowns=base.players[1].crowns,
                reserved=base.players[1].reserved,
                purchased=base.players[1].purchased,
                privileges=p1_priv,
            ),
        )
        return base.__class__(
            players=new_players,
            board=base.board,
            bag=base.bag,
            decks=base.decks,
            pyramid=base.pyramid,
            royals_available=base.royals_available,
            privileges_supply=supply,
            current_player=base.current_player,
            winner=base.winner,
            phase=base.phase,
            pending_buy=base.pending_buy,
            pending_reserve=base.pending_reserve,
            rng=base.rng,
            extra_turn=base.extra_turn,
            pending_ability=base.pending_ability,
            pending_royal=base.pending_royal,
        )

    def test_grants_from_supply(self):
        state = self._state_with_privileges(p0_priv=0, p1_priv=0, supply=2)
        new_state = state.grant_privilege(0)

        assert new_state.players[0].privileges == 1
        assert new_state.players[1].privileges == 0
        assert new_state.privileges_supply == 1

    def test_steals_from_opponent_when_supply_empty(self):
        # Player 0 has 0, player 1 has 1, supply is 0
        state = self._state_with_privileges(p0_priv=0, p1_priv=1, supply=0)
        new_state = state.grant_privilege(0)

        assert new_state.players[0].privileges == 1
        assert new_state.players[1].privileges == 0
        assert new_state.privileges_supply == 0

    def test_no_privilege_when_supply_empty_and_opponent_has_none(self):
        # Both players have 0, supply is 0
        state = self._state_with_privileges(p0_priv=0, p1_priv=0, supply=0)
        new_state = state.grant_privilege(0)

        assert new_state.players[0].privileges == 0
        assert new_state.players[1].privileges == 0
        assert new_state.privileges_supply == 0
