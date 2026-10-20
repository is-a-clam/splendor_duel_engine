"""Determinization helper for MCTS: samples hidden information from an Observation."""

from __future__ import annotations

import random
from collections import defaultdict

from splendor_duel_engine.engine.cards import Card

Deck = tuple[Card, ...]
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
    player0 = _build_player_state(observation.you, is_current=True, reserved_hidden=observation.your_reserved_deck)
    player1 = _build_player_state(observation.opponent, is_current=False, reserved_hidden=opp_reserved)

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
    Compute exact bag contents: fixed census minus all public tokens.
    This is public knowledge — no sampling.
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

    known = _count_all_public_tokens(obs)

    counts = {}
    for color, total in totals.items():
        count = total - known.get(color, 0)
        assert count >= 0, f"Negative count for {color}: {count}"
        if count > 0:
            counts[color.value] = count

    return Tokens(**counts)


def _count_all_public_tokens(obs: Observation) -> dict[Color, int]:
    """Sum all tokens visible in the observation."""
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
    # Purchased card bonuses (both players)
    for card in obs.you.purchased:
        if card.card.bonus is not None:
            counts[card.card.bonus] += 1
    for card in obs.opponent.purchased:
        if card.card.bonus is not None:
            counts[card.card.bonus] += 1
    # Face-up reserved bonuses (both players)
    for rc in obs.you.reserved_public:
        if rc.bonus is not None:
            counts[rc.bonus] += 1
    for rc in obs.opponent.reserved_public:
        if rc.bonus is not None:
            counts[rc.bonus] += 1
    # NOTE: Opponent face-down reserves have gold bonuses, but these are NOT
    # physical tokens - they're purchasing power bonuses. The bag census only
    # counts physical tokens (3 gold, 2 pearl, 4 each gem).
    return counts


def _sample_decks(obs: Observation, rng: random.Random) -> tuple[Deck, Deck, Deck]:
    # obs.deck_counts gives (level3_count, level2_count, level1_count)
    # For each level, sample that many cards from the appropriate pool without replacement
    # Pool = all cards of that level minus those in pyramid, purchased, reserved (face-up)
    from splendor_duel_engine.engine.cards import load_cards

    jewels, _ = load_cards()

    # Build excluded card IDs from public information
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

    # For each level, filter available cards and sample
    decks_result: list[Deck] = []
    deck_counts = obs.deck_counts  # (level3, level2, level1)

    for level_idx, count in enumerate(deck_counts):
        level = 3 - level_idx  # level3 -> idx0, level2 -> idx1, level1 -> idx2
        pool = [c for c in jewels if c.level == level and c.id not in excluded_ids]
        assert len(pool) >= count, f"Not enough cards in pool for level {level}: need {count}, have {len(pool)}"
        sampled = rng.sample(pool, count)
        # Store with top card last (same as GameState convention)
        decks_result.append(tuple(sampled))

    return tuple(decks_result)  # type: ignore[return-value]


def _sample_opponent_reserved(
    obs: Observation, rng: random.Random, decks: tuple[Deck, Deck, Deck]
) -> list[ReservedCard]:
    # obs.opponent.reserved_deck_count gives total deck-reserved (hidden)
    # obs.opponent.reserved_public gives face-up ones
    # Hidden count = reserved_deck_count
    # Sample hidden cards from decks (same pool as deck sampling) without replacement
    # Each hidden reserve has a gold bonus token (already accounted in _count_all_public_tokens)
    
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

    # Also exclude cards already in decks
    for deck in decks:
        for card in deck:
            excluded_ids.add(card.id)

    # Pool of remaining cards by level
    pool_by_level: dict[int, list[Card]] = {1: [], 2: [], 3: []}
    for card in jewels:
        if card.id not in excluded_ids:
            pool_by_level[card.level].append(card)

    # We need to sample hidden_count cards from the combined pool
    # In the real game, deck-reserved cards come from the top of their respective decks
    # But from an information set perspective, we just need to sample cards consistent
    # with the remaining deck counts per level
    # The deck_counts tell us how many cards of each level remain in decks
    # The hidden reserves must come from those same pools

    # Sample hidden reserves: we need to pick cards such that the remaining
    # deck counts match obs.deck_counts. Since we already sampled decks with
    # those exact counts, the hidden reserves should come from the same level
    # distribution as the remaining undealt cards.
    #
    # However, we don't know which levels the hidden reserves came from.
    # The correct approach: the total cards of each level = pyramid + purchased + reserved_public + deck + hidden_reserves
    # We know pyramid, purchased, reserved_public, and deck counts.
    # So hidden reserves per level = total_per_level - known_per_level - deck_counts

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

    deck_counts = obs.deck_counts  # (level3, level2, level1)
    deck_counts_by_level = {3: deck_counts[0], 2: deck_counts[1], 1: deck_counts[2]}

    hidden_per_level: dict[int, int] = {}
    for level in (1, 2, 3):
        hidden_per_level[level] = (
            total_per_level[level] - known_per_level[level] - deck_counts_by_level[level]
        )
        assert hidden_per_level[level] >= 0, f"Negative hidden count for level {level}"

    # Now sample from each level's pool
    result: list[ReservedCard] = []
    for level in (1, 2, 3):
        count = hidden_per_level[level]
        pool = pool_by_level[level]
        assert len(pool) >= count, f"Not enough cards in level {level} pool for {count} hidden reserves"
        sampled = rng.sample(pool, count)
        for card in sampled:
            result.append(ReservedCard(card=card, from_deck=True))

    return result


def _build_player_state(
    view: Observation.PlayerView,
    *,
    is_current: bool,
    reserved_hidden: list[ReservedCard] | tuple[Card, ...] | None = None,
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