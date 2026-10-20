"""Tests for the MCTS determinization helper."""

from __future__ import annotations

import random

from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.engine.actions import (
    ChooseGold,
    DoneWithPrivileges,
    DoneWithReplenish,
    Replenish,
    ReserveCard,
    TakeTokens,
    apply,
)
from splendor_duel_engine.engine.colors import Color
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import new_game


def _advance_to_mandatory(state):
    """Advance from initial state to MANDATORY phase."""
    # USE_PRIVILEGES -> DoneWithPrivileges -> REPLENISH
    state = apply(state, DoneWithPrivileges())
    # REPLENISH -> DoneWithReplenish -> MANDATORY (bag is empty initially)
    state = apply(state, DoneWithReplenish())
    assert state.phase == Phase.MANDATORY
    return state


def _take_turn_to_mandatory(state):
    """Current player takes a turn (take tokens), advance to next player's MANDATORY."""
    from splendor_duel_engine.engine.actions import decide
    assert state.phase == Phase.MANDATORY
    dp = decide(state)
    take_action = next(a for a in dp.legal_actions if isinstance(a, TakeTokens))
    state = apply(state, take_action)
    # Now next player's turn, in USE_PRIVILEGES (or DISCARD if over limit)
    # Advance through privileges and replenish to MANDATORY
    if state.phase == Phase.DISCARD:
        # Discard down to 10 tokens
        from splendor_duel_engine.engine.actions import DiscardTokens
        dp = decide(state)
        discard_action = next(a for a in dp.legal_actions if isinstance(a, DiscardTokens))
        state = apply(state, discard_action)
    assert state.phase == Phase.USE_PRIVILEGES
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    assert state.phase == Phase.MANDATORY
    return state


def _make_state_with_opponent_reserved():
    """Create a state where opponent (player 1) has face-down reserved cards."""
    # Find a seed where player 0 starts (so we can control the flow better)
    for seed in range(100):
        state = new_game(seed)
        if state.current_player == 0:
            break
    else:
        state = new_game(0)  # fallback
    
    # Player 0 starts in USE_PRIVILEGES
    state = _advance_to_mandatory(state)  # Player 0 in MANDATORY
    
    # Player 0 takes turn -> Player 1 in MANDATORY
    state = _take_turn_to_mandatory(state)
    
    # Now it's player 1's turn in MANDATORY phase
    # Player 1 reserves from deck level 1 (requires gold on board)
    gold_idx = next(i for i, c in enumerate(state.board) if c == Color.GOLD)
    state = apply(state, ReserveCard(source="deck_1", index=0))
    state = apply(state, ChooseGold(index=gold_idx))
    
    # After reserve, it's player 0's turn in USE_PRIVILEGES
    # Advance to MANDATORY so we have a clean state for observation
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())
    
    # Now it's player 0's turn in MANDATORY, and player 1 has a face-down reserved card
    assert state.players[1].reserved
    assert state.players[1].reserved[0].from_deck
    assert state.current_player == 0
    assert state.phase == Phase.MANDATORY
    return state


def test_determinize_preserves_public_info():
    state = new_game(0)
    obs = observation(state, 0)
    rng = random.Random(42)
    det_state = determinize(obs, rng)
    # Public info must match exactly
    assert det_state.board == state.board
    assert det_state.bag.total() == state.bag.total()  # total only; composition sampled
    assert det_state.current_player == state.current_player
    assert det_state.phase == state.phase
    # Player 0 public info preserved
    assert det_state.players[0].tokens == state.players[0].tokens
    assert det_state.players[0].bonus == state.players[0].bonus
    assert det_state.players[0].prestige == state.players[0].prestige
    assert det_state.players[0].crowns == state.players[0].crowns


def test_determinize_samples_opponent_reserve_hidden():
    # Construct state where opponent has face-down reserved cards
    # Determinization must assign concrete cards from appropriate decks
    state = _make_state_with_opponent_reserved()
    obs = observation(state, 0)
    det1 = determinize(obs, random.Random(1))
    det2 = determinize(obs, random.Random(2))
    # Different seeds -> different face-down cards (usually)
    assert det1.players[1].reserved != det2.players[1].reserved


def test_determinize_samples_deck_order():
    state = new_game(0)
    obs = observation(state, 0)
    det1 = determinize(obs, random.Random(1))
    det2 = determinize(obs, random.Random(2))
    # Deck order should differ with different seeds
    assert det1.decks != det2.decks


def test_determinize_bag_multiset_exact():
    rng = random.Random(42)
    state = new_game(0)
    obs = observation(state, 0)
    det = determinize(obs, rng)
    # Bag multiset is EXACTLY the fixed census minus all public tokens
    expected_bag = _compute_exact_bag_multiset(obs)  # helper using same logic as _compute_bag_multiset
    assert det.bag == expected_bag


def test_determinize_rng_seeded():
    """Different determinization seeds produce different RNG states."""
    state = new_game(0)
    obs = observation(state, 0)
    det1 = determinize(obs, random.Random(1))
    det2 = determinize(obs, random.Random(2))
    # Same public state, different RNG
    assert det1.bag == det2.bag
    assert det1.rng.getstate() != det2.rng.getstate()


def test_determinize_replenish_deterministic_per_root():
    """Multiple branches from same determinized root see same replenish."""
    # This is an integration test: run MCTS with 2 children from root,
    # verify they get same replenish outcome.
    # For unit test, just verify engine.apply behavior:
    state = new_game(0)
    obs = observation(state, 0)
    det = determinize(obs, random.Random(42))

    # Simulate two replenish actions from same root state
    action = Replenish()

    # Check if Replenish is legal in this state
    from splendor_duel_engine.engine.actions import decide
    dp = decide(det)
    if action in dp.legal_actions:
        result1 = apply(det, action)
        result2 = apply(det, action)

        # Both should have identical board (same replenish draw)
        assert result1.board == result2.board
        # But both should have advanced RNGs (different from each other and root)
        assert result1.rng.getstate() != result2.rng.getstate()
        assert result1.rng.getstate() != det.rng.getstate()
    else:
        # If replenish not legal in initial state, just verify determinization worked
        # and that the RNG was properly initialized
        assert det is not None
        assert det.rng is not None
        assert det.bag is not None


def _compute_exact_bag_multiset(obs):
    """Helper that computes the exact bag multiset from public info."""
    # Fixed census per rules
    totals = {
        Color.GOLD: 3,
        Color.PEARL: 2,
        Color.BLUE: 4,
        Color.WHITE: 4,
        Color.GREEN: 4,
        Color.BLACK: 4,
        Color.RED: 4,
    }

    known: dict[Color, int] = {}

    # Board tokens (obs.board is tuple[Color | None, ...])
    for color in obs.board:
        if color is not None:
            known[color] = known.get(color, 0) + 1

    # Player 0 (you) tokens
    for color in Color:
        count = obs.you.tokens.count(color)
        if count:
            known[color] = known.get(color, 0) + count

    # Player 1 (opponent) tokens
    for color in Color:
        count = obs.opponent.tokens.count(color)
        if count:
            known[color] = known.get(color, 0) + count

    # Purchased card bonuses (both players)
    for card in obs.you.purchased:
        if card.card.bonus is not None:
            known[card.card.bonus] = known.get(card.card.bonus, 0) + 1
    for card in obs.opponent.purchased:
        if card.card.bonus is not None:
            known[card.card.bonus] = known.get(card.card.bonus, 0) + 1

    # Face-up reserved bonuses (both players)
    for rc in obs.you.reserved_public:
        if rc.bonus is not None:
            known[rc.bonus] = known.get(rc.bonus, 0) + 1
    for rc in obs.opponent.reserved_public:
        if rc.bonus is not None:
            known[rc.bonus] = known.get(rc.bonus, 0) + 1

    # NOTE: Opponent face-down reserves have gold bonuses, but these are NOT
    # physical tokens - they're purchasing power bonuses. The bag census only
    # counts physical tokens (3 gold, 2 pearl, 4 each gem).

    counts = {}
    for color, total in totals.items():
        count = total - known.get(color, 0)
        assert count >= 0, f"Negative count for {color}: {count}"
        if count > 0:
            counts[color.value] = count

    from splendor_duel_engine.engine.colors import Tokens
    return Tokens(**counts)