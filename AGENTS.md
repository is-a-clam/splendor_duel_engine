# AGENTS.md

Guidance for AI coding agents working on this repo.

## Project

An AI that plays Splendor Duel (two-player). The plan is a deterministic game engine, simple baseline agents, determinized MCTS, and then AlphaZero-style self-play once the search baseline is solid.

## Stack

- Python 3.11+ for the engine, agents, training and evaluation (PyTorch for networks)
- Rust (PyO3 + maturin) for the hot path, added only after the Python engine is correct and profiled
- pytest for tests, ruff for lint and formatting, both via uv (`uv sync`, `uv run pytest`, `uv run ruff check .`)
- No runtime dependencies for the engine; adding one needs a stated reason

## Layout

```
src/splendor_duel_engine/
  engine/     Game rules, state, legal move generation (pure Python reference)
  agents/     random, greedy heuristic, determinized MCTS, neural agents
  training/   Self-play, replay buffer, network training
  eval/       Round-robin matches, Elo tracking, win-type stats
engine_rs/    Rust crate (own Cargo.toml), built by maturin and imported as
              splendor_duel._core (later stage)
docs/
  specs/      Authoritative rules spec (splendor-duel-rules.md); engine tests cite it
  superpowers/plans/  Implementation plans
tests/        Rules tests, fuzz tests, agent sanity tests
pyproject.toml
```

## Commands

```
uv sync                      # install (dev group: pytest, ruff)
uv run pytest                # run tests
uv run ruff check . && uv run ruff format .  # lint and format
python -m splendor_duel.eval.arena A B -n 200   # play agent A vs agent B, both seats
```

## Rules for the engine

- The engine is the source of truth. A rules bug here poisons every agent, so be conservative.
- State must be cheap to copy and fully deterministic given a seed. No global randomness; pass an RNG in.
- A turn is a sequence of small decisions (use privilege, choose gem line, buy or reserve a card), not one giant flat action.
- Always provide a legal-action mask for any decision point.
- Model hidden information explicitly: face-down deck cards, the opponent's face-down reserved cards, and the bag.
- Win conditions: 20 points, 10 crowns, or 10 points in a single color. Test all three.
- When the Rust engine exists, the Python engine stays as the reference. Fuzz both against each other with identical seeds and compare states after every move.

## Conventions

- Type hints on all public functions. Keep modules small and focused.
- Prefer plain dataclasses or NamedTuples for state, with no hidden mutation.
- Never change game rules or card data silently. If something in the rulebook is ambiguous, leave a clear TODO and ask.
- Do not add dependencies without a good reason, and mention it when you do.

## Testing and evaluation

- Every rule gets a test: gem line taking, privileges, forced refills, reserving, royal cards, ability cards, extra turns, all win conditions.
- Agent comparisons must play both seats and use fixed seeds. Report win rate with sample size, not a single number.
- Run `pytest` and `ruff` before calling any task done.

## Working style

- Make small, reviewable changes. Explain what changed and why in a sentence or two.
- If a task touches engine behavior, add or update tests in the same change.
- Profile before optimizing. Only port to Rust what the profiler says is hot.
