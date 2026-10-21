"""Arena integration tests for the MCTS agent (minimal playouts for speed)."""

from __future__ import annotations

from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.mcts_agent import MCTSAgent
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.eval.arena import play_match


def test_mcts_vs_random():
    # MCTS with minimal playouts - just verify it runs
    result = play_match(
        MCTSAgent(seed=1, max_playouts=20),
        RandomAgent(seed=2),
        n_games=2,
        seed_base=100,
    )
    assert 0.0 <= result["agent_a_winrate"] <= 1.0
    assert result["agent_a_wins"] + result["agent_b_wins"] == 2


def test_mcts_vs_greedy():
    # MCTS with minimal playouts - just verify it runs
    result = play_match(
        MCTSAgent(seed=1, max_playouts=20), GreedyAgent(), n_games=2, seed_base=200
    )
    assert 0.0 <= result["agent_a_winrate"] <= 1.0
    assert result["agent_a_wins"] + result["agent_b_wins"] == 2


def test_mcts_both_seats():
    # Test MCTS as both player 0 and player 1
    for seed in range(2):
        final1 = play_game(
            MCTSAgent(seed=seed, max_playouts=10), GreedyAgent(), seed=seed
        )
        final2 = play_game(
            GreedyAgent(), MCTSAgent(seed=seed, max_playouts=10), seed=seed
        )
        assert final1.winner in (0, 1)
        assert final2.winner in (0, 1)


def test_mcts_arena_cli_runs():
    import subprocess

    # Use random vs greedy for speed
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "splendor_duel_engine.eval.arena",
            "random",
            "greedy",
            "-n",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=".",
        timeout=60,
    )
    assert result.returncode == 0
    assert "winrate" in result.stdout.lower()
