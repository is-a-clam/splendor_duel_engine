"""Determinization helper for MCTS: samples hidden information from an Observation."""

from __future__ import annotations

import random
from collections import defaultdict

from splendor_duel_engine.engine.cards import Card
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.observation import Observation
from splendor_duel_engine.engine.state import GameState, PlayerState, ReservedCard

# Constants from engine: fixed census per rules
GOLD_TOTAL = 3
PEARL_TOTAL = 2
GEM_TOTAL = 4  # 4 each of 5 gem colors


def determinize(observation: Observation, rng: random.Random) -> GameState:
    """Create a fully-determined GameState consistent with the Observation.

    Samples: deck order, opponent face-down reserved cards, RNG seed.
    Preserves: all public info (board, pyramids, royals, both players' public state).
    Bag composition is public by deduction (fixed census minus all public tokens).
    Replenish and other randomness use the state's RNG — engine.apply deep-copies
    it before mutating, so multiple tree branches from the same root see the same
    replenish outcome.
    """
    # --- Compute exact bag multiset (public deduction) ---
    bag_multiset = _compute_bag_multiset(observation)

    # --- Sample deck order consistent with deck counts ---
    decks = _sample_decks(observation, rng)

    # --- Sample opponent face-down reserved cards ---
    opp_reserved = _sample_opponent_reserved(observation, rng, decks)

    # --- Build player states ---
    player0 = _build_player_state(
        observation.you, is_current=True, reserved_hidden=observation.your_reserved_deck
    )
    player1 = _build_player_state(
        observation.opponent, is_current=False, reserved_hidden=opp_reserved
    )

    # --- Create fresh RNG for this determinization (split from input) ---
    det_rng = random.Random(rng.randint(0, 2**31 - 1))

    # --- Build GameState ---
    return GameState(
        players=(player0, player1),
        board=observation.board,
        bag=bag_multiset,
        decks=decks,
        pyramid=observation.pyramid,
        royals_available=observation.royals_available,
        current_player=observation.current_player,
        phase=observation.phase,
        winner=observation.winner,
        privileges_supply=observation.privileges_supply,
        extra_turn=False,
        pending_buy=None,
        pending_reserve=None,
        pending_ability=None,
        pending_royal=False,
        rng=det_rng,
    )


def _compute_bag_multiset(obs: Observation) -> Tokens:
    """
    Compute exact bag contents: fixed census minus all public physical tokens.
    This is public knowledge — no sampling.

    Physical tokens are ONLY: board + player 0 hand + player 1 hand.
    Card bonuses (purchased, reserved) are purchasing power, not physical tokens.
    """
    totals = {
        Color.GOLD: GOLD_TOTAL,
        Color.PEARL: PEARL_TOTAL,
        Color.BLUE: GEM_TOTAL,
        Color.WHITE: GEM_TOTAL,
        Color.GREEN: GEM_TOTAL,
        Color.BLACK: GEM_TOTAL,
        Color.RED: GEM_TOTAL,
    }

    known = _count_public_physical_tokens(obs)

    counts: dict[str, int] = {}
    for color, total in totals.items():
        count = total - known.get(color, 0)
        assert count >= 0, f"Negative count for {color}: {count}"
        if count > 0:
            counts[color.value] = count

    return Tokens(**counts)


def _count_public_physical_tokens(obs: Observation) -> dict[Color, int]:
    """Sum all physical tokens visible in the observation (board + both players' hands)."""
    counts: dict[Color, int] = defaultdict(int)
    # Board tokens (obs.board is tuple[Color | None, ...])
    for color in obs.board:
        if color is not None:
            counts[color] += 1
    # Player 0 (you) tokens
    for color in Color:
        count = obs.you.tokens.count(color)
        if count:
            counts[color] += count
    # Player 1 (opponent) tokens
    for color in Color:
        count = obs.opponent.tokens.count(color)
        if count:
            counts[color] += count
    # NOTE: Purchased card bonuses and reserved card bonuses are NOT physical tokens.
    # They are permanent purchasing power discounts. The bag census (25 tokens)
    # only tracks physical tokens: board + hands + bag.
    # Opponent face-down reserves have gold bonuses, but these are also NOT
    # physical tokens - they're purchasing power bonuses.
    return counts


def _sample_decks(
    obs: Observation, rng: random.Random
) -> tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]]:
    # obs.deck_counts gives (level3_count, level2_count, level1_count)
    # For each level, sample that many cards from the appropriate pool without replacement
    # Pool = all cards of that level minus those in pyramid, purchased, reserved (face-up), and your hidden reserves
    from splendor_duel_engine.engine.cards import load_cards

    jewels, _ = load_cards()

    # Build excluded card IDs from public information + your known hidden reserves
    excluded_ids: set[str] = set()

    # Pyramid cards (face-up)
    for row in obs.pyramid:
        for card in row:
            if card is not None:
                excluded_ids.add(card.id)

    # Purchased cards (both players)
    for card in obs.you.purchased:
        excluded_ids.add(card.card.id)
    for card in obs.opponent.purchased:
        excluded_ids.add(card.card.id)

    # Face-up reserved cards (both players)
    for rc in obs.you.reserved_public:
        excluded_ids.add(rc.id)
    for rc in obs.opponent.reserved_public:
        excluded_ids.add(rc.id)

    # Your hidden reserved cards (from deck) — known to you, cannot be in decks
    for card in obs.your_reserved_deck:
        excluded_ids.add(card.id)

    # For each level, filter available cards and sample
    decks_result: list[tuple[Card, ...]] = []
    deck_counts = obs.deck_counts  # (level3, level2, level1)

    for level_idx, count in enumerate(deck_counts):
        level = 3 - level_idx  # level3 -> idx0, level2 -> idx1, level1 -> idx2
        pool = [c for c in jewels if c.level == level and c.id not in excluded_ids]
        assert len(pool) >= count, (
            f"Not enough cards in pool for level {level}: need {count}, have {len(pool)}"
        )
        sampled = rng.sample(pool, count)
        # Store with top card last (same as GameState convention)
        decks_result.append(tuple(sampled))

    return tuple(decks_result)  # type: ignore[return-value]


def _sample_opponent_reserved(
    obs: Observation,
    rng: random.Random,
    decks: tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]],
) -> list[ReservedCard]:
    # obs.opponent.reserved_deck_count gives total deck-reserved (hidden)
    # obs.opponent.reserved_public gives face-up ones
    # Hidden count = reserved_deck_count
    # Sample hidden cards from decks (same pool as deck sampling) without replacement
    # Each hidden reserve has a gold bonus token (purchasing power, not physical)

    hidden_count = obs.opponent.reserved_deck_count
    if hidden_count == 0:
        return []

    # Build the same pool as _sample_decks
    from splendor_duel_engine.engine.cards import load_cards

    jewels, _ = load_cards()

    excluded_ids: set[str] = set()
    for row in obs.pyramid:
        for card in row:
            if card is not None:
                excluded_ids.add(card.id)
    for card in obs.you.purchased:
        excluded_ids.add(card.card.id)
    for card in obs.opponent.purchased:
        excluded_ids.add(card.card.id)
    for rc in obs.you.reserved_public:
        excluded_ids.add(rc.id)
    for rc in obs.opponent.reserved_public:
        excluded_ids.add(rc.id)
    # Also exclude your hidden reserves (known to you)
    for card in obs.your_reserved_deck:
        excluded_ids.add(card.id)

    # Also exclude cards already in decks
    for deck in decks:
        for card in deck:
            excluded_ids.add(card.id)

    # Pool of remaining cards by level
    pool_by_level: dict[int, list[Card]] = {1: [], 2: [], 3: []}
    for card in jewels:
        if card.id not in excluded_ids:
            pool_by_level[card.level].append(card)

    # We need to sample hidden_count cards from the combined pool.
    # In the real game, deck-reserved cards come from the top of their respective decks.
    # From an information set perspective, we sample cards consistent with
    # the remaining deck counts per level.
    # hidden_per_level = total_per_level - known_per_level - deck_counts

    total_per_level = {1: 30, 2: 24, 3: 13}

    known_per_level: dict[int, int] = defaultdict(int)
    for row in obs.pyramid:
        for card in row:
            if card is not None:
                known_per_level[card.level] += 1
    for card in obs.you.purchased:
        known_per_level[card.card.level] += 1
    for card in obs.opponent.purchased:
        known_per_level[card.card.level] += 1
    for rc in obs.you.reserved_public:
        known_per_level[rc.level] += 1
    for rc in obs.opponent.reserved_public:
        known_per_level[rc.level] += 1
    # Your hidden reserves are KNOWN to you — they reduce the pool for opponent's hidden reserves
    for card in obs.your_reserved_deck:
        known_per_level[card.level] += 1

    deck_counts = obs.deck_counts  # (level3, level2, level1)
    deck_counts_by_level = {3: deck_counts[0], 2: deck_counts[1], 1: deck_counts[2]}

    hidden_per_level: dict[int, int] = {}
    for level in (1, 2, 3):
        hidden_per_level[level] = (
            total_per_level[level]
            - known_per_level[level]
            - deck_counts_by_level[level]
        )
        assert hidden_per_level[level] >= 0, f"Negative hidden count for level {level}"

    # Now sample from each level's pool
    result: list[ReservedCard] = []
    for level in (1, 2, 3):
        count = hidden_per_level[level]
        pool = pool_by_level[level]
        assert len(pool) >= count, (
            f"Not enough cards in level {level} pool for {count} hidden reserves"
        )
        sampled = rng.sample(pool, count)
        for card in sampled:
            result.append(ReservedCard(card=card, from_deck=True))

    return result


def _build_player_state(
    view: Observation.PlayerView,
    *,
    is_current: bool,
    reserved_hidden: tuple[Card, ...] | list[ReservedCard] | None = None,
) -> PlayerState:
    # Copy tokens, bonus, prestige, crowns, purchased, reserved_public from view
    # If reserved_hidden provided, append to reserved (each gets a gold bonus)

    reserved_list: list[ReservedCard] = []

    # Public reserved cards (from pyramid)
    for card in view.reserved_public:
        reserved_list.append(ReservedCard(card=card, from_deck=False))

    # Hidden reserved cards
    if reserved_hidden:
        for item in reserved_hidden:
            if isinstance(item, ReservedCard):
                reserved_list.append(item)
            else:
                # It's a Card (from observation.your_reserved_deck)
                reserved_list.append(ReservedCard(card=item, from_deck=True))

    return PlayerState(
        tokens=view.tokens,
        bonus=view.bonus,
        prestige=view.prestige,
        crowns=view.crowns,
        reserved=tuple(reserved_list),
        purchased=view.purchased,
        privileges=view.privileges,
    )
