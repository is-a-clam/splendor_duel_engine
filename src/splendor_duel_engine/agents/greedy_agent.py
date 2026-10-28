"""Greedy heuristic baseline agent: deterministic, table-driven phase rules.

Implements the "Greedy heuristics" table of the baseline-agents plan (Task 3).
The agent reads only the :class:`Observation` it is given (hidden-information
discipline: no ``GameState`` access) and only ever returns an action taken
verbatim from ``legal_actions``. It is deterministic by default but can use
a seed for stochastic tie-breaking in playouts.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import TYPE_CHECKING, TypeVar

from splendor_duel_engine.agents.base import first_of
from splendor_duel_engine.engine_api import (
    GEM_COLORS,
    Ability,
    Action,
    BuyCard,
    ChooseMulticolor,
    ChooseRoyal,
    ChooseStealToken,
    Color,
    DiscardTokens,
    DoneWithPrivileges,
    DoneWithReplenish,
    Observation,
    PayTokens,
    Replenish,
    ReserveCard,
    TakeTokens,
    Tokens,
    UsePrivilege,
    helpers,
)

if TYPE_CHECKING:
    from splendor_duel_engine.engine_api import Card

#: Weight of prestige points in card/action value scores.
_VALUE_WEIGHT = 2
#: Score bonus per taken token of a needed color.
_TOKEN_WEIGHT = 2
_NEEDED_COLOR_BONUS = 2
#: A card with more than this many prestige points is a "high-value" card.
_HIGH_VALUE_POINTS = 4
#: Cost of taking a penalty line (3 same-color tokens or 2+ pearls).
_PENALTY_COST = 10
#: Abilities that make a visible card worth reserving blindly for.
_GOOD_ABILITIES = frozenset({Ability.EXTRA_TURN, Ability.PRIVILEGE})
#: Royal pick priority: extra turn > privilege > steal token > plain 3pt.
_ROYAL_PRIORITY = {
    Ability.EXTRA_TURN: 3,
    Ability.PRIVILEGE: 2,
    Ability.STEAL_TOKEN: 1,
    None: 0,
}


class GreedyAgent:
    """A greedy agent driven by per-phase heuristics.

    By default, the agent is fully deterministic (no RNG). When a ``seed`` is
    provided, tie-breaking in action selection becomes stochastic, which is
    useful for MCTS playouts to introduce variance.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed) if seed is not None else None

    T = TypeVar("T", bound=Action)

    def _maybe_shuffle(self, actions: list[T]) -> list[T]:
        """Shuffle actions if RNG is available, for stochastic tie-breaking."""
        if self._rng is not None and len(actions) > 1:
            self._rng.shuffle(actions)
        return actions

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        """Return the heuristic choice among ``legal_actions``.

        The engine only offers actions belonging to one phase at a time, so
        the phase is inferred from the type of the first legal action.
        """
        if not legal_actions:
            raise ValueError("no legal actions offered")
        if len(legal_actions) == 1:
            return legal_actions[0]

        action_type = type(legal_actions[0])

        if action_type is UsePrivilege or action_type is DoneWithPrivileges:
            return self._choose_use_privileges(observation, legal_actions)
        if action_type is Replenish or action_type is DoneWithReplenish:
            return self._choose_replenish(observation, legal_actions)
        if (
            action_type is TakeTokens
            or action_type is BuyCard
            or action_type is ReserveCard
        ):
            return self._choose_mandatory(observation, legal_actions)
        if action_type is PayTokens:
            return self._choose_payment(observation, legal_actions)
        if action_type is ChooseMulticolor:
            return self._choose_multicolor(observation, legal_actions)
        if action_type is ChooseStealToken:
            return self._choose_steal(observation, legal_actions)
        if action_type is ChooseRoyal:
            return self._choose_royal(observation, legal_actions)
        if action_type is DiscardTokens:
            return self._choose_discard(observation, legal_actions)
        # CHOOSE_GOLD / TAKE_MATCHING_TOKEN: all offered actions are
        # interchangeable for the heuristics; the first is deterministic.
        return legal_actions[0]

    # --- Phase-specific methods ---

    def _choose_use_privileges(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        use_actions = [a for a in legal_actions if isinstance(a, UsePrivilege)]
        if not use_actions:
            return legal_actions[0]  # out of privileges

        # Take the color most needed for the highest-value affordable card.
        for color in self._colors_needed_for_best_purchase(obs):
            for action in use_actions:
                if obs.board[action.index] == color:
                    return action

        # Nothing affordable: take the least abundant (contested) non-gold
        # color on the board.
        if not self._get_affordable_cards(obs):
            contested = self._least_abundant_board_color(obs)
            if contested is not None:
                for action in use_actions:
                    if obs.board[action.index] == contested:
                        return action

        # No useful color to take.
        done = first_of(legal_actions, DoneWithPrivileges)
        if done is not None:
            return done
        return legal_actions[0]

    def _choose_replenish(
        self, _obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        """Never replenish voluntarily; take the forced ``Replenish()`` only.

        ``_obs`` is unused: the decision depends solely on the offered actions.
        The parameter stays so every phase handler shares the
        ``(observation, legal_actions)`` dispatch signature.
        """
        done = first_of(legal_actions, DoneWithReplenish)
        if done is not None:
            return done
        return legal_actions[0]

    def _choose_mandatory(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        # (1) Buy the best affordable card.
        buy_actions = [a for a in legal_actions if isinstance(a, BuyCard)]
        if buy_actions:
            return self._best_buy_action(buy_actions)

        # (2) Take tokens when it enables a high-value buy next turn.
        take_actions = [a for a in legal_actions if isinstance(a, TakeTokens)]
        visible = self._visible_cards(obs)
        enabling = [a for a in take_actions if self._enables_high_value_buy(obs, a, visible)]
        if enabling:
            return self._best_take_action(obs, enabling)

        # (3) Reserve for a visible high-value card (gold on board and a free
        # slot are guaranteed by the engine's legal-action mask).
        reserve_actions = [a for a in legal_actions if isinstance(a, ReserveCard)]
        if reserve_actions and self._should_reserve(obs):
            best_reserve = self._best_reserve_action(obs, reserve_actions)
            if best_reserve is not None:
                return best_reserve

        # (4) Take tokens, scored by tokens x2 + needed bonus - penalty.
        if take_actions:
            return self._best_take_action(obs, take_actions)

        return legal_actions[0]

    def _choose_payment(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        pay_actions = [a for a in legal_actions if isinstance(a, PayTokens)]
        if not pay_actions:
            return legal_actions[0]
        # Prefer fewest gold, then fewest total tokens.
        return max(
            self._maybe_shuffle(pay_actions),
            key=lambda a: (-a.payment.gold, -a.payment.total()),
        )

    def _choose_multicolor(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        color_actions = [a for a in legal_actions if isinstance(a, ChooseMulticolor)]
        if not color_actions:
            return legal_actions[0]
        # Most bonus tokens wins; tie-break on prestige already scored in
        # that color (point potential toward the 10-point single-color win).
        offered = [a.color for a in color_actions]
        best_bonus = max(obs.you.bonus.count(c) for c in offered)
        tied = [c for c in offered if obs.you.bonus.count(c) == best_bonus]
        best = max(tied, key=lambda c: helpers.color_points(obs.you.purchased, c))
        for action in color_actions:
            if action.color is best:
                return action
        return legal_actions[0]

    def _choose_steal(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        steal_actions = [a for a in legal_actions if isinstance(a, ChooseStealToken)]
        if not steal_actions:
            return legal_actions[0]
        # Prefer colors we need, then the opponent's most-held color. (The
        # engine only offers non-gold colors the opponent actually holds.)
        needed = set(self._colors_needed_for_best_purchase(obs))
        return max(
            self._maybe_shuffle(steal_actions),
            key=lambda a: (
                a.color in needed,
                obs.opponent.tokens.count(a.color),
            ),
        )

    def _choose_royal(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        royal_actions = [a for a in legal_actions if isinstance(a, ChooseRoyal)]
        if not royal_actions:
            return legal_actions[0]
        # Priority: extra turn > privilege > steal token > plain points.
        by_id = {royal.id: royal for royal in obs.royals_available}
        return max(
            self._maybe_shuffle(royal_actions),
            key=lambda a: _ROYAL_PRIORITY.get(
                by_id[a.royal_id].ability if a.royal_id in by_id else None, 0
            ),
        )

    def _choose_discard(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        discard_actions = [a for a in legal_actions if isinstance(a, DiscardTokens)]
        if not discard_actions:
            return legal_actions[0]
        # Prefer discarding: never gold, never pearls, not needed colors,
        # and come from the colors held in the largest counts.
        needed = set(self._colors_needed_for_best_purchase(obs))
        hand = obs.you.tokens

        def discard_key(action: DiscardTokens) -> tuple[int, int, int, int]:
            discarded = action.tokens
            needed_discarded = sum(discarded.count(c) for c in needed)
            high_count_bonus = sum(
                discarded.count(c) * hand.count(c) for c in GEM_COLORS
            )
            return (
                -discarded.gold,
                -discarded.pearl,
                -needed_discarded,
                high_count_bonus,
            )

        return max(self._maybe_shuffle(discard_actions), key=discard_key)

    # --- Helpers ---

    def _colors_needed_for_best_purchase(self, obs: Observation) -> list[Color]:
        """Colors still needed for the best affordable card, most needed first.

        Reads only public information: the pyramid and the player's own
        reserved cards (public + own deck reservations).
        """
        affordable = self._get_affordable_cards(obs)
        if not affordable:
            return []
        best = max(
            affordable, key=lambda card: card.points * _VALUE_WEIGHT + card.crowns
        )

        deficits = helpers.cost_deficits(best.cost, obs.you.bonus, obs.you.tokens)
        nets = sorted((-count, color) for color in Color if (count := helpers.get_tokens(deficits, color) > 0))
        needed: list[Color] = []
        for neg_count, color in nets:
            needed.extend([color] * -neg_count)
        return needed

    def _visible_cards(self, obs: Observation) -> list[Card]:
        """The cards this player may buy, in the helper's contract order."""
        return helpers.visible_cards(
            obs.pyramid, obs.you.reserved_public, obs.your_reserved_deck
        )

    def _get_affordable_cards(self, obs: Observation) -> list[Card]:
        return [
            card
            for card in self._visible_cards(obs)
            if helpers.can_afford_card(card, obs.you.bonus, obs.you.tokens)
        ]

    def _best_buy_action(self, buy_actions: list[BuyCard]) -> BuyCard:
        # Highest points x2 + crowns.
        return max(
            self._maybe_shuffle(buy_actions),
            key=lambda a: a.card.points * _VALUE_WEIGHT + a.card.crowns,
        )

    def _enables_high_value_buy(self, obs: Observation, action: TakeTokens, visible_cards: list[Card]) -> bool:
        """Would taking this line make a >4-point card affordable?

        Simulates the resulting hand (current tokens + line tokens) against
        every visible card, per the table's one-step lookahead.

        The `visible_cards` parameter is the pre-computed list of visible cards
        to avoid re-computing it for each action in the loop.
        """
        hand = obs.you.tokens
        for index in action.line:
            color = obs.board[index]
            if color is not None:
                hand = helpers.add_tokens(hand, Tokens(**{color: 1}))
        return any(
            card.points > _HIGH_VALUE_POINTS
            and helpers.can_afford_card(card, obs.you.bonus, hand)
            for card in visible_cards
        )

    def _best_take_action(
        self, obs: Observation, take_actions: list[TakeTokens]
    ) -> TakeTokens:
        needed = set(self._colors_needed_for_best_purchase(obs))

        def score(action: TakeTokens) -> tuple[int, tuple[int, ...]]:
            colors = [
                color
                for index in action.line
                if (color := obs.board[index]) is not None
            ]
            penalty = _PENALTY_COST if helpers.is_penalty_triggered(colors) else 0
            needed_bonus = _NEEDED_COLOR_BONUS * sum(1 for c in colors if c in needed)
            total = len(colors) * _TOKEN_WEIGHT + needed_bonus - penalty
            return (total, action.line)

        return max(self._maybe_shuffle(take_actions), key=score)

    def _should_reserve(self, obs: Observation) -> bool:
        reserved_count = len(obs.you.reserved_public) + obs.you.reserved_deck_count
        if not helpers.can_reserve(obs.board, reserved_count):
            return False
        return any(
            self._is_high_value_target(card)
            for row in obs.pyramid
            for card in row
            if card is not None
        )

    @staticmethod
    def _is_high_value_target(card: Card) -> bool:
        return card.points > _HIGH_VALUE_POINTS or card.ability in _GOOD_ABILITIES

    def _best_reserve_action(
        self, obs: Observation, reserve_actions: list[ReserveCard]
    ) -> ReserveCard | None:
        """Best reserve of a *visible* high-value card, or None.

        Deck reservations hide the card's identity, so they never qualify;
        reserving blindly is not in the table.
        """
        best: ReserveCard | None = None
        best_score = -1
        for action in reserve_actions:
            if action.source != "pyramid":
                continue
            row, col = action.index // 10, action.index % 10
            if row >= len(obs.pyramid) or col >= len(obs.pyramid[row]):
                continue
            card = obs.pyramid[row][col]
            if card is None or not self._is_high_value_target(card):
                continue
            score = card.points * _VALUE_WEIGHT + card.crowns
            if score > best_score:
                best, best_score = action, score
        return best

    def _least_abundant_board_color(self, obs: Observation) -> Color | None:
        counts = Counter(c for c in obs.board if c is not None and c != Color.GOLD)
        if not counts:
            return None
        return min(counts, key=lambda c: (counts[c], c))
