# Splendor Duel Engine

A deterministic, pure-Python implementation of **Splendor Duel** (the two-player variant of Splendor), with a pluggable agent framework for AI research.

## Overview

This project provides:

- **Game Engine** — Full rules implementation with deterministic state transitions, legal action masks at every decision point, and explicit hidden-information modeling (face-down deck cards, opponent reserved cards, bag contents).
- **Agent Framework** — A minimal `Agent` protocol (`choose_action(observation, legal_actions)`) with three baseline agents:
  - `RandomAgent(seed)` — uniformly samples legal actions (seeded for reproducibility)
  - `GreedyAgent()` — deterministic heuristic rules per decision phase
  - `HumanAgent(input_fn, print_fn)` — terminal-based human player (injectable I/O for tests)
- **Evaluation Harness** — `play_game()` runs full games between any two agents; `play_match()` runs head-to-head batches with alternating seats.
- **CLI Tools** — Arena for agent-vs-agent matches; terminal play vs. an agent.

## Architecture

```
src/splendor_duel_engine/
  engine/      Game rules, state, legal move generation (pure Python reference)
  agents/      Agent protocol, RandomAgent, GreedyAgent
  play/        HumanAgent + terminal CLI
  eval/        Arena (head-to-head matches)
  training/    (future) Self-play, replay buffer, network training
```

## Installation

```bash
# Requires Python 3.11+
uv sync
```

## Quick Start

### Play against the greedy agent (terminal)

```bash
python -m splendor_duel_engine.play.human --opponent greedy --human-seat 0
```

- `--opponent`: `greedy` or `random`
- `--human-seat`: `0` (you go first) or `1` (agent goes first)

At each prompt, enter the **number** of the action you want (0-indexed). The game renders the full board on main decisions and a short prompt on sub-decisions.

### Run agent vs. agent matches (arena)

```bash
# Greedy vs Random, 200 games, alternating seats
python -m splendor_duel_engine.eval.arena greedy random -n 200

# Random vs Random (sanity check)
python -m splendor_duel_engine.eval.arena random random -n 100

# Custom seed base
python -m splendor_duel_engine.eval.arena greedy random -n 50 --seed 42

# MCTS agent examples
python -m splendor_duel_engine.eval.arena mcts greedy -n 100
python -m splendor_duel_engine.eval.arena mcts random -n 100
```

Output shows win counts, win rates, and average turns per game.

### Programmatic usage

```python
from splendor_duel_engine.agents import play_game, GreedyAgent, RandomAgent
from splendor_duel_engine.eval.arena import play_match

# Single game
final_state = play_game(GreedyAgent(), RandomAgent(seed=42), seed=123)
print(f"Winner: Player {final_state.winner}")

# Batch match (alternating seats)
result = play_match(GreedyAgent(), RandomAgent(seed=42), n_games=100, seed_base=0)
print(f"Greedy winrate: {result['agent_a_winrate']:.1%}")
```

## Development Commands

```bash
# Run all tests
uv run python -m pytest -q

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## Game Rules Summary

Splendor Duel is a two-player race to 20 prestige points (or 10 crowns, or 10 points in a single color).

**Turn structure:**

1. **Privileges** — If you have privilege tokens, optionally use them to take a gem from the board.
2. **Replenish** — Optionally refill the board from the bag (costs a privilege to the opponent).
3. **Main action** — Choose one:
   - **Take tokens** — Pick a line of 2–3 tokens from the board (penalties for 3 of a color or 2 pearls).
   - **Buy a card** — Pay its cost from your tokens + bonuses (gold is wild).
   - **Reserve a card** — Take a face-down card from a deck (or face-up from pyramid) into your reserve; gain a gold.
4. **Follow-up decisions** (as triggered):
   - Payment choice (which tokens to spend)
   - Multicolor bonus color
   - Steal token from opponent
   - Choose royal card ability
   - Discard down to 10 tokens

**Win conditions** (checked after every action):

- 20+ prestige points
- 10+ crowns
- 10+ points in a single color (bonus color for multicolor cards)

## Project Conventions

- **No runtime dependencies** — engine and agents use only the standard library.
- **Determinism** — all state transitions are deterministic given a seed; agents must not use global randomness.
- **Hidden-information discipline** — agents receive only `Observation`, never the full `GameState`.
- **Type hints** on all public functions; `ruff` clean required.
- **Tests** — every rule has a test; agent comparisons always play both seats with fixed seeds.

## Next Steps (Roadmap)

1. Determinized MCTS agent
2. AlphaZero-style self-play (PyTorch)
3. Rust hot-path acceleration (PyO3 + maturin)
