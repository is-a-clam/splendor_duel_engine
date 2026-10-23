"""The agents must run unchanged on top of the Rust engine.

The backend is a process-wide switch, so the Rust backend is driven in a
subprocess rather than by switching the current pytest process.
"""

from __future__ import annotations

import os
import subprocess
import sys

GREEDY_GAME = """
from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.greedy_agent import GreedyAgent

final = play_game(GreedyAgent(), GreedyAgent(), seed=0)
print(final.winner)
"""


def _run(code: str, backend: str) -> str:
    env = dict(os.environ, SPLENDOR_DUEL_ENGINE=backend)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_greedy_agent_plays_a_full_game_on_rust() -> None:
    assert _run(GREEDY_GAME, "rust") in ("0", "1")


def test_both_backends_produce_the_same_game() -> None:
    assert _run(GREEDY_GAME, "rust") == _run(GREEDY_GAME, "python")


def test_mcts_agent_returns_a_legal_action_on_rust() -> None:
    code = """
from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.mcts_agent import MCTSAgent

final = play_game(MCTSAgent(seed=0), MCTSAgent(seed=1), seed=0)
print(final.winner)
"""
    assert _run(code, "rust") in ("0", "1")
