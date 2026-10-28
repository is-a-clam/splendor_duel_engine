# Splendor Duel Engine

A bot that plays the game _Splendor Duel_ created with Monte-Carlo Tree Search and AlphaGo style self-play. Includes a cli-interface to play with agents and an arena evaluation framework.

## Architecture

```
src/splendor_duel_engine/
  engine/      Game rules, state, legal move generation, rule helpers (helpers.py)
  agents/      Agent protocol, RandomAgent, GreedyAgent, MCTSAgent
  play/        HumanAgent + terminal CLI
  eval/        Arena (head-to-head matches)
  mcts/        MCTS helper functions
  training/    (future) Self-play, replay buffer, network training
  data/        Card data (cards.json)
  engine_rs/   Rust port of python engine (splendor_duel_engine._core)
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
# Show all available Make targets
make help

# Daily development (build + parity tests)
make dev

# Full verification before commit (build + all tests + lint)
make verify

# Build Rust extension in release mode (incremental) and install to venv
make build-dev

# Build Rust extension in debug mode (faster compile) and install to venv
make build-dev-debug

# Run Rust parity tests only (the gate)
make test-rust

# Run full test suite
make test-all

# Lint and format check
make lint

# First-time setup / after Cargo.lock changes (full rebuild)
make install-dev

# Clean all build artifacts
make clean

# Raw commands (if not using Make):
# Run all tests
uv run python -m pytest

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
   - Multicolor bonus color
   - Steal token from opponent
   - Take matching token from board
   - Choose royal card ability
   - Discard down to 10 tokens

**Win conditions** (checked after every action):

- 20+ prestige points
- 10+ crowns
- 10+ points in a single color (bonus color for multicolor cards)
