"""Cross-engine comparison helpers.

Every function here reads attributes *by name*, so the same fingerprint
function works on the pure-Python dataclasses and on the Rust pyclasses.
Anything that differs between the two engines (a Rust ``Color`` is not a
Python ``Color``) is normalised away here, so a fingerprint mismatch always
means a real behavioural difference.
"""

from __future__ import annotations

TOKENS_FIELDS = ("white", "blue", "green", "red", "black", "pearl", "gold")


def tokens_fingerprint(tokens) -> tuple[int, ...]:
    return tuple(getattr(tokens, field) for field in TOKENS_FIELDS)


def card_fingerprint(card) -> tuple:
    bonus = card.bonus
    ability = card.ability
    return (
        card.id,
        card.level,
        card.points,
        card.crowns,
        bonus.value if bonus is not None else None,
        card.bonus_count,
        ability.value if ability is not None else None,
        card.is_multicolor,
        tokens_fingerprint(card.cost),
    )


def royal_fingerprint(royal) -> tuple:
    ability = royal.ability
    return (
        royal.id,
        royal.points,
        ability.value if ability is not None else None,
    )


def purchased_fingerprint(purchased) -> tuple:
    chosen = purchased.chosen_color
    return (
        card_fingerprint(purchased.card),
        chosen.value if chosen is not None else None,
    )


def reserved_fingerprint(reserved) -> tuple:
    return (card_fingerprint(reserved.card), reserved.from_deck)


def player_fingerprint(player) -> tuple:
    return (
        tokens_fingerprint(player.tokens),
        tokens_fingerprint(player.bonus),
        player.prestige,
        player.crowns,
        tuple(reserved_fingerprint(r) for r in player.reserved),
        tuple(purchased_fingerprint(p) for p in player.purchased),
        player.privileges,
    )


def player_view_fingerprint(view) -> tuple:
    return (
        tokens_fingerprint(view.tokens),
        tokens_fingerprint(view.bonus),
        view.prestige,
        view.crowns,
        tuple(card_fingerprint(c) for c in view.reserved_public),
        view.reserved_deck_count,
        tuple(purchased_fingerprint(p) for p in view.purchased),
        view.privileges,
    )


def state_fingerprint(state) -> tuple:
    """A comparable snapshot of a full game state."""
    return (
        tuple(player_fingerprint(p) for p in state.players),
        tuple(c.value if c is not None else None for c in state.board),
        tokens_fingerprint(state.bag),
        tuple(tuple(card_fingerprint(c) for c in deck) for deck in state.decks),
        tuple(
            tuple(card_fingerprint(c) if c is not None else None for c in row)
            for row in state.pyramid
        ),
        tuple(royal_fingerprint(r) for r in state.royals_available),
        state.privileges_supply,
        state.current_player,
        state.winner,
        state.phase.value,
        action_fingerprint(state.pending_buy)
        if state.pending_buy is not None
        else None,
        (
            action_fingerprint(state.pending_reserve)
            if state.pending_reserve is not None
            else None
        ),
        state.extra_turn,
        state.pending_ability.value if state.pending_ability is not None else None,
        state.pending_royal,
    )


def observation_fingerprint(obs) -> tuple:
    return (
        player_view_fingerprint(obs.you),
        player_view_fingerprint(obs.opponent),
        tuple(c.value if c is not None else None for c in obs.board),
        tuple(
            tuple(card_fingerprint(c) if c is not None else None for c in row)
            for row in obs.pyramid
        ),
        tuple(royal_fingerprint(r) for r in obs.royals_available),
        obs.privileges_supply,
        tuple(obs.deck_counts),
        tokens_fingerprint(obs.bag),
        obs.current_player,
        obs.winner,
        tuple(card_fingerprint(c) for c in obs.your_reserved_deck),
        obs.phase.value,
        action_fingerprint(obs.pending_buy) if obs.pending_buy is not None else None,
        (
            action_fingerprint(obs.pending_reserve)
            if obs.pending_reserve is not None
            else None
        ),
        obs.pending_ability.value if obs.pending_ability is not None else None,
        obs.pending_royal,
        obs.extra_turn,
    )


def action_fingerprint(action) -> tuple:
    """A comparable snapshot of one action."""
    kind = type(action).__name__
    if kind in ("DoneWithPrivileges", "Replenish", "DoneWithReplenish"):
        return (kind,)
    if kind in ("UsePrivilege", "ChooseGold", "ChooseMatchingToken"):
        return (kind, action.index)
    if kind == "TakeTokens":
        return (kind, tuple(action.line))
    if kind == "BuyCard":
        return (kind, card_fingerprint(action.card), action.source)
    if kind == "PayTokens":
        return (kind, tokens_fingerprint(action.payment))
    if kind == "ReserveCard":
        return (kind, action.source, action.index)
    if kind == "ChooseMulticolor":
        return (kind, action.color.value)
    if kind == "ChooseStealToken":
        return (kind, action.color.value)
    if kind == "ChooseRoyal":
        return (kind, action.royal_id)
    if kind == "DiscardTokens":
        return (kind, tokens_fingerprint(action.tokens))
    raise AssertionError(f"unknown action kind: {kind}")
