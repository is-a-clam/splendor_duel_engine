"""Board, state, and deterministic setup tests.

Spec: docs/specs/splendor-duel-rules.md — "Components and setup",
"Hidden information".
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from splendor_duel_engine.engine.board import SPIRAL
from splendor_duel_engine.engine.cards import load_cards
from splendor_duel_engine.engine.colors import GEM_COLORS, Color
from splendor_duel_engine.engine.state import GameState, new_game


def test_setup_matches_spec():
    st = new_game(seed=0)
    assert st.board[12] is not None and all(
        c is not None for c in st.board
    )  # board full (25 tokens)
    assert st.bag.total() == 0  # spec: all 25 tokens on board, bag empty
    assert [len(d) for d in st.decks] == [10, 20, 25]  # 13/24/30 minus pyramid 3/4/5
    assert [sum(1 for c in row if c is not None) for row in st.pyramid] == [3, 4, 5]
    assert len(st.royals_available) == 4
    assert st.privileges_supply == 2  # 3 minus 1 given to second player
    assert st.players[st.current_player].privileges == 0
    assert st.players[1 - st.current_player].privileges == 1


def test_token_census_on_board():
    st = new_game(seed=0)
    census = Counter(st.board)
    assert census[Color.GOLD] == 3 and census[Color.PEARL] == 2
    assert all(census[c] == 4 for c in GEM_COLORS)


def test_setup_is_deterministic_given_seed():
    a, b = new_game(seed=42), new_game(seed=42)
    assert a == b
    assert a.board == b.board and a.decks == b.decks
    assert (
        new_game(seed=43).board != a.board
    )  # different seed shuffles differently (extremely likely)


def test_first_player_is_random_but_reproducible():
    assert new_game(seed=1).current_player == new_game(seed=1).current_player


# --- Rulings pinned for this task (spiral deal, deck top = end, RNG order) ---


def test_spiral_is_the_printed_order():
    assert SPIRAL == (
        12,
        7,
        8,
        13,
        18,
        17,
        16,
        11,
        6,
        1,
        2,
        3,
        4,
        9,
        14,
        19,
        24,
        23,
        22,
        21,
        20,
        15,
        10,
        5,
        0,
    )
    assert SPIRAL[0] == 12  # the centre is dealt first
    assert sorted(SPIRAL) == list(range(25))


def _replay_setup(seed: int):
    """Replicate the pinned RNG consumption to check exact placement.

    RNG order: shuffle decks level 1, 2, 3; deal the pyramid (no RNG); shuffle
    the 25-token supply; pick the first player. Returns the expected board,
    decks, pyramid, per-row top cards, and first player.
    """
    rng = random.Random(seed)
    jewels, _ = load_cards()
    by_level: dict[int, list] = {}
    for level in (1, 2, 3):  # pinned shuffle order
        cards = [c for c in jewels if c.level == level]
        rng.shuffle(cards)
        by_level[level] = cards
    # decks[0/1/2] is level 3/2/1, matching the pyramid rows.
    decks = [by_level[3], by_level[2], by_level[1]]
    # pyramid rows are levels 3, 2, 1; each dealt left-to-right from the deck
    # top, which is the deck's last element.
    pyramid = []
    tops = []
    for row_length, deck_index in ((3, 0), (4, 1), (5, 2)):
        tops.append(decks[deck_index][-1])
        pyramid.append(tuple(decks[deck_index].pop() for _ in range(row_length)))
    supply = (
        [c for c in GEM_COLORS for _ in range(4)] + [Color.PEARL] * 2 + [Color.GOLD] * 3
    )
    assert len(supply) == 25
    rng.shuffle(supply)
    board: list[Color | None] = [None] * 25
    for i, color in enumerate(supply):
        board[SPIRAL[i]] = color
    first = rng.randrange(2)
    return (
        tuple(board),
        tuple(tuple(d) for d in decks),
        tuple(pyramid),
        tuple(tops),
        first,
    )


def test_spiral_deal_and_deck_top_match_pinned_rng_order():
    st = new_game(seed=7)
    board, decks, pyramid, tops, first = _replay_setup(seed=7)
    assert st.board == board
    assert st.decks == decks
    assert st.pyramid == pyramid
    assert st.current_player == first
    # The deck top is the last element, and it becomes the row's first card.
    for row, top in zip(st.pyramid, tops, strict=True):
        assert row[0] is not None and row[0].id == top.id
        assert row[0] is not top  # different instances from replay using fresh load


def test_pyramid_and_decks_partition_each_level():
    st = new_game(seed=3)
    expected = {1: 30, 2: 24, 3: 13}
    for level, deck in zip((3, 2, 1), st.decks, strict=True):
        row = st.pyramid[3 - level]
        ids = [c.id for c in row if c is not None]
        ids += [c.id for c in deck]
        assert len(ids) == expected[level]
        assert len(set(ids)) == len(ids)  # nothing lost or duplicated


def test_pyramid_rows_have_level_matching_cards():
    st = new_game(seed=11)
    for level, deck, row_length in zip((3, 2, 1), st.decks, (3, 4, 5), strict=True):
        row = st.pyramid[3 - level]
        assert len(row) == row_length
        assert all(c is not None and c.level == level for c in row)
        assert all(c.level == level for c in deck)


@pytest.mark.parametrize("seed", [0, 1, 42, 2**63 - 1, 987654321012345678])
def test_extreme_seeds_reproduce(seed: int):
    assert new_game(seed) == new_game(seed)


def test_rng_is_excluded_from_state_equality():
    a, b = new_game(seed=5), new_game(seed=5)
    assert a == b
    assert a.rng is not b.rng  # equality ignores the RNG, identity does not


def test_initial_players_are_empty():
    st = new_game(seed=0)
    for player in st.players:
        assert player.tokens.total() == 0
        assert player.bonus.total() == 0  # bonuses hold gem counts only
        assert player.bonus.pearl == 0 and player.bonus.gold == 0
        assert player.prestige == 0
        assert player.crowns == 0
        assert player.reserved == ()
        assert player.purchased == ()


def test_new_game_returns_game_state_type():
    assert isinstance(new_game(seed=0), GameState)
