"""Head-to-head evaluation of Splendor Duel agents."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from splendor_duel_engine.agents.base import Agent, play_game
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.mcts_agent import MCTSAgent
from splendor_duel_engine.agents.random_agent import RandomAgent

AGENT_REGISTRY: dict[str, Callable[[], Agent]] = {
    "random": lambda: RandomAgent(seed=None),
    "greedy": GreedyAgent,
    "mcts": lambda: MCTSAgent(seed=None),
}


def play_match(
    agent_a: Agent, agent_b: Agent, n_games: int, seed_base: int = 0
) -> dict[str, Any]:
    """Play ``n_games`` between ``agent_a`` and ``agent_b``.

    Seats alternate: ``agent_a`` goes first in even-indexed games and
    ``agent_b`` first in odd-indexed games. Game seeds are ``seed_base + i``.
    Returns a plain dict with win counts, win rates and an average game
    length proxy.

    Reproducibility requires fresh agent instances per call: the caller's
    agent instances are reused across all games, so stateful agents (for
    example ``RandomAgent``'s RNG) carry over between games and calls.
    """
    a_wins = 0
    b_wins = 0
    total_turns = 0
    if n_games <= 0:
        return {
            "agent_a_wins": 0,
            "agent_b_wins": 0,
            "agent_a_winrate": 0.0,
            "agent_b_winrate": 0.0,
            "avg_turns": 0.0,
        }
    for i in range(n_games):
        if i % 2 == 0:
            first, second = agent_a, agent_b
            first_is_a = True
        else:
            first, second = agent_b, agent_a
            first_is_a = False

        final = play_game(first, second, seed=seed_base + i)
        total_turns += sum(len(p.purchased) for p in final.players)
        if final.winner == (0 if first_is_a else 1):
            a_wins += 1
        else:
            b_wins += 1

    return {
        "agent_a_wins": a_wins,
        "agent_b_wins": b_wins,
        "agent_a_winrate": a_wins / n_games,
        "agent_b_winrate": b_wins / n_games,
        "avg_turns": total_turns / n_games,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Play agent vs agent matches")
    parser.add_argument(
        "agent_a", choices=list(AGENT_REGISTRY.keys()), help="First agent"
    )
    parser.add_argument(
        "agent_b", choices=list(AGENT_REGISTRY.keys()), help="Second agent"
    )
    parser.add_argument("-n", "--games", type=int, default=100, help="Number of games")
    parser.add_argument("--seed", type=int, default=0, help="Base seed")
    args = parser.parse_args()

    agent_a = AGENT_REGISTRY[args.agent_a]()
    agent_b = AGENT_REGISTRY[args.agent_b]()
    result = play_match(agent_a, agent_b, args.games, args.seed)

    print(f"{args.agent_a} vs {args.agent_b} ({args.games} games, alternating seats)")
    print(
        f"  {args.agent_a}: {result['agent_a_wins']} wins "
        f"(winrate: {result['agent_a_winrate']:.1%})"
    )
    print(
        f"  {args.agent_b}: {result['agent_b_wins']} wins "
        f"(winrate: {result['agent_b_winrate']:.1%})"
    )
    print(f"  Avg turns: {result['avg_turns']:.1f}")


if __name__ == "__main__":
    main()
