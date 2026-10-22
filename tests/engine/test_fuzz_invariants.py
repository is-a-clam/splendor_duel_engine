"""Seeded random-play invariant fuzz tests (Task 10)."""

import copy
import random

import pytest

from splendor_duel_engine.engine.actions import Action, TakeTokens, apply, decide
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, PlayerState, new_game

SEEDS = range(50)


@pytest.mark.parametrize("seed", SEEDS)
def test_invariants_hold_through_random_play(seed):
    st, _ = _play_random_game(seed)
    _assert_invariants(st)


@pytest.mark.parametrize("seed", SEEDS)
def test_random_games_terminate_with_exactly_one_winner(seed):
    st, _ = _play_random_game(seed)
    assert st.winner in (0, 1)
    assert st.phase is Phase.GAME_OVER
    # Recheck the three win conditions independently of ``winner_of``.
    p = st.players[st.winner]
    color_points: dict[Color, int] = {}
    for pc in p.purchased:
        eff = pc.chosen_color if pc.card.is_multicolor else pc.card.bonus
        if eff is not None:
            color_points[eff] = color_points.get(eff, 0) + pc.card.points
    assert (
        p.prestige >= 20
        or p.crowns >= 10
        or any(v >= 10 for v in color_points.values())
    ), f"winner {st.winner} fails all three win conditions"


@pytest.mark.parametrize("seed", SEEDS)
def test_replay_from_clone_reproduces_final_state(seed):
    """Invariant 5: replaying the action sequence reproduces the final state."""
    st, actions = _play_random_game(seed)
    clone = copy.deepcopy(new_game(seed))
    replayed = _replay(clone, actions)
    assert replayed == st


@pytest.mark.parametrize("seed", SEEDS)
def test_apply_does_not_mutate_input_rng(seed):
    """Invariant 5: ``apply`` never advances the caller's RNG."""
    st = new_game(seed)
    for _ in range(60):
        if st.winner is not None:
            break
        dp = decide(st)
        action = dp.legal_actions[0]
        before = copy.deepcopy(st.rng).getstate()
        apply(st, action)
        assert st.rng.getstate() == before, (
            f"apply({type(action).__name__}) mutated the input state's rng"
        )
        st = apply(st, action)


def _count_tokens_on_board(board: tuple[Color | None, ...]) -> int:
    return sum(1 for c in board if c is not None)


def _count_tokens_in_bag(bag: Tokens) -> int:
    return bag.total()


def _count_tokens_in_hands(players: tuple[PlayerState, PlayerState]) -> int:
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


def _action_semantic_key(action: Action) -> object:
    """Return a key under which semantically equivalent actions compare equal.

    ``TakeTokens`` is the one action whose *representation* can vary for the
    same rule-level move: the line ``(A, B)`` and its reverse ``(B, A)`` take
    the same tokens. Key by the token-cell set so a mask that offers both
    directions is caught (this is the predicate that let the duplicated
    take-lines ship).
    """
    if isinstance(action, TakeTokens):
        return ("take", frozenset(action.line))
    return ("raw", action)


def _assert_invariants(state: GameState) -> None:
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
        # 5. the legal-action mask offers each semantic move exactly once
        keys = [_action_semantic_key(a) for a in dp.legal_actions]
        assert len(keys) == len(set(keys)), (
            f"duplicate equivalent legal actions in phase {state.phase}: {dp.legal_actions}"
        )
    else:
        assert state.phase is Phase.GAME_OVER


def _play_random_game(
    seed: int, max_steps: int = 10000
) -> tuple[GameState, tuple[Action, ...]]:
    """Play a full game with random legal moves, asserting invariants each step.

    Returns ``(final_state, actions)`` so callers can replay the same action
    sequence (invariant 5). Raises ``AssertionError`` if the game does not reach
    a winner within ``max_steps`` plies.
    """
    rng = random.Random(seed)
    start = new_game(seed)
    st = start
    actions: list[Action] = []
    step = 0
    while st.winner is None and step < max_steps:
        _assert_invariants(st)
        dp = decide(st)
        # Invariant 4 guarantees a non-empty action list here; if it is ever
        # empty, ``rng.choice`` raising on the empty sequence is the failure.
        action = rng.choice(dp.legal_actions)
        actions.append(action)
        st = apply(st, action)
        step += 1
    if st.winner is None:
        raise AssertionError(
            f"game did not terminate within max_steps={max_steps} (step={step})"
        )
    _assert_invariants(st)
    return st, tuple(actions)


def _replay(start: GameState, actions: tuple[Action, ...]) -> GameState:
    """Apply ``actions`` to ``start`` in order and return the final state."""
    st = start
    for action in actions:
        st = apply(st, action)
    return st
