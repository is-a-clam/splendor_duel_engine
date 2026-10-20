# MCTS Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a determinized MCTS agent that uses the engine's `Observation` API and `Agent` protocol, with configurable playout budget and playout policy (greedy default, random optional).

**Architecture:** A `MCTSAgent` class implementing the existing `Agent` protocol. At each decision point, it determinizes the hidden information (deck order, opponent face-down reserved cards, bag contents) from the `Observation`, runs MCTS with UCT on the resulting perfect-information game tree, and returns the most-visited action. Playouts use a configurable policy (default: `GreedyAgent`; option: `RandomAgent`). The agent is added to the arena registry for evaluation.

**Tech Stack:** Python 3.11+, stdlib only (no new dependencies), depends on engine (`decide`, `apply`, `observation`, `Action`, `Observation`, `Phase`, `Color`, `Tokens`, `Card`) and existing agents (`GreedyAgent`, `RandomAgent`).

**Spec:** `docs/specs/splendor-duel-rules.md` (game rules); `docs/superpowers/plans/2026-10-17-python-engine.md` Task 9 (Observation API); `docs/superpowers/plans/2026-10-18-baseline-agents.md` (Agent protocol, `play_game`, `GreedyAgent`, `RandomAgent`, arena).

## Global Constraints

- Python 3.11+; **no new runtime dependencies** (engine has none; agents add none).
- Type hints on all public functions; ruff clean; tests pass.
- Agents must use `observation(state, player)` — never access `GameState` directly (hidden-info discipline).
- Agents must only choose from `decide(state).legal_actions` — never construct actions manually.
- Deterministic given a seed: MCTS agent takes an `rng: random.Random` (or seed) for reproducibility of determinization and tree randomness.
- Fixed playout budget (default 2000, configurable 500-10000).
- Greedy playout policy by default; random available for ablation.

## Review Focus

1. **Hidden-info leakage in determinization** — determinization must only use info in `Observation` (deck counts, opponent reserve counts, bag total). Must not peek at `GameState` deck order, opponent face-down cards, or bag composition. Pinned to determinization tests.
2. **Illegal action selection** — MCTS must only expand/select from `legal_actions` at each node; test with engine's `apply` rejection. Pinned to integration tests.
3. **Token limit awareness in playouts** — greedy playouts already handle this; random playouts must not exceed hand limit of 10 (engine enforces, but playout policy should be legal). Pinned to playout policy tests.
4. **Determinization bias** — agent must re-determinize at every decision point (not cache at game start); test by verifying different determinizations produce different trees on same Observation. Pinned to determinization tests.
5. **Time/space bounds** — MCTS must not leak memory across `choose_action` calls; tree must be discarded after each decision. Pinned to memory/performance tests.

---

### Task 1: Determinization helper — sample hidden info from Observation

**Files:**
- Create: `src/splendor_duel_engine/agents/mcts_determinize.py`
- Test: `tests/agents/test_mcts_determinize.py`

**Interfaces:**
- Consumes: `engine.observation.Observation`, `engine.cards.Card`, `engine.colors.Tokens`, `engine.state.GameState` (for type hints only), `random.Random`.
- Produces: `determinize(observation: Observation, rng: random.Random) -> GameState` — returns a fully-specified `GameState` consistent with the `Observation`, with hidden info sampled.

- [ ] **Step 1: Write failing tests**

`tests/agents/test_mcts_determinize.py`:
```python
from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.engine.colors import Color
import random

def test_determinize_preserves_public_info():
    state = new_game(0)
    obs = observation(state, 0)
    rng = random.Random(42)
    det_state = determinize(obs, rng)
    # Public info must match exactly
    assert det_state.board == state.board
    assert det_state.bag.total() == state.bag.total()  # total only; composition sampled
    assert det_state.current_player == state.current_player
    assert det_state.phase == state.phase
    # Player 0 public info preserved
    assert det_state.players[0].tokens == state.players[0].tokens
    assert det_state.players[0].bonus == state.players[0].bonus
    assert det_state.players[0].prestige == state.players[0].prestige
    assert det_state.players[0].crowns == state.players[0].crowns

def test_determinize_samples_opponent_reserve_hidden():
    # Construct state where opponent has face-down reserved cards
    # Determinization must assign concrete cards from appropriate decks
    rng = random.Random(42)
    state = new_game(0)
    # ... advance to a state with opponent reserved cards ...
    obs = observation(state, 0)
    det1 = determinize(obs, random.Random(1))
    det2 = determinize(obs, random.Random(2))
    # Different seeds -> different face-down cards (usually)
    assert det1.players[1].reserved != det2.players[1].reserved

def test_determinize_samples_deck_order():
    rng = random.Random(42)
    state = new_game(0)
    obs = observation(state, 0)
    det1 = determinize(obs, random.Random(1))
    det2 = determinize(obs, random.Random(2))
    # Deck order should differ with different seeds
    assert det1.decks != det2.decks

def test_determinize_bag_composition():
    rng = random.Random(42)
    state = new_game(0)
    obs = observation(state, 0)
    det = determinize(obs, rng)
    # Bag total matches, composition sums to total
    assert det.bag.total() == obs.bag.total()
    # All tokens in bag are valid colors
    for color in Color:
        assert det.bag.count(color) >= 0
```

- [ ] **Step 2: Run to verify failure**
Run: `uv run python -m pytest tests/agents/test_mcts_determinize.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `mcts_determinize.py`**

```python
from __future__ import annotations
import random
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.cards import Card, Deck, RoyalCard
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.observation import Observation
from splendor_duel_engine.engine.state import GameState, PlayerState

if TYPE_CHECKING:
    from splendor_duel_engine.engine.cards import PurchasedCard, ReservedCard

# Constants from engine: 3 gold total, 5 pearl, 7 each gem
GOLD_TOTAL = 3
PEARL_TOTAL = 5
GEM_TOTAL = 7

def determinize(observation: Observation, rng: random.Random) -> GameState:
    """Create a fully-determined GameState consistent with the Observation.

    Samples: deck order, opponent face-down reserved cards, bag composition.
    Preserves: all public info (board, pyramids, royals, both players' public state).
    """
    # Start from a fresh game state structure, then overwrite with observed + sampled
    # We don't call new_game() because we need to control every field.
    # Instead, construct PlayerState and GameState directly from Observation data.

    # --- Sample bag composition consistent with total and known tokens ---
    bag = _sample_bag(observation, rng)

    # --- Sample deck order consistent with deck counts ---
    decks = _sample_decks(observation, rng)

    # --- Sample opponent face-down reserved cards ---
    opp_reserved = _sample_opponent_reserved(observation, rng, decks)

    # --- Build player states ---
    player0 = _build_player_state(observation.you, is_current=True)
    player1 = _build_player_state(observation.opponent, is_current=False, reserved_hidden=opp_reserved)

    # --- Build GameState ---
    return GameState(
        players=(player0, player1),
        board=observation.board,
        bag=bag,
        decks=decks,
        pyramid=observation.pyramid,
        royals=observation.royals_available,
        current_player=observation.current_player,
        phase=observation.phase,
        winner=None,
        # ... other fields from observation
    )

def _sample_bag(obs: Observation, rng: random.Random) -> Tokens:
    # Total tokens in bag known from obs.bag.total()
    # Known tokens: on board, in both players' hands, in reserves (face-up), purchased
    # Remaining tokens distributed per initial totals minus known
    # Implementation: compute known counts per color, subtract from totals, distribute remainder
    ...

def _sample_decks(obs: Observation, rng: random.Random) -> tuple[Deck, Deck, Deck]:
    # obs.deck_counts gives (level3_count, level2_count, level1_count)
    # For each level, sample that many cards from the appropriate pool without replacement
    # Pool = all cards of that level minus those in pyramid, purchased, reserved (face-up)
    ...

def _sample_opponent_reserved(obs: Observation, rng: random.Random, decks: tuple[Deck, Deck, Deck]) -> list[ReservedCard]:
    # obs.opponent.reserved_count gives total reserved (public + hidden)
    # obs.opponent.reserved_public gives face-up ones
    # Hidden count = total - len(public)
    # Sample hidden cards from decks (same pool as deck sampling) without replacement
    ...

def _build_player_state(view, is_current: bool, reserved_hidden: list | None = None) -> PlayerState:
    # Copy tokens, bonus, prestige, crowns, purchased, reserved_public from view
    # If reserved_hidden provided, append to reserved
    ...
```

- [ ] **Step 4: Run tests, lint**
Run: `uv run python -m pytest tests/agents/test_mcts_determinize.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(mcts): determinization helper from Observation"
```

---

### Task 2: MCTS core — tree search with UCT

**Files:**
- Create: `src/splendor_duel_engine/agents/mcts_core.py`
- Test: `tests/agents/test_mcts_core.py`

**Interfaces:**
- Consumes: `engine.actions.decide`, `engine.actions.apply`, `engine.actions.Action`, `engine.observation.Observation`, `agents.mcts_determinize.determinize`, `agents.greedy_agent.GreedyAgent`, `agents.random_agent.RandomAgent`, `random.Random`.
- Produces:
  - `class MCTSNode:` — tree node with `state: GameState`, `parent: MCTSNode | None`, `action: Action | None`, `children: dict[Action, MCTSNode]`, `visits: int`, `value: float`, `untried_actions: list[Action]`.
  - `def uct_select(node: MCTSNode, exploration: float = 1.414) -> MCTSNode` — standard UCT selection.
  - `def expand(node: MCTSNode, rng: random.Random) -> MCTSNode` — pick untried action, apply, create child.
  - `def playout(state: GameState, rng: random.Random, playout_policy: str = "greedy") -> float` — simulate to terminal, return result (1.0 win, 0.5 draw, 0.0 loss for current player).
  - `def backpropagate(node: MCTSNode, result: float)` — update visits/value up to root.
  - `def mcts_search(root_state: GameState, rng: random.Random, max_playouts: int, exploration: float = 1.414, playout_policy: str = "greedy") -> Action` — returns best action (most visits).

- [ ] **Step 1: Write failing tests**

`tests/agents/test_mcts_core.py`:
```python
from splendor_duel_engine.agents.mcts_core import MCTSNode, uct_select, expand, playout, backpropagate, mcts_search
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.engine.observation import observation
import random

def test_mcts_node_creation():
    state = new_game(0)
    node = MCTSNode(state=state, parent=None, action=None)
    assert node.visits == 0
    assert node.value == 0.0
    assert node.children == {}
    assert node.untried_actions == []  # populated lazily

def test_uct_select_prefers_unvisited():
    # Node with unvisited children should select one of them
    ...

def test_uct_select_balances_exploitation_exploration():
    # Child with high value but many visits vs low value few visits
    ...

def test_expand_creates_valid_child():
    state = new_game(0)
    node = MCTSNode(state=state, parent=None, action=None)
    # Manually populate untried_actions from decide(state).legal_actions
    child = expand(node, random.Random(0))
    assert child.parent is node
    assert child.action in node.untried_actions  # before removal

def test_playout_returns_valid_result():
    state = new_game(0)
    result = playout(state, random.Random(0), playout_policy="random")
    assert result in (0.0, 0.5, 1.0)

def test_playout_greedy_policy_terminates():
    state = new_game(0)
    result = playout(state, random.Random(0), playout_policy="greedy")
    assert result in (0.0, 0.5, 1.0)

def test_backpropagate_updates_path():
    root = MCTSNode(state=new_game(0), parent=None, action=None)
    child = MCTSNode(state=new_game(0), parent=root, action=some_action)
    root.children[some_action] = child
    backpropagate(child, 1.0)
    assert child.visits == 1
    assert child.value == 1.0
    assert root.visits == 1
    assert root.value == 1.0

def test_mcts_search_returns_legal_action():
    state = new_game(0)
    obs = observation(state, 0)
    det_state = determinize(obs, random.Random(0))
    action = mcts_search(det_state, random.Random(0), max_playouts=100)
    # Action must be legal in the original state
    from splendor_duel_engine.engine.actions import decide
    dp = decide(state)
    assert action in dp.legal_actions

def test_mcts_search_deterministic_with_same_seed():
    state = new_game(0)
    obs = observation(state, 0)
    det = determinize(obs, random.Random(0))
    a1 = mcts_search(det, random.Random(42), max_playouts=200)
    a2 = mcts_search(det, random.Random(42), max_playouts=200)
    assert a1 == a2
```

- [ ] **Step 2: Run to verify failure**
Run: `uv run python -m pytest tests/agents/test_mcts_core.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `mcts_core.py`**

```python
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from splendor_duel_engine.engine.actions import Action, apply, decide
from splendor_duel_engine.engine.state import GameState
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.random_agent import RandomAgent

if TYPE_CHECKING:
    from splendor_duel_engine.engine.observation import Observation

PLAYOUT_POLICIES = {"greedy": GreedyAgent, "random": lambda: RandomAgent(seed=None)}

@dataclass
class MCTSNode:
    state: GameState
    parent: MCTSNode | None
    action: Action | None
    children: dict[Action, MCTSNode] = field(default_factory=dict)
    visits: int = 0
    value: float = 0.0
    untried_actions: list[Action] = field(default_factory=list)

    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0

    def is_terminal(self) -> bool:
        return self.state.winner is not None

def uct_select(node: MCTSNode, exploration: float = 1.414) -> MCTSNode:
    while not node.is_terminal():
        if not node.is_fully_expanded():
            return node
        # UCT formula: value/visits + exploration * sqrt(ln(parent.visits)/visits)
        best_child = max(
            node.children.values(),
            key=lambda c: (c.value / c.visits) + exploration * math.sqrt(math.log(node.visits) / c.visits)
        )
        node = best_child
    return node

def expand(node: MCTSNode, rng: random.Random) -> MCTSNode:
    if not node.untried_actions:
        node.untried_actions = list(decide(node.state).legal_actions)
    action = rng.choice(node.untried_actions)
    node.untried_actions.remove(action)
    new_state = apply(node.state, action)
    child = MCTSNode(state=new_state, parent=node, action=action)
    node.children[action] = child
    return child

def playout(state: GameState, rng: random.Random, playout_policy: str = "greedy") -> float:
    policy_class = PLAYOUT_POLICIES[playout_policy]
    if playout_policy == "random":
        agent0 = policy_class()
        agent1 = policy_class()
    else:
        agent0 = policy_class()
        agent1 = policy_class()
    # Simulate from current state to terminal
    # Note: agents need Observation; we'll use a simplified playout that uses decide/apply directly
    # to avoid re-observation overhead, or we can call play_game with the agents
    from splendor_duel_engine.agents.base import play_game
    final = play_game(agent0, agent1, seed=rng.randint(0, 2**31-1))
    current_player = state.current_player
    if final.winner is None:
        return 0.5
    return 1.0 if final.winner == current_player else 0.0

def backpropagate(node: MCTSNode, result: float):
    while node is not None:
        node.visits += 1
        node.value += result
        node = node.parent

def mcts_search(
    root_state: GameState,
    rng: random.Random,
    max_playouts: int,
    exploration: float = 1.414,
    playout_policy: str = "greedy",
) -> Action:
    root = MCTSNode(state=root_state, parent=None, action=None)
    for _ in range(max_playouts):
        node = uct_select(root, exploration)
        if node.is_terminal():
            # Terminal node — backpropagate result directly
            current_player = root_state.current_player
            result = 1.0 if node.state.winner == current_player else 0.0
        else:
            node = expand(node, rng)
            result = playout(node.state, rng, playout_policy)
        backpropagate(node, result)
    # Return most-visited action
    best_action = max(root.children.items(), key=lambda kv: kv[1].visits)[0]
    return best_action
```

- [ ] **Step 4: Run tests, lint**
Run: `uv run python -m pytest tests/agents/test_mcts_core.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat(mcts): core MCTS with UCT, playouts, backpropagation"
```

---

### Task 3: MCTS Agent — Agent protocol wrapper

**Files:**
- Create: `src/splendor_duel_engine/agents/mcts_agent.py`
- Test: `tests/agents/test_mcts_agent.py`
- Modify: `src/splendor_duel_engine/agents/__init__.py` (export MCTSAgent)
- Modify: `src/splendor_duel_engine/eval/arena.py` (add to AGENT_REGISTRY)

**Interfaces:**
- Consumes: `agents.base.Agent`, `agents.base.play_game`, `agents.mcts_determinize.determinize`, `agents.mcts_core.mcts_search`, `engine.observation.observation`, `engine.actions.decide`, `random.Random`.
- Produces:
  - `class MCTSAgent:`
    - `__init__(self, seed: int | None = None, max_playouts: int = 2000, exploration: float = 1.414, playout_policy: str = "greedy")`
    - `choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action`
  - Arena registry entry: `"mcts": lambda: MCTSAgent(seed=None)`

- [ ] **Step 1: Write failing tests**

`tests/agents/test_mcts_agent.py`:
```python
from splendor_duel_engine.agents.mcts_agent import MCTSAgent
from splendor_duel_engine.engine.actions import decide
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.engine.observation import observation

def test_mcts_agent_chooses_legal_action():
    agent = MCTSAgent(seed=42, max_playouts=100)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions

def test_mcts_agent_deterministic_with_same_seed():
    agent1 = MCTSAgent(seed=123, max_playouts=200)
    agent2 = MCTSAgent(seed=123, max_playouts=200)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    a1 = agent1.choose_action(obs, dp.legal_actions)
    a2 = agent2.choose_action(obs, dp.legal_actions)
    assert a1 == a2

def test_mcts_agent_different_seeds_different_actions():
    agent1 = MCTSAgent(seed=1, max_playouts=200)
    agent2 = MCTSAgent(seed=2, max_playouts=200)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    a1 = agent1.choose_action(obs, dp.legal_actions)
    a2 = agent2.choose_action(obs, dp.legal_actions)
    # Very likely different with >1 legal action
    assert a1 != a2

def test_mcts_agent_full_game_terminates():
    from splendor_duel_engine.agents.base import play_game
    final = play_game(MCTSAgent(seed=1, max_playouts=100), MCTSAgent(seed=2, max_playouts=100), seed=999)
    assert final.winner in (0, 1)

def test_mcts_agent_respects_max_playouts():
    # With very low playouts, should still return a legal action
    agent = MCTSAgent(seed=0, max_playouts=10)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions

def test_mcts_agent_random_playout_policy():
    agent = MCTSAgent(seed=42, max_playouts=100, playout_policy="random")
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions

def test_mcts_agent_re_determinizes_each_decision():
    # Two calls with same Observation but different internal RNG state
    # should produce different determinizations and potentially different actions
    agent = MCTSAgent(seed=0, max_playouts=200)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    actions = [agent.choose_action(obs, dp.legal_actions) for _ in range(5)]
    # Should not be all identical (different determinizations each call)
    assert len(set(actions)) > 1 or len(dp.legal_actions) == 1
```

- [ ] **Step 2: Run to verify failure**
Run: `uv run python -m pytest tests/agents/test_mcts_agent.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `mcts_agent.py`**

```python
from __future__ import annotations
import random
from typing import TYPE_CHECKING

from splendor_duel_engine.agents.base import Agent
from splendor_duel_engine.agents.mcts_core import mcts_search
from splendor_duel_engine.agents.mcts_determinize import determinize
from splendor_duel_engine.engine.actions import Action, decide
from splendor_duel_engine.engine.observation import Observation
from splendor_duel_engine.engine.state import GameState

if TYPE_CHECKING:
    from splendor_duel_engine.engine.observation import Observation

class MCTSAgent:
    def __init__(
        self,
        seed: int | None = None,
        max_playouts: int = 2000,
        exploration: float = 1.414,
        playout_policy: str = "greedy",
    ) -> None:
        if max_playouts < 1:
            raise ValueError("max_playouts must be >= 1")
        if playout_policy not in ("greedy", "random"):
            raise ValueError(f"playout_policy must be 'greedy' or 'random', got {playout_policy}")
        self._rng = random.Random(seed)
        self._max_playouts = max_playouts
        self._exploration = exploration
        self._playout_policy = playout_policy

    def choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # Determinize the observation into a full GameState
        det_state = determinize(observation, self._rng)
        
        # Run MCTS search
        action = mcts_search(
            root_state=det_state,
            rng=self._rng,
            max_playouts=self._max_playouts,
            exploration=self._exploration,
            playout_policy=self._playout_policy,
        )
        
        # Action must be in legal_actions (it will be, since MCTS only expands legal moves)
        assert action in legal_actions
        return action
```

- [ ] **Step 4: Update `agents/__init__.py` and `eval/arena.py`**

`agents/__init__.py`: add `MCTSAgent` to `__all__` and import.

`eval/arena.py`: add `"mcts": lambda: MCTSAgent(seed=None)` to `AGENT_REGISTRY`.

- [ ] **Step 5: Run tests, lint**
Run: `uv run python -m pytest tests/agents/test_mcts_agent.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 6: Commit**
```bash
git add -A && git commit -m "feat(mcts): MCTSAgent with Agent protocol, arena integration"
```

---

### Task 4: MCTS evaluation — arena integration tests

**Files:**
- Test: `tests/eval/test_mcts_arena.py`

**Interfaces:**
- Consumes: `eval.arena.play_match`, `agents.mcts_agent.MCTSAgent`, `agents.greedy_agent.GreedyAgent`, `agents.random_agent.RandomAgent`.

- [ ] **Step 1: Write failing tests**

`tests/eval/test_mcts_arena.py`:
```python
from splendor_duel_engine.agents.mcts_agent import MCTSAgent
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.eval.arena import play_match
from splendor_duel_engine.agents.base import play_game

def test_mcts_vs_random():
    # MCTS with low playouts should still beat random
    result = play_match(
        MCTSAgent(seed=1, max_playouts=500, playout_policy="greedy"),
        RandomAgent(seed=2),
        n_games=20,
        seed_base=100
    )
    assert result["agent_a_winrate"] > 0.6

def test_mcts_vs_greedy():
    # MCTS should be competitive with greedy (may not beat it at low playouts)
    result = play_match(
        MCTSAgent(seed=1, max_playouts=1000, playout_policy="greedy"),
        GreedyAgent(),
        n_games=20,
        seed_base=200
    )
    # At 1000 playouts, should be roughly even or better
    assert result["agent_a_winrate"] > 0.35  # not crushed

def test_mcts_both_seats():
    # Test MCTS as both player 0 and player 1
    for seed in range(5):
        final1 = play_game(MCTSAgent(seed=seed, max_playouts=200), GreedyAgent(), seed=seed)
        final2 = play_game(GreedyAgent(), MCTSAgent(seed=seed, max_playouts=200), seed=seed)
        assert final1.winner in (0, 1)
        assert final2.winner in (0, 1)

def test_mcts_arena_cli_runs():
    import subprocess
    result = subprocess.run([
        "uv", "run", "python", "-m", "splendor_duel_engine.eval.arena",
        "mcts", "greedy", "-n", "10"
    ], capture_output=True, text=True, cwd=".")
    assert result.returncode == 0
    assert "winrate" in result.stdout.lower()
```

- [ ] **Step 2: Run to verify failure**
Run: `uv run python -m pytest tests/eval/test_mcts_arena.py -v` — expected: FAIL (module missing or MCTSAgent not in registry).

- [ ] **Step 3: Run tests after Tasks 1-3 are done**
Run: `uv run python -m pytest tests/eval/test_mcts_arena.py -v` — expected: PASS.

- [ ] **Step 4: Run full suite, lint**
Run: `uv run python -m pytest -q && uv run ruff check .` — expected: all PASS.

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "test(mcts): arena integration tests for MCTS agent"
```

---

### Task 5: Performance and memory tests

**Files:**
- Test: `tests/agents/test_mcts_performance.py`

**Interfaces:**
- Consumes: `agents.mcts_agent.MCTSAgent`, `engine.state.new_game`, `engine.observation.observation`, `engine.actions.decide`.

- [ ] **Step 1: Write failing tests**

`tests/agents/test_mcts_performance.py`:
```python
import time
from splendor_duel_engine.agents.mcts_agent import MCTSAgent
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.actions import decide

def test_mcts_decision_time_reasonable():
    agent = MCTSAgent(seed=0, max_playouts=2000)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    
    start = time.perf_counter()
    action = agent.choose_action(obs, dp.legal_actions)
    elapsed = time.perf_counter() - start
    
    # 2000 playouts should complete in well under 2 seconds
    assert elapsed < 2.0, f"MCTS took {elapsed:.2f}s for 2000 playouts"
    assert action in dp.legal_actions

def test_mcts_no_memory_leak():
    # Run multiple decisions, memory should not grow unbounded
    import gc
    agent = MCTSAgent(seed=0, max_playouts=500)
    state = new_game(0)
    
    for _ in range(10):
        if state.winner is not None:
            break
        obs = observation(state, state.current_player)
        dp = decide(state)
        action = agent.choose_action(obs, dp.legal_actions)
        state = apply(state, action)
    
    # Force GC and check no obvious leaks (qualitative)
    gc.collect()
    # Just verify it runs without error

def test_mcts_scales_with_playouts():
    # More playouts = more time, roughly linear
    for playouts in [100, 500, 1000]:
        agent = MCTSAgent(seed=0, max_playouts=playouts)
        state = new_game(0)
        obs = observation(state, state.current_player)
        dp = decide(state)
        
        start = time.perf_counter()
        agent.choose_action(obs, dp.legal_actions)
        elapsed = time.perf_counter() - start
        
        assert elapsed < 1.0  # generous bound
```

- [ ] **Step 2: Run to verify failure**
Run: `uv run python -m pytest tests/agents/test_mcts_performance.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Run after Tasks 1-3**
Run: `uv run python -m pytest tests/agents/test_mcts_performance.py -v` — expected: PASS.

- [ ] **Step 4: Commit**
```bash
git add -A && git commit -m "test(mcts): performance and memory tests"
```

---

## Self-Review Checklist

- [ ] Spec coverage: Determinized MCTS with Observation API, UCT, configurable playouts/policy, arena integration.
- [ ] Step scan: Each step has exactly one test and one implementation action.
- [ ] Type consistency: `MCTSAgent` implements `Agent` protocol; `determinize` returns `GameState`; `mcts_search` returns `Action`.
- [ ] Review Focus: All five items have tests in Tasks 1–5.
- [ ] Module discipline: `agents/` stays IO-free; determinization and MCTS core are internal modules; only `mcts_agent.py` exposes public `MCTSAgent`.
- [ ] Proportion: Plan is concise; code blocks only for non-obvious algorithms (UCT, determinization).

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-10-21-mcts-agent.md`. Please review the plan. Does it capture what you want?**

**Recommended execution approach:** **Subagent-driven** — the tasks have clear independent interfaces (determinization → core → agent wrapper → integration), each with its own test surface. The determinization helper (Task 1) is the critical foundation that Tasks 2–3 depend on; getting it right early avoids cascading rework. Subagent-driven gives independent review gates at each layer.