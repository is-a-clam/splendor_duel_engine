"""Determinization helper for MCTS: samples hidden information from an Observation."""

from __future__ import annotations

import random
from collections import defaultdict

from splendor_duel_engine.engine.cards import Card, load_cards
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.observation import Observation, PlayerView
from splendor_duel_engine.engine.state import GameState, PlayerState, ReservedCard

# Constants from engine: fixed census per rules
GOLD_TOTAL = 3
PEARL_TOTAL = 2
GEM_TOTAL = 4  # 4 each of 5 gem colors

# Total cards per level (from rules)
TOTAL_PER_LEVEL = {1: 30, 2: 24, 3: 13}


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

    # --- Build remaining pools and partition into decks + opponent hidden reserves ---
    pools = _build_remaining_pools(observation)
    decks_dict, opp_reserved = _partition_pools(pools, observation, rng)
    decks = (decks_dict[3], decks_dict[2], decks_dict[1])

    # --- Build player states ---
    current_player = observation.current_player
    # Build player states in the correct order (index 0 = player 0, index 1 = player 1)
    if current_player == 0:
        player0 = _build_player_state(
            observation.you,
            is_current=True,
            reserved_hidden=observation.your_reserved_deck,
        )
        player1 = _build_player_state(
            observation.opponent, is_current=False, reserved_hidden=opp_reserved
        )
    else:
        # current_player == 1: "you" is player 1, "opponent" is player 0
        player1 = _build_player_state(
            observation.you,
            is_current=True,
            reserved_hidden=observation.your_reserved_deck,
        )
        player0 = _build_player_state(
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


def _build_remaining_pools(obs: Observation) -> dict[int, list[Card]]:
    """Returns {level: list[Card]} of all unseen cards (not in pyramid, purchased, face-up reserved, or your hidden reserves)."""
    jewels, _ = load_cards()
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

    # Your hidden deck reserves (known to you, not in decks)
    for card in obs.your_reserved_deck:
        excluded_ids.add(card.id)

    pools: dict[int, list[Card]] = {1: [], 2: [], 3: []}
    for card in jewels:
        if card.id not in excluded_ids:
            pools[card.level].append(card)

    return pools


def _compute_known_per_level(obs: Observation) -> dict[int, int]:
    """Count known cards per level (pyramid, purchased, face-up reserved, your hidden reserves)."""
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
    for card in obs.your_reserved_deck:
        known_per_level[card.level] += 1
    return known_per_level


def _partition_pools(
    pools: dict[int, list[Card]], obs: Observation, rng: random.Random
) -> tuple[dict[int, tuple[Card, ...]], list[ReservedCard]]:
    """
    Partition pools into:
    - decks: exactly obs.deck_counts[level] cards per level (top card last)
    - opponent hidden reserves: hidden_per_level[level] cards per level

    hidden_per_level = total_per_level - known_per_level - deck_counts[level]
    where known_per_level includes pyramid, purchased, face-up reserved, your hidden reserves
    """
    deck_counts = obs.deck_counts  # (level3, level2, level1)
    deck_counts_by_level = {3: deck_counts[0], 2: deck_counts[1], 1: deck_counts[2]}

    # Compute known per level (excluding opponent hidden reserves)
    known_per_level = _compute_known_per_level(obs)

    # Compute hidden reserves per level
    hidden_per_level: dict[int, int] = {}
    for level in (1, 2, 3):
        hidden_per_level[level] = (
            TOTAL_PER_LEVEL[level]
            - known_per_level[level]
            - deck_counts_by_level[level]
        )
        assert hidden_per_level[level] >= 0, f"Negative hidden count for level {level}"

    # Invariant check: pool size must match deck + hidden_per_level (all unseen cards at this level)
    for level in (1, 2, 3):
        expected_pool_size = deck_counts_by_level[level] + hidden_per_level[level]
        assert len(pools[level]) == expected_pool_size, (
            f"Pool size mismatch for level {level}: {len(pools[level])} != {expected_pool_size} "
            f"(total={TOTAL_PER_LEVEL[level]}, known={known_per_level[level]}, deck={deck_counts_by_level[level]}, hidden={hidden_per_level[level]})"
        )

    # Sample decks
    decks: dict[int, tuple[Card, ...]] = {}
    for level in (1, 2, 3):
        count = deck_counts_by_level[level]
        sampled = rng.sample(pools[level], count)
        decks[level] = tuple(sampled)
        # Remove sampled from pools
        for card in sampled:
            pools[level].remove(card)

    # Sample opponent hidden reserves
    opp_reserved: list[ReservedCard] = []
    for level in (1, 2, 3):
        count = hidden_per_level[level]
        sampled = rng.sample(pools[level], count)
        for card in sampled:
            opp_reserved.append(ReservedCard(card=card, from_deck=True))
        for card in sampled:
            pools[level].remove(card)

    # Return decks in GameState order: (level3, level2, level1)
    return ({3: decks[3], 2: decks[2], 1: decks[1]}, opp_reserved)


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
    return counts


def _build_player_state(
    view: PlayerView,
    *,
    is_current: bool,
    reserved_hidden: tuple[Card, ...] | list[ReservedCard] | None = None,
) -> PlayerState:
    # Copy tokens, bonus, prestige, crowns, purchased, reserved_public from view
    # If reserved_hidden provided, append to reserved

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
