"""Tests for observation API with hidden information (Task 9)."""

import dataclasses
from dataclasses import replace

import pytest

from splendor_duel_engine.engine.observation import get_observation
from splendor_duel_engine.engine.state import GameState, ReservedCard


def test_own_deck_reserved_visible_to_self_only():
    base_st = GameState.new_game(0)
    # Make player 0 reserve from a deck top
    # Need gold on board and setup for reserve from deck
    # Find a deck card
    deck_card = base_st.decks[0][
        -1
    ]  # top of level 3 deck? decks stored as level3,level2,level1; top is end
    p0 = replace(
        base_st.players[0], reserved=(ReservedCard(card=deck_card, from_deck=True),)
    )
    st = replace(base_st, current_player=0, players=(p0, base_st.players[1]))
    obs0 = get_observation(st, 0)
    obs1 = get_observation(st, 1)
    # own deck reserved visible to self
    assert deck_card in obs0.your_reserved_deck
    # opponent shouldn't see the card identity in their view of opponent's hidden deck
    # Check opponent.reserved_deck_count is 1 for player 1 looking at player 0
    assert obs1.opponent.reserved_deck_count == 1
    # card id should not appear anywhere in obs1
    obs1_str = str(obs1)
    assert deck_card.id not in obs1_str


def test_pyramid_reserved_is_public():
    base_st = GameState.new_game(0)
    # Get a pyramid card
    pyramid_card = base_st.pyramid[2][0]  # a level 1 card from bottom row
    assert pyramid_card is not None
    p1 = replace(
        base_st.players[1], reserved=(ReservedCard(card=pyramid_card, from_deck=False),)
    )
    st = replace(base_st, current_player=0, players=(base_st.players[0], p1))
    obs0 = get_observation(st, 0)
    # Player 1's pyramid-reserved card should be public in opponent.reserved_public
    assert pyramid_card in obs0.opponent.reserved_public
    assert pyramid_card.id in [c.id for c in obs0.opponent.reserved_public]


def test_deck_reserved_identity_hidden_from_opponent():
    base_st = GameState.new_game(0)
    deck_card = base_st.decks[1][-1]
    p1 = replace(
        base_st.players[1], reserved=(ReservedCard(card=deck_card, from_deck=True),)
    )
    st = replace(base_st, current_player=0, players=(base_st.players[0], p1))
    obs0 = get_observation(st, 0)
    assert obs0.opponent.reserved_deck_count == 1
    assert deck_card.id not in str(obs0)


def test_deck_order_hidden_but_counts_and_bag_visible():
    st = GameState.new_game(0)
    obs = get_observation(st, 0)
    assert obs.deck_counts == tuple(len(d) for d in st.decks)
    assert obs.bag == st.bag


def test_public_info_matches_state():
    st = GameState.new_game(0)
    obs = get_observation(st, 0)
    assert obs.board == st.board
    assert obs.pyramid == st.pyramid
    assert obs.royals_available == st.royals_available
    assert obs.privileges_supply == st.privileges_supply
    assert obs.current_player == st.current_player
    assert obs.winner == st.winner


def test_observation_is_immutable():
    st = GameState.new_game(0)
    obs = get_observation(st, 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.current_player = 5  # type: ignore[misc]  # frozen dataclass: rejected
