"""Terminal human-vs-agent play for Splendor Duel."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from splendor_duel_engine.agents.base import Agent, play_game
from splendor_duel_engine.engine.actions import (
    Action,
    BuyCard,
    ChooseGold,
    ChooseMatchingToken,
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
from splendor_duel_engine.engine.colors import Tokens
from splendor_duel_engine.engine.observation import Observation


def _fmt_tokens(tokens: Tokens) -> str:
    parts = []
    for name in ("white", "blue", "green", "red", "black", "pearl", "gold"):
        count = getattr(tokens, name)
        if count:
            parts.append(f"{name[:1].upper()}{count}" if False else f"{name}={count}")
    return " ".join(parts) if parts else "none"


def _card_summary(card) -> str:
    bonus = (
        "joker" if card.is_multicolor else (card.bonus.value if card.bonus else "none")
    )
    ability = card.ability.value if card.ability else "-"
    return (
        f"{card.points}pt crowns={card.crowns} bonus={bonus} "
        f"cost={_fmt_tokens(card.cost)} ability={ability}"
    )


def _royal_summary(royal) -> str:
    ability = royal.ability.value if royal.ability else "-"
    return f"{royal.id} ({royal.points}pt, {ability})"


def describe(action: Action, obs: Observation) -> str:
    """Human-readable description of an action, using only public info."""
    if isinstance(action, UsePrivilege):
        color = obs.board[action.index]
        color_name = color.value if color is not None else "?"
        return f"Use privilege: take {color_name} from board index {action.index}"
    if isinstance(action, DoneWithPrivileges):
        return "Done using privileges"
    if isinstance(action, Replenish):
        return "Replenish board from bag"
    if isinstance(action, DoneWithReplenish):
        return "Done replenishing"
    if isinstance(action, TakeTokens):
        colors = [obs.board[i] for i in action.line]
        color_names = [c.value if c is not None else "?" for c in colors]
        return f"Take tokens: indices {action.line} -> {', '.join(color_names)}"
    if isinstance(action, BuyCard):
        return f"Buy card: {_card_summary(action.card)} (source={action.source})"
    if isinstance(action, PayTokens):
        return f"Pay tokens: {_fmt_tokens(action.payment)}"
    if isinstance(action, ReserveCard):
        if action.source == "pyramid":
            row, col = divmod(action.index, 10)
            card = None
            if 0 <= row < len(obs.pyramid) and 0 <= col < len(obs.pyramid[row]):
                card = obs.pyramid[row][col]
            if card is not None:
                return f"Reserve pyramid card: {_card_summary(card)}"
        return f"Reserve card from {action.source}"
    if isinstance(action, ChooseGold):
        return f"Take gold token at board index {action.index}"
    if isinstance(action, ChooseMulticolor):
        return f"Choose multicolor bonus color: {action.color.value}"
    if isinstance(action, ChooseStealToken):
        return f"Steal {action.color.value} token from opponent"
    if isinstance(action, ChooseMatchingToken):
        color = obs.board[action.index]
        color_name = color.value if color is not None else "?"
        return f"Take matching {color_name} token at board index {action.index}"
    if isinstance(action, ChooseRoyal):
        for royal in obs.royals_available:
            if royal.id == action.royal_id:
                return f"Choose royal: {_royal_summary(royal)}"
        return f"Choose royal: {action.royal_id}"
    if isinstance(action, DiscardTokens):
        return f"Discard tokens: {_fmt_tokens(action.tokens)}"
    return str(action)


class HumanAgent:
    """A human player driven by terminal IO."""

    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[..., None] = print,
    ) -> None:
        self.input_fn = input_fn
        self.print_fn = print_fn

    def _is_full_turn(self, legal_actions: tuple[Action, ...]) -> bool:
        if not legal_actions:
            return False
        first = type(legal_actions[0])
        return first in (
            UsePrivilege,
            DoneWithPrivileges,
            Replenish,
            DoneWithReplenish,
            TakeTokens,
            BuyCard,
            ReserveCard,
        )

    def _render_full(self, obs: Observation) -> None:
        self.print_fn("=== Splendor Duel ===")
        self.print_fn(
            "You: tokens="
            + _fmt_tokens(obs.you.tokens)
            + " bonus="
            + _fmt_tokens(obs.you.bonus)
            + f" prestige={obs.you.prestige} crowns={obs.you.crowns}"
            + f" privileges={obs.you.privileges}"
            + f" reserved={len(obs.you.reserved_public) + obs.you.reserved_deck_count}"
        )
        self.print_fn(
            "Opponent: tokens="
            + _fmt_tokens(obs.opponent.tokens)
            + " bonus="
            + _fmt_tokens(obs.opponent.bonus)
            + f" prestige={obs.opponent.prestige} crowns={obs.opponent.crowns}"
            + f" privileges={obs.opponent.privileges}"
            + f" reserved_public={len(obs.opponent.reserved_public)}"
            + f" reserved_deck={obs.opponent.reserved_deck_count}"
        )
        self.print_fn("Board (index:color):")
        for r in range(5):
            cells = []
            for c in range(5):
                idx = r * 5 + c
                color = obs.board[idx]
                label = color.value[0].upper() if color is not None else "."
                cells.append(f"{idx:>2}:{label}")
            self.print_fn("  " + " ".join(cells))
        self.print_fn("Pyramid:")
        for row in obs.pyramid:
            self.print_fn(
                "  "
                + " | ".join(_card_summary(c) if c is not None else "-" for c in row)
            )
        royals = ", ".join(_royal_summary(r) for r in obs.royals_available)
        self.print_fn(f"Royals available: {royals if royals else 'none'}")
        self.print_fn(
            f"Deck counts: {obs.deck_counts}  Bag: {obs.bag.total()} tokens  "
            f"Privileges supply: {obs.privileges_supply}  Current player: {obs.current_player}"
        )

    def _render_short(
        self, obs: Observation, legal_actions: tuple[Action, ...]
    ) -> None:
        self.print_fn(
            f"Sub-decision ({len(legal_actions)} option(s)). "
            + "You: tokens="
            + _fmt_tokens(obs.you.tokens)
            + f" prestige={obs.you.prestige} crowns={obs.you.crowns}"
        )

    def choose_action(
        self, observation: Observation, legal_actions: tuple[Action, ...]
    ) -> Action:
        if not legal_actions:
            raise ValueError("no legal actions offered")

        if self._is_full_turn(legal_actions):
            self._render_full(observation)
        else:
            self._render_short(observation, legal_actions)

        for i, action in enumerate(legal_actions):
            self.print_fn(f"{i}) {describe(action, observation)}")

        while True:
            try:
                raw = self.input_fn("")
            except (StopIteration, EOFError):
                self.print_fn("input terminated")
                raise SystemExit("input terminated")
            try:
                choice = int(str(raw).strip())
            except (ValueError, TypeError):
                self.print_fn("invalid choice")
                continue
            if choice < 0 or choice >= len(legal_actions):
                self.print_fn("invalid choice")
                continue
            return legal_actions[choice]


def main() -> None:
    from splendor_duel_engine.eval.arena import AGENT_REGISTRY

    parser = argparse.ArgumentParser(description="Play Splendor Duel against an agent")
    parser.add_argument(
        "--opponent", choices=list(AGENT_REGISTRY.keys()), default="greedy"
    )
    parser.add_argument("--human-seat", type=int, choices=(0, 1), default=0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    opponent_factory = AGENT_REGISTRY[args.opponent]
    opponent = opponent_factory() if callable(opponent_factory) else opponent_factory
    human: Agent = HumanAgent()

    if args.human_seat == 0:
        final = play_game(human, opponent, seed=args.seed)
    else:
        final = play_game(opponent, human, seed=args.seed)

    if final.winner is None:
        print("No winner")
    else:
        name = "Human" if final.winner == args.human_seat else args.opponent
        print(f"Winner: seat {final.winner} ({name})")


if __name__ == "__main__":
    main()
