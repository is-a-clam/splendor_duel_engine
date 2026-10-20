"""Greedy heuristic baseline agent: deterministic, table-driven phase rules.

Implements the "Greedy heuristics" table of the baseline-agents plan (Task 3).
The agent reads only the :class:`Observation` it is given (hidden-information
discipline: no ``GameState`` access) and only ever returns an action taken
verbatim from ``legal_actions``. It is fully deterministic: no RNG, no global
state, no clock.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.actions import (
    Action,
    BuyCard,
    ChooseMulticolor,
    ChooseRoyal,
    ChooseStealToken,
    DiscardTokens,
    DoneWithPrivileges,
    DoneWithReplenish,
    PayTokens,
    Replenish,
    ReserveCard,
    TakeTokens,
    UsePrivilege,
)
from splendor_duel_engine.engine.cards import Ability
from splendor_duel_engine.engine.colors import GEM_COLORS, Color, Tokens
from splendor_duel_engine.engine.observation import Observation, PlayerView

if TYPE_CHECKING:
    from splendor_duel_engine.engine.cards import Card

#: Weight of prestige points in card/action value scores.
_VALUE_WEIGHT = 2
#: Score bonus per taken token of a needed color.
_TOKEN_WEIGHT = 2
_NEEDED_COLOR_BONUS = 2
#: A card with more than this many prestige points is a "high-value" card.
_HIGH_VALUE_POINTS = 4
#: Cost of taking a penalty line (3 same-color tokens or 2+ pearls).
_PENALTY_COST = 10
#: Replenish only when forced *and* the bag holds more than this many tokens.
_REPLENISH_MIN_BAG = 5
#: Maximum number of cards a player may reserve.
_MAX_RESERVED = 3
#: Abilities that make a visible card worth reserving blindly for.
_GOOD_ABILITIES = frozenset({Ability.EXTRA_TURN, Ability.PRIVILEGE})
#: Royal pick priority: extra turn > privilege > steal token > plain 3pt.
_ROYAL_PRIORITY = {
    Ability.EXTRA_TURN: 3,
    Ability.PRIVILEGE: 2,
    Ability.STEAL_TOKEN: 1,
}


class GreedyAgent:
    """A deterministic greedy agent driven by per-phase heuristics."""

    def __init__(self) -> None:
        pass

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        """Return the heuristic choice among ``legal_actions``.

        The engine only offers actions belonging to one phase at a time, so
        the phase is inferred from the type of the first legal action.
        """
        if not legal_actions:
            raise ValueError("no legal actions offered")

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
        return next(
            (a for a in legal_actions if isinstance(a, DoneWithPrivileges)),
            legal_actions[0],
        )

    def _choose_replenish(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        replenish = next((a for a in legal_actions if isinstance(a, Replenish)), None)
        if replenish is None:
            return legal_actions[0]
        done = next(
            (a for a in legal_actions if isinstance(a, DoneWithReplenish)), None
        )
        if done is None:
            return replenish  # forced: the engine offers no alternative
        # Only replenish when forced AND the bag is worth the opponent's
        # privilege (more than 5 tokens).
        if obs.bag.total() > _REPLENISH_MIN_BAG and self._mandatory_is_blocked(obs):
            return replenish
        return done

    def _choose_mandatory(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        # (1) Buy the best affordable card.
        buy_actions = [a for a in legal_actions if isinstance(a, BuyCard)]
        if buy_actions:
            return self._best_buy_action(buy_actions)

        # (2) Take tokens when it enables a high-value buy next turn.
        take_actions = [a for a in legal_actions if isinstance(a, TakeTokens)]
        enabling = [a for a in take_actions if self._enables_high_value_buy(obs, a)]
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
            pay_actions,
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
        best = max(tied, key=lambda c: self._color_prestige(obs.you, c))
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
            steal_actions,
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
            royal_actions,
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

        return max(discard_actions, key=discard_key)

    # --- Helpers ---

    def _colors_needed_for_best_purchase(self, obs: Observation) -> list[Color]:
        """Colors still needed for the best affordable card, most needed first.

        Reads only public information: the pyramid and the player's own
        reserved cards (public + own deck reservations).
        """
        affordable = [
            card
            for card in self._get_visible_cards(obs)
            if self._can_afford(card, obs.you.tokens, obs.you.bonus)
        ]
        if not affordable:
            return []
        best = max(
            affordable, key=lambda card: card.points * _VALUE_WEIGHT + card.crowns
        )
        # Gold is wild and never a card cost, so it is never "needed" as a
        # color; pearls are never reduced by bonuses.
        nets: list[tuple[int, str, Color]] = []
        for color in (*GEM_COLORS, Color.PEARL):
            net = best.cost.count(color) - obs.you.tokens.count(color)
            if color in GEM_COLORS:
                net -= obs.you.bonus.count(color)
            if net > 0:
                nets.append((-net, color.value, color))
        nets.sort()
        needed: list[Color] = []
        for neg_net, _, color in nets:
            needed.extend([color] * -neg_net)
        return needed

    def _get_visible_cards(self, obs: Observation) -> list[Card]:
        """Cards the current player may buy: pyramid + own reserved cards."""
        cards: list[Card] = [
            card for row in obs.pyramid for card in row if card is not None
        ]
        cards.extend(obs.you.reserved_public)
        cards.extend(obs.your_reserved_deck)
        return cards

    def _get_affordable_cards(self, obs: Observation) -> list[Card]:
        return [
            card
            for card in self._get_visible_cards(obs)
            if self._can_afford(card, obs.you.tokens, obs.you.bonus)
        ]

    @staticmethod
    def _can_afford(card: Card, tokens: Tokens, bonus: Tokens) -> bool:
        """Whether ``tokens`` (+ gold as wild) covers the card's cost.

        Mirrors the engine's affordability rules: per-gem bonuses reduce the
        cost (min 0), pearls are never reduced, gold is wild, and a
        multicolor card requires at least one colored bonus.
        """
        if card.is_multicolor and not any(bonus.count(c) > 0 for c in GEM_COLORS):
            return False
        deficit = sum(
            max(0, card.cost.count(c) - bonus.count(c) - tokens.count(c))
            for c in GEM_COLORS
        )
        deficit += max(0, card.cost.pearl - tokens.pearl)
        return deficit <= tokens.gold

    def _best_buy_action(self, buy_actions: list[BuyCard]) -> BuyCard:
        # Highest points x2 + crowns.
        return max(
            buy_actions, key=lambda a: a.card.points * _VALUE_WEIGHT + a.card.crowns
        )

    def _enables_high_value_buy(self, obs: Observation, action: TakeTokens) -> bool:
        """Would taking this line make a >4-point card affordable?

        Simulates the resulting hand (current tokens + line tokens) against
        every visible card, per the table's one-step lookahead.
        """
        hand = obs.you.tokens
        for index in action.line:
            color = obs.board[index]
            if color is not None:
                hand = hand + Tokens(**{color.value: 1})
        return any(
            card.points > _HIGH_VALUE_POINTS
            and self._can_afford(card, hand, obs.you.bonus)
            for card in self._get_visible_cards(obs)
        )

    def _best_take_action(
        self, obs: Observation, take_actions: list[TakeTokens]
    ) -> TakeTokens:
        needed = set(self._colors_needed_for_best_purchase(obs))

        def score(action: TakeTokens) -> tuple[int, tuple[int, ...]]:
            colors = [obs.board[index] for index in action.line]
            counts = Counter(colors)
            penalty = 0
            if any(n >= 3 for n in counts.values()) or counts.get(Color.PEARL, 0) >= 2:
                penalty = _PENALTY_COST
            needed_bonus = _NEEDED_COLOR_BONUS * sum(1 for c in colors if c in needed)
            total = len(colors) * _TOKEN_WEIGHT + needed_bonus - penalty
            return (total, action.line)

        return max(take_actions, key=score)

    def _should_reserve(self, obs: Observation) -> bool:
        reserved_count = len(obs.you.reserved_public) + obs.you.reserved_deck_count
        if reserved_count >= _MAX_RESERVED:
            return False
        if not any(color == Color.GOLD for color in obs.board):
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

    def _mandatory_is_blocked(self, obs: Observation) -> bool:
        """Whether the MANDATORY phase would offer zero legal actions."""
        has_take = any(c is not None and c != Color.GOLD for c in obs.board)
        reserved_count = len(obs.you.reserved_public) + obs.you.reserved_deck_count
        has_reserve = any(c == Color.GOLD for c in obs.board) and (
            reserved_count < _MAX_RESERVED
        )
        has_buy = bool(self._get_affordable_cards(obs))
        return not (has_take or has_reserve or has_buy)

    def _least_abundant_board_color(self, obs: Observation) -> Color | None:
        counts = Counter(c for c in obs.board if c is not None and c != Color.GOLD)
        if not counts:
            return None
        return min(counts, key=lambda c: (counts[c], c.value))

    @staticmethod
    def _color_prestige(view: PlayerView, color: Color) -> int:
        """Prestige the player has already scored in ``color`` (public info)."""
        points = 0
        for purchased in view.purchased:
            card = purchased.card
            if card.is_multicolor:
                if purchased.chosen_color == color:
                    points += card.points
            elif card.bonus == color:
                points += card.points
        return points
