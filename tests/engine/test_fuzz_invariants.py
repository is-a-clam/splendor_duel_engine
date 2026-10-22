"""Seeded random-play invariant fuzz tests (Task 10)."""

import copy

import pytest

from splendor_duel_engine.engine.actions import apply, decide
from splendor_duel_engine.engine.colors import Color
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import new_game
from tests.engine.fuzz_helpers import assert_invariants, play_random_game, replay

SEEDS = range(50)


@pytest.mark.parametrize("seed", SEEDS)
def test_invariants_hold_through_random_play(seed):
    st, _ = play_random_game(seed)
    assert_invariants(st)


@pytest.mark.parametrize("seed", SEEDS)
def test_random_games_terminate_with_exactly_one_winner(seed):
    st, _ = play_random_game(seed)
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
    st, actions = play_random_game(seed)
    clone = copy.deepcopy(new_game(seed))
    replayed = replay(clone, actions)
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
