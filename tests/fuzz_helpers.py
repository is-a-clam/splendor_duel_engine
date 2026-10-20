"""Fuzz harness helpers for invariant checking."""

from __future__ import annotations

import random

from splendor_duel_engine.engine.actions import apply, decide
from splendor_duel_engine.engine.colors import Color
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, new_game


def _count_tokens_on_board(board) -> int:
    return sum(1 for c in board if c is not None)


def _count_tokens_in_bag(bag) -> int:
    return bag.total()


def _count_tokens_in_hands(players) -> int:
    total = 0
    for p in players:
        total += p.tokens.total()
    return total


def _total_tokens(state: GameState) -> int:
    return (
        _count_tokens_on_board(state.board)
        + _count_tokens_in_bag(state.bag)
        + _count_tokens_in_hands(state.players)
    )


def _gold_total(state: GameState) -> int:
    total = sum(1 for c in state.board if c == Color.GOLD)
    total += state.bag.gold
    total += sum(p.tokens.gold for p in state.players)
    return total


def _all_card_ids(state: GameState) -> list[str]:
    ids: list[str] = []
    for d in state.decks:
        for c in d:
            ids.append(c.id)
    for row in state.pyramid:
        for c in row:
            if c is not None:
                ids.append(c.id)
    for p in state.players:
        for r in p.reserved:
            ids.append(r.card.id)
        for pc in p.purchased:
            ids.append(pc.card.id)
    return ids


def assert_invariants(state: GameState) -> None:
    """Assert invariants hold for the given state."""
    # 1. token conservation
    assert _total_tokens(state) == 25
    assert _gold_total(state) == 3  # 3 gold total

    # 2. card conservation
    all_ids = _all_card_ids(state)
    assert len(all_ids) == 67  # 67 jewels total
    assert len(set(all_ids)) == 67  # all unique

    # 3. privilege counts
    total_priv = (
        state.privileges_supply
        + state.players[0].privileges
        + state.players[1].privileges
    )
    assert 0 <= total_priv <= 3

    # 4. decide returns >= 1 legal action unless winner is not None
    if state.winner is None:
        dp = decide(state)
        assert len(dp.legal_actions) > 0, f"deadlock in phase {state.phase}"
    else:
        assert state.phase is Phase.GAME_OVER


def play_random_game(seed: int, max_steps: int = 10000) -> GameState:
    """Play a full game with random legal moves, asserting invariants at each step."""
    rng = random.Random(seed)
    st = new_game(seed)
    step = 0
    while st.winner is None and step < max_steps:
        assert_invariants(st)
        dp = decide(st)
        if len(dp.legal_actions) == 0:
            break  # should not happen if invariants hold
        action = rng.choice(dp.legal_actions)
        # Replay with clone to ensure apply doesn't consult rng? - check by copying state
        st = apply(st, action)
        step += 1
    assert_invariants(st)
    return st
