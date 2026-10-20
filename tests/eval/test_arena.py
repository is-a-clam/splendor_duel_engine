from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.eval.arena import play_match


def test_random_vs_random_symmetric():
    result = play_match(
        RandomAgent(seed=1), RandomAgent(seed=2), n_games=20, seed_base=100
    )
    # With 20 games, win rates should be roughly 50/50 (allowing variance)
    assert result["agent_a_wins"] + result["agent_b_wins"] == 20
    assert 0.3 < result["agent_a_winrate"] < 0.7


def test_greedy_beats_random():
    result = play_match(GreedyAgent(), RandomAgent(seed=42), n_games=50, seed_base=200)
    # Greedy should win noticeably more than random
    assert result["agent_a_winrate"] > 0.55  # agent_a is GreedyAgent


def test_arena_cli_runs():
    # Integration test via subprocess
    import subprocess

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "splendor_duel_engine.eval.arena",
            "greedy",
            "random",
            "-n",
            "10",
        ],
        capture_output=True,
        text=True,
        cwd=".",
        check=False,
    )
    assert result.returncode == 0
    assert "winrate" in result.stdout.lower()
