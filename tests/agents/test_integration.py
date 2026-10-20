"""Integration tests: full game simulations and win-condition verification.

These tests exercise the agent stack end to end through :func:`play_game`.
Every game uses a fixed engine seed and deterministic agents, so failures are
reproducible. The three win conditions are defined in
``actions.winner_of``: 20 prestige, 10 crowns, or 10 prestige in one gem
colour.
"""

from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.engine.colors import GEM_COLORS
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import PlayerState


def _color_points(player: PlayerState, color: object) -> int:
    """Prestige the player scores from purchased cards of one gem colour.

    Mirrors the engine's colour-win rule: ordinary cards count toward their
    bonus colour; a multicolor card counts toward the colour chosen when it
    was bought.
    """
    points = 0
    for purchased in player.purchased:
        card = purchased.card
        if card.is_multicolor:
            if purchased.chosen_color == color:
                points += card.points
        elif card.bonus == color:
            points += card.points
    return points


def _win_conditions(player: PlayerState) -> set[str]:
    """All documented win conditions ``player`` satisfies."""
    conditions: set[str] = set()
    if player.prestige >= 20:
        conditions.add("prestige")
    if player.crowns >= 10:
        conditions.add("crowns")
    if any(_color_points(player, color) >= 10 for color in GEM_COLORS):
        conditions.add("color")
    return conditions


def test_random_vs_greedy_both_seats() -> None:
    # Both seat assignments: greedy must not depend on moving first.
    for seed in range(5):
        final1 = play_game(GreedyAgent(), RandomAgent(seed=seed), seed=seed)
        assert final1.winner in (0, 1)
        assert final1.phase is Phase.GAME_OVER

        final2 = play_game(RandomAgent(seed=seed), GreedyAgent(), seed=seed)
        assert final2.winner in (0, 1)
        assert final2.phase is Phase.GAME_OVER


def test_all_three_win_conditions_reachable() -> None:
    # Fixed seeds make this deterministic despite the name "random": all
    # three end-of-game conditions are observed across these 100 games.
    win_types: set[str] = set()
    for seed in range(100):
        final = play_game(
            RandomAgent(seed=seed), RandomAgent(seed=seed + 1000), seed=seed
        )
        assert final.winner in (0, 1)
        assert final.phase is Phase.GAME_OVER
        winner = final.players[final.winner]
        conditions = _win_conditions(winner)
        # Every completed game must end through a documented win condition.
        assert conditions, f"seed {seed}: winner satisfies no win condition"
        win_types |= conditions
    assert win_types == {"prestige", "crowns", "color"}


def test_agents_never_choose_illegal_action() -> None:
    # The engine's apply() raises on an illegal action, so playing each game
    # to completion is the legality check: no uncaught exception means every
    # action was legal.
    for seed in range(20):
        final = play_game(GreedyAgent(), RandomAgent(seed=seed), seed=seed)
        assert final.winner in (0, 1)
        assert final.phase is Phase.GAME_OVER
