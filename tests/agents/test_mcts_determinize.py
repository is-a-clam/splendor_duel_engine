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
from splendor_duel_engine.engine.observation import Observation, observation
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
        discard_action = next(
            a for a in dp.legal_actions if isinstance(a, DiscardTokens)
        )
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


def _make_state_with_your_reserved_deck():
    """Create a state where current player (player 0) has face-down reserved cards."""
    for seed in range(100):
        state = new_game(seed)
        if state.current_player == 0:
            break
    else:
        state = new_game(0)

    # Player 0 starts in USE_PRIVILEGES
    state = _advance_to_mandatory(state)

    # Player 0 reserves from deck level 1
    gold_idx = next(i for i, c in enumerate(state.board) if c == Color.GOLD)
    state = apply(state, ReserveCard(source="deck_1", index=0))
    state = apply(state, ChooseGold(index=gold_idx))

    # After reserve, still player 0's turn in USE_PRIVILEGES (extra turn from reserve?)
    # Actually reserve doesn't grant extra turn. Let's advance to MANDATORY.
    state = apply(state, DoneWithPrivileges())
    state = apply(state, DoneWithReplenish())

    # Now player 1's turn. Let them take a turn.
    state = _take_turn_to_mandatory(state)

    # Now back to player 0's MANDATORY, with a face-down reserve
    assert state.current_player == 0
    assert state.phase == Phase.MANDATORY
    assert state.players[0].reserved
    assert state.players[0].reserved[0].from_deck
    return state


def _make_midgame_state_with_purchases():
    """Create a mid-game state where players have purchased cards (so bag is non-empty)."""
    from splendor_duel_engine.engine.actions import BuyCard, decide

    state = new_game(0)
    # Advance to mandatory for player 0
    state = _advance_to_mandatory(state)

    # Play several turns, trying to buy cards when possible
    for _ in range(12):
        if state.phase != Phase.MANDATORY:
            # Should not happen with _take_turn_to_mandatory
            break
        dp = decide(state)
        # Try to buy a card if affordable
        buy_actions = [a for a in dp.legal_actions if isinstance(a, BuyCard)]
        if buy_actions:
            state = apply(state, buy_actions[0])
            # After buy, may be in CHOOSE_ROYAL or other phase
            # Advance to next MANDATORY
            while state.phase != Phase.MANDATORY:
                dp = decide(state)
                if state.phase == Phase.CHOOSE_GOLD:
                    gold_idx = next(
                        i for i, c in enumerate(state.board) if c == Color.GOLD
                    )
                    state = apply(state, ChooseGold(index=gold_idx))
                elif state.phase == Phase.CHOOSE_ROYAL:
                    state = apply(state, dp.legal_actions[0])
                elif state.phase == Phase.USE_PRIVILEGES:
                    state = apply(state, DoneWithPrivileges())
                elif state.phase == Phase.REPLENISH:
                    state = apply(state, DoneWithReplenish())
                elif state.phase == Phase.DISCARD:
                    from splendor_duel_engine.engine.actions import DiscardTokens

                    discard_action = next(
                        a for a in dp.legal_actions if isinstance(a, DiscardTokens)
                    )
                    state = apply(state, discard_action)
                else:
                    # Take a default action
                    state = apply(state, dp.legal_actions[0])
        else:
            # Take tokens
            take_actions = [a for a in dp.legal_actions if isinstance(a, TakeTokens)]
            if take_actions:
                state = apply(state, take_actions[0])
                # Advance to next MANDATORY
                while state.phase != Phase.MANDATORY:
                    dp = decide(state)
                    if state.phase == Phase.USE_PRIVILEGES:
                        state = apply(state, DoneWithPrivileges())
                    elif state.phase == Phase.REPLENISH:
                        state = apply(state, DoneWithReplenish())
                    elif state.phase == Phase.DISCARD:
                        from splendor_duel_engine.engine.actions import DiscardTokens

                        discard_action = next(
                            a for a in dp.legal_actions if isinstance(a, DiscardTokens)
                        )
                        state = apply(state, discard_action)
                    else:
                        state = apply(state, dp.legal_actions[0])
            else:
                break

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


def test_determinize_copies_the_observation_bag():
    state = new_game(0)
    obs = observation(state, 0)
    det = determinize(obs, random.Random(42))
    assert det.bag == obs.bag


def test_determinize_your_reserved_deck_excluded_from_decks():
    """Your hidden reserves (your_reserved_deck) must not appear in sampled decks."""
    state = _make_state_with_your_reserved_deck()
    obs = observation(state, 0)
    # Run many determinizations to catch any leakage
    for seed in range(50):
        det = determinize(obs, random.Random(seed))
        # Collect all cards in sampled decks
        deck_cards = {card.id for deck in det.decks for card in deck}
        # Your hidden reserves must not be in decks
        your_hidden_ids = {card.id for card in obs.your_reserved_deck}
        assert not (deck_cards & your_hidden_ids), (
            f"Your hidden reserves leaked into decks: {deck_cards & your_hidden_ids}"
        )


def test_determinize_your_reserved_deck_excluded_from_opponent_reserves():
    """Your hidden reserves must reduce opponent's hidden reserve pool."""
    state = _make_state_with_your_reserved_deck()
    obs = observation(state, 0)
    # Opponent may have 0 hidden reserves, but if they do, your hidden reserves
    # should not be sampled for them
    for seed in range(50):
        det = determinize(obs, random.Random(seed))
        opp_hidden_cards = [r.card for r in det.players[1].reserved if r.from_deck]
        your_hidden_ids = {card.id for card in obs.your_reserved_deck}
        opp_hidden_ids = {card.id for card in opp_hidden_cards}
        assert not (opp_hidden_ids & your_hidden_ids), (
            f"Your hidden reserves sampled as opponent's: {opp_hidden_ids & your_hidden_ids}"
        )


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
    # Need a state where bag is non-empty and phase is REPLENISH
    state = _make_midgame_state_with_purchases()
    # Ensure bag is non-empty
    assert state.bag.total() > 0, "Test setup failed: bag should be non-empty"
    # Manually set phase to REPLENISH for the test (normally happens after USE_PRIVILEGES)
    from dataclasses import replace

    state = replace(state, phase=Phase.REPLENISH)
    obs = observation(state, state.current_player)
    det = determinize(obs, random.Random(42))

    # Replenish should be legal (bag non-empty, phase REPLENISH)
    from splendor_duel_engine.engine.actions import decide

    dp = decide(det)
    action = Replenish()
    assert action in dp.legal_actions, (
        "Replenish should be legal with non-empty bag in REPLENISH phase"
    )

    # Two applications from SAME root state should yield IDENTICAL results
    result1 = apply(det, action)
    result2 = apply(det, action)

    # Both should have identical board (same replenish draw)
    assert result1.board == result2.board, "Replenish draws differ from same root"
    # RNG states should be IDENTICAL (both deep-copy root RNG and advance identically)
    assert result1.rng.getstate() == result2.rng.getstate(), (
        "RNG states should be equal"
    )
    # Both should differ from root RNG
    assert result1.rng.getstate() != det.rng.getstate()


def test_determinize_invariant_check():
    """Verify the card count invariant: total = known + deck + hidden_reserves + pool_remaining.

    This test runs determinization on multiple random game states and verifies that
    the invariant holds at the point of partitioning pools.
    """
    import random as pyrandom

    # Test on initial state
    state = new_game(0)
    obs = observation(state, 0)
    for seed in range(20):
        det = determinize(obs, random.Random(seed))
        _verify_card_invariant(obs, det)

    # Test on state with opponent reserved
    state = _make_state_with_opponent_reserved()
    obs = observation(state, 0)
    for seed in range(20):
        det = determinize(obs, random.Random(seed))
        _verify_card_invariant(obs, det)

    # Test on state with your reserved deck
    state = _make_state_with_your_reserved_deck()
    obs = observation(state, 0)
    for seed in range(20):
        det = determinize(obs, random.Random(seed))
        _verify_card_invariant(obs, det)

    # Test on mid-game state with purchases
    state = _make_midgame_state_with_purchases()
    obs = observation(state, 0)
    for seed in range(20):
        det = determinize(obs, random.Random(seed))
        _verify_card_invariant(obs, det)

    # Test with random seeds for initial game
    for game_seed in range(10):
        state = new_game(game_seed)
        # Advance a few random turns
        for _ in range(pyrandom.randint(0, 5)):
            if state.phase == Phase.MANDATORY:
                from splendor_duel_engine.engine.actions import TakeTokens, decide

                dp = decide(state)
                take_actions = [
                    a for a in dp.legal_actions if isinstance(a, TakeTokens)
                ]
                if take_actions:
                    state = apply(state, take_actions[0])
                    while state.phase != Phase.MANDATORY:
                        dp = decide(state)
                        if state.phase == Phase.USE_PRIVILEGES:
                            state = apply(state, DoneWithPrivileges())
                        elif state.phase == Phase.REPLENISH:
                            state = apply(state, DoneWithReplenish())
                        elif state.phase == Phase.DISCARD:
                            from splendor_duel_engine.engine.actions import (
                                DiscardTokens,
                            )

                            discard_action = next(
                                a
                                for a in dp.legal_actions
                                if isinstance(a, DiscardTokens)
                            )
                            state = apply(state, discard_action)
                        else:
                            state = apply(state, dp.legal_actions[0])
                else:
                    break
            else:
                break
        obs = observation(state, state.current_player)
        for seed in range(10):
            det = determinize(obs, random.Random(seed))
            _verify_card_invariant(obs, det)


def _verify_card_invariant(obs: Observation, det_state) -> None:
    """Verify the card count invariants:
    1. known + deck + opp_hidden == total (all cards accounted for)
    2. pre_sampling_pool_size == deck + opp_hidden (pool contains exactly deck + hidden cards)
    """
    from splendor_duel_engine.agents.mcts_determinize import (
        TOTAL_PER_LEVEL,
        _build_remaining_pools,
        _compute_known_per_level,
    )

    pools = _build_remaining_pools(obs)
    known_per_level = _compute_known_per_level(obs)

    deck_counts = obs.deck_counts  # (level3, level2, level1)
    deck_counts_by_level = {3: deck_counts[0], 2: deck_counts[1], 1: deck_counts[2]}

    # Count opponent hidden reserves per level in the determinized state
    # det_state.players[0] = engine player 0, det_state.players[1] = engine player 1
    # obs.current_player tells us which engine player is "you"
    if obs.current_player == 0:
        # You are engine player 0, opponent is engine player 1
        opp_player = det_state.players[1]
    else:
        # You are engine player 1, opponent is engine player 0
        opp_player = det_state.players[0]

    opp_hidden_per_level: dict[int, int] = {1: 0, 2: 0, 3: 0}
    for rc in opp_player.reserved:
        if rc.from_deck:
            opp_hidden_per_level[rc.card.level] += 1

    # Verify invariant for each level
    for level in (1, 2, 3):
        total = TOTAL_PER_LEVEL[level]
        known = known_per_level[level]
        deck = deck_counts_by_level[level]
        opp_hidden = opp_hidden_per_level[level]
        pre_sampling_pool_size = len(pools[level])

        # Invariant 1: All cards accounted for
        assert known + deck + opp_hidden == total, (
            f"Card count invariant violated for level {level}: "
            f"known={known} + deck={deck} + opp_hidden={opp_hidden} "
            f"= {known + deck + opp_hidden} != total={total}"
        )

        # Invariant 2: Pre-sampling pool contains exactly deck + hidden cards
        assert pre_sampling_pool_size == deck + opp_hidden, (
            f"Pool size invariant violated for level {level}: "
            f"pool={pre_sampling_pool_size} != deck+opp_hidden={deck + opp_hidden}"
        )
