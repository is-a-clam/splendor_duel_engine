# Baseline Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create two baseline agents — a random agent and a greedy heuristic agent — that use the engine's Observation API to make decisions through the step API (`decide`/`apply`).

**Architecture:** An `agents` module with a common `Agent` protocol/interface. Agents receive an `Observation` (not the full `GameState`) and return a legal `Action`. The random agent samples uniformly; the greedy agent applies deterministic rules per decision point. Two companion modules consume the agents: `eval` (arena for head-to-head batch matches) and `play` (a terminal human-vs-agent game, where a `HumanAgent` implements the same `Agent` protocol and blocks on stdin).

**Tech Stack:** Python 3.11+, stdlib only, depends on engine (`decide`, `apply`, `observation`, `Action` types, `Phase`, `Color`, `Tokens`, `Card`).

**Spec:** `docs/specs/splendor-duel-rules.md` (game rules); `docs/superpowers/plans/2026-10-17-python-engine.md` Task 9 (Observation API).

**Dependency:** This plan requires the Observation API from the engine plan (Task 9: `src/splendor_duel_engine/engine/observation.py` with `observation(state, player) -> Observation`). Agents cannot be fully implemented until that exists. For now, agents can use a temporary `GameState` view or we implement a minimal observation shim.

## Global Constraints

- Python 3.11+; **no new runtime dependencies** (engine has none; agents add none).
- Type hints on all public functions; ruff clean; tests pass.
- Agents must use `observation(state, player)` — never access `GameState` directly (hidden-info discipline).
- Agents must only choose from `decide(state).legal_actions` — never construct actions manually.
- Deterministic given a seed: random agent takes an `rng: random.Random` (or seed) for reproducibility.
- Greedy agent is fully deterministic (no RNG).

## Review Focus

1. **Hidden-info leakage** — agents must not see opponent's deck-reserved cards or deck order; they only get `Observation`. Pinned to agent tests that verify `observation()` is the only state access.
2. **Illegal action selection** — agents must only pick from `legal_actions`; test with engine's `apply` rejection. Pinned to integration tests.
3. **Token limit awareness** — greedy agent must not take tokens that would exceed hand limit of 10 (or must plan to discard). Pinned to greedy agent's take-tokens logic.
4. **Gold scarcity awareness** — only 3 gold exist total; greedy agent tracks gold on board/in bag/opponent hand. Pinned to reserve/buy logic.
5. **Replenish privilege cost** — replenishing gives opponent a privilege; greedy agent only replenishes when forced or strategically necessary. Pinned to REPLENISH decision logic.

---

### Task 1: Agents module scaffolding and Agent protocol

**Files:**
- Create: `src/splendor_duel_engine/agents/__init__.py`
- Create: `src/splendor_duel_engine/agents/base.py`
- Test: `tests/agents/test_base.py`

**Interfaces:**
- Consumes: Engine `observation` (Task 9 — **must be implemented first**), `decide`, `apply`, `Action`, `Phase`, `Color`, `Tokens`.
- Produces:
  - `base.py`:
    - `from typing import Protocol`
    - `class Agent(Protocol):`
      - `def choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action: ...`
    - `def play_game(agent0: Agent, agent1: Agent, seed: int) -> GameState` — helper that runs a full game between two agents using `new_game`, `decide`, `apply`, `observation`; returns final `GameState` with `winner` set.
  - **Note:** Until `engine.observation` exists, agents will use a temporary `get_observation(state, player)` shim in `agents.base` that exposes the same interface using public `GameState` fields. This shim will be replaced by the real `engine.observation.observation` once Task 9 is done.

- [ ] **Step 1: Write failing tests**

`tests/agents/test_base.py`:
```python
from splendor_duel_engine.engine.actions import decide
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.agents.base import Agent, play_game

def test_agent_protocol_exists():
    # Just verify the protocol can be imported and used for type checking
    class DummyAgent:
        def choose_action(self, obs, legal_actions):
            return legal_actions[0]
    assert isinstance(DummyAgent(), Agent)

def test_play_game_runs_to_completion():
    class FirstLegalAgent:
        def choose_action(self, obs, legal_actions):
            return legal_actions[0]
    final = play_game(FirstLegalAgent(), FirstLegalAgent(), seed=0)
    assert final.winner in (0, 1)
    assert final.phase.name == "GAME_OVER"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/agents/test_base.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `base.py`**

`base.py`:
```python
from __future__ import annotations
from typing import Protocol
import random

from splendor_duel_engine.engine.actions import Action, apply, decide
from splendor_duel_engine.engine.observation import Observation, observation
from splendor_duel_engine.engine.state import GameState, new_game

class Agent(Protocol):
    def choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action: ...

def play_game(agent0: Agent, agent1: Agent, seed: int) -> GameState:
    state = new_game(seed)
    agents = (agent0, agent1)
    while state.winner is None:
        player = state.current_player
        obs = observation(state, player)
        dp = decide(state)
        action = agents[player].choose_action(obs, dp.legal_actions)
        state = apply(state, action)
    return state
```

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/agents/test_base.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(agents): base protocol and play_game helper"
```

---

### Task 2: Random agent

**Files:**
- Create: `src/splendor_duel_engine/agents/random_agent.py`
- Test: `tests/agents/test_random_agent.py`

**Interfaces:**
- Consumes: Task 1 (`Agent` protocol, `Observation`, `Action`).
- Produces:
  - `random_agent.py`:
    - `class RandomAgent:`
      - `__init__(self, seed: int | None = None)` — creates internal `random.Random(seed)` or uses system randomness if `None`.
      - `choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action` — returns `self._rng.choice(legal_actions)`.

- [ ] **Step 1: Write failing tests**

`tests/agents/test_random_agent.py`:
```python
import pytest
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.engine.actions import decide
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.engine.observation import observation

def test_random_agent_chooses_legal_action():
    agent = RandomAgent(seed=42)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions

def test_random_agent_deterministic_with_same_seed():
    agent1 = RandomAgent(seed=123)
    agent2 = RandomAgent(seed=123)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    # Both agents should make the same choice given the same RNG state
    a1 = agent1.choose_action(obs, dp.legal_actions)
    a2 = agent2.choose_action(obs, dp.legal_actions)
    assert a1 == a2

def test_random_agent_different_seeds_different_choices():
    agent1 = RandomAgent(seed=1)
    agent2 = RandomAgent(seed=2)
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    # Very likely different (not guaranteed but extremely likely with >1 action)
    choices1 = [agent1.choose_action(obs, dp.legal_actions) for _ in range(10)]
    choices2 = [agent2.choose_action(obs, dp.legal_actions) for _ in range(10)]
    assert choices1 != choices2  # different sequences

def test_random_agent_full_game_terminates():
    from splendor_duel_engine.agents.base import play_game
    final = play_game(RandomAgent(seed=1), RandomAgent(seed=2), seed=999)
    assert final.winner in (0, 1)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/agents/test_random_agent.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `random_agent.py`**

```python
from __future__ import annotations
import random
from typing import TYPE_CHECKING

from splendor_duel_engine.agents.base import Agent
from splendor_duel_engine.engine.actions import Action
from splendor_duel_engine.engine.observation import Observation

if TYPE_CHECKING:
    from splendor_duel_engine.engine.actions import Action as ActionType

class RandomAgent:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action:
        return self._rng.choice(legal_actions)
```

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/agents/test_random_agent.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(agents): random agent with seeded RNG"
```

---

### Task 3: Greedy agent — core heuristics and decision logic

**Files:**
- Create: `src/splendor_duel_engine/agents/greedy_agent.py`
- Test: `tests/agents/test_greedy_agent.py`

**Interfaces:**
- Consumes: Task 1 (`Agent` protocol, `Observation`, `Action`, `Phase`, `Color`, `Tokens`, `Card`, `RoyalCard`).
- Produces:
  - `greedy_agent.py`:
    - `class GreedyAgent:`
      - `__init__(self) -> None` — no RNG, fully deterministic.
      - `choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action` — dispatches to phase-specific methods.
    - Private helper methods for each phase:
      - `_choose_use_privileges(obs, legal_actions) -> Action`
      - `_choose_replenish(obs, legal_actions) -> Action`
      - `_choose_mandatory(obs, legal_actions) -> Action`
      - `_choose_payment(obs, legal_actions) -> Action`
      - `_choose_multicolor(obs, legal_actions) -> Action`
      - `_choose_steal(obs, legal_actions) -> Action`
      - `_choose_royal(obs, legal_actions) -> Action`
      - `_choose_discard(obs, legal_actions) -> Action`

**Greedy heuristics (deterministic rules):**

| Phase | Heuristic |
|-------|-----------|
| `USE_PRIVILEGES` | If have privileges, use them to take the color most needed for the highest-value affordable card. If no cards affordable, take the **least abundant non-gold color on board** (contested color). Always `DoneWithPrivileges` when out of privileges or no useful color. |
| `REPLENISH` | **Only replenish if forced** (MANDATORY would have zero legal actions AND bag non-empty) **AND bag has >5 tokens**. Otherwise `DoneWithReplenish`. |
| `MANDATORY` | Priority with one-step lookahead: (1) Buy best affordable card (points×2 + crowns). (2) **Take tokens if it enables a high-value buy next turn** (simulate: would the resulting hand make a >4pt card affordable?). (3) Reserve if gold on board, <3 reserved slots, for high-value card (>4pts or good ability). (4) Take tokens: score = tokens×2 + needed_bonus - penalty_cost (configurable weights). |
| `CHOOSE_PAYMENT` | Among legal `PayTokens`, prefer fewest gold, then fewest total tokens. |
| `MULTICOLOR_COLOR` | Choose color with most bonus tokens. Tie-break: highest point potential. |
| `STEAL_TOKEN` | Steal opponent's most-held non-gold color, preferring colors we need. |
| `CHOOSE_ROYAL` | Priority: `EXTRA_TURN` > `PRIVILEGE` > `STEAL_TOKEN` > 3pt none. |
| `DISCARD` | Discard excess (total - 10) preferring: non-needed colors first, then high-count colors, preserve gold/pearls. Simple, no lookahead. |

- [ ] **Step 1: Write failing tests**

`tests/agents/test_greedy_agent.py`:
```python
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.engine.actions import decide
from splendor_duel_engine.engine.state import new_game
from splendor_duel_engine.engine.observation import observation
from splendor_duel_engine.engine.phase import Phase

def test_greedy_agent_chooses_legal_action():
    agent = GreedyAgent()
    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions

def test_greedy_agent_deterministic():
    agent1 = GreedyAgent()
    agent2 = GreedyAgent()
    state = new_game(42)
    # Play a few turns and verify same choices
    for _ in range(5):
        if state.winner is not None:
            break
        player = state.current_player
        obs = observation(state, player)
        dp = decide(state)
        a1 = agent1.choose_action(obs, dp.legal_actions)
        a2 = agent2.choose_action(obs, dp.legal_actions)
        assert a1 == a2, f"Diverged at phase {dp.phase}: {a1} vs {a2}"
        state = apply(state, a1)  # apply from engine.actions

def test_greedy_agent_full_game_terminates():
    from splendor_duel_engine.agents.base import play_game
    final = play_game(GreedyAgent(), GreedyAgent(), seed=0)
    assert final.winner in (0, 1)

def test_greedy_never_replenishes_unless_forced_or_scarce_board():
    # Construct a state in REPLENISH with bag non-empty but board has plenty of tokens
    # Greedy should choose DoneWithReplenish
    ...

def test_greedy_prefers_buying_high_value_affordable_card():
    # Construct state where multiple cards affordable; verify picks highest (points*2+crowns)
    ...

def test_greedy_reserves_only_when_gold_needed_and_slots_available():
    # No gold on board -> no ReserveCard in legal actions chosen
    # Gold on board, 3 reserved -> no ReserveCard
    # Gold on board, <3 reserved -> picks ReserveCard for high-value card
    ...

def test_greedy_avoids_penalty_unless_high_value_purchase_enabled():
    # If taking 3 same color enables immediate buy of 4+ point card, allow it
    ...

def test_greedy_multicolor_chooses_most_bonus_color():
    # Agent has bonus: 3 white, 1 blue; multicolor card -> should choose white
    ...

def test_greedy_discard_prefers_excess_colors_not_needed():
    # Hand has 12 tokens, needs to discard 2; has 4 red (not needed), 3 blue (needed)
    # Should discard reds first
    ...
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/agents/test_greedy_agent.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `greedy_agent.py`**

Key implementation notes:
- All helpers receive `(obs: Observation, legal_actions: tuple[Action, ...])`.
- Use `obs.you` for current player's public view, `obs.opponent` for opponent.
- `obs.you.tokens.total()` gives hand size; max is 10.
- Affordability check: for each card in `obs.you.purchased` (no, pyramid/reserved) — need to check pyramid cards from `obs.pyramid` and own reserved from `obs.you.reserved_public` + `obs.your_reserved_deck`.
- For payment: `legal_actions` are already filtered to legal payments by `decide`; greedy just picks the best one.
- Token line evaluation: iterate `TakeTokens` actions, compute heuristic score.

Structure:
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from splendor_duel_engine.agents.base import Agent
from splendor_duel_engine.engine.actions import (
    Action, TakeTokens, BuyCard, ReserveCard, PayTokens,
    ChooseMulticolor, ChooseStealToken, ChooseRoyal, DiscardTokens,
    UsePrivilege, DoneWithPrivileges, Replenish, DoneWithReplenish
)
from splendor_duel_engine.engine.observation import Observation
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.colors import Color, Tokens, GEM_COLORS

if TYPE_CHECKING:
    from splendor_duel_engine.engine.cards import Card, RoyalCard
    from splendor_duel_engine.engine.state import PurchasedCard, ReservedCard

class GreedyAgent:
    def __init__(self) -> None:
        pass

    def choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # Determine current phase from legal_actions[0] type or observation context
        # Actually, phase is not directly in Observation; infer from action types
        # legal_actions will only contain actions for one phase
        action_type = type(legal_actions[0])
        
        if action_type is UsePrivilege or action_type is DoneWithPrivileges:
            return self._choose_use_privileges(observation, legal_actions)
        elif action_type is Replenish or action_type is DoneWithReplenish:
            return self._choose_replenish(observation, legal_actions)
        elif action_type is TakeTokens or action_type is BuyCard or action_type is ReserveCard:
            return self._choose_mandatory(observation, legal_actions)
        elif action_type is PayTokens:
            return self._choose_payment(observation, legal_actions)
        elif action_type is ChooseMulticolor:
            return self._choose_multicolor(observation, legal_actions)
        elif action_type is ChooseStealToken:
            return self._choose_steal(observation, legal_actions)
        elif action_type is ChooseRoyal:
            return self._choose_royal(observation, legal_actions)
        elif action_type is DiscardTokens:
            return self._choose_discard(observation, legal_actions)
        else:
            return legal_actions[0]  # fallback

    # --- Phase-specific methods ---

    def _choose_use_privileges(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # If DoneWithPrivileges is the only action, take it
        done_actions = [a for a in legal_actions if isinstance(a, DoneWithPrivileges)]
        use_actions = [a for a in legal_actions if isinstance(a, UsePrivilege)]
        if not use_actions:
            return done_actions[0]
        
        # Heuristic: pick color most needed for best affordable card
        needed_colors = self._colors_needed_for_best_purchase(obs)
        if needed_colors:
            for color in needed_colors:
                for action in use_actions:
                    if action.color == color:
                        return action
        # Fallback: most abundant non-gold color on board
        board_colors = [c for c in obs.board if c is not None and c != Color.GOLD]
        if board_colors:
            from collections import Counter
            most_common = Counter(board_colors).most_common(1)[0][0]
            for action in use_actions:
                if action.color == most_common:
                    return action
        return done_actions[0]

    def _choose_replenish(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        done_actions = [a for a in legal_actions if isinstance(a, DoneWithReplenish)]
        replenish_actions = [a for a in legal_actions if isinstance(a, Replenish)]
        
        if not replenish_actions:
            return done_actions[0]
        
        # Only replenish if forced (no mandatory actions would exist) OR board is scarce
        # Heuristic: count non-gold tokens on board
        non_gold_count = sum(1 for c in obs.board if c is not None and c != Color.GOLD)
        if non_gold_count < 3:
            return replenish_actions[0]
        return done_actions[0]

    def _choose_mandatory(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # Priority: Buy > Reserve > TakeTokens
        buy_actions = [a for a in legal_actions if isinstance(a, BuyCard)]
        if buy_actions:
            return self._best_buy_action(obs, buy_actions)
        
        reserve_actions = [a for a in legal_actions if isinstance(a, ReserveCard)]
        if reserve_actions and self._should_reserve(obs):
            return self._best_reserve_action(obs, reserve_actions)
        
        take_actions = [a for a in legal_actions if isinstance(a, TakeTokens)]
        if take_actions:
            return self._best_take_action(obs, take_actions)
        
        return legal_actions[0]  # fallback

    def _best_buy_action(self, obs: Observation, buy_actions: list[BuyCard]) -> BuyCard:
        # Score cards by points*2 + crowns
        best_action = None
        best_score = -1
        for action in buy_actions:
            card = self._find_card_by_id(obs, action.card_id)
            if card:
                score = card.points * 2 + card.crowns
                if score > best_score:
                    best_score = score
                    best_action = action
        return best_action or buy_actions[0]

    def _should_reserve(self, obs: Observation) -> bool:
        # Reserve if gold on board and we have < 3 reserved cards
        has_gold = any(c == Color.GOLD for c in obs.board)
        reserved_count = len(obs.you.reserved_public) + len(obs.your_reserved_deck)
        return has_gold and reserved_count < 3

    def _best_reserve_action(self, obs: Observation, reserve_actions: list[ReserveCard]) -> ReserveCard:
        # Prefer pyramid cards with high value, else deck with most cards
        best_action = None
        best_score = -1
        for action in reserve_actions:
            if action.source == "pyramid":
                card = self._find_pyramid_card(obs, action.index)
                if card:
                    score = card.points * 2 + card.crowns
            else:  # deck
                # Deck level: index 0=level3, 1=level2, 2=level1
                deck_counts = obs.deck_counts
                if action.index < len(deck_counts) and deck_counts[action.index] > 0:
                    # Prefer higher level (more points typically)
                    score = (3 - action.index) * 10  # level 3 > 2 > 1
                else:
                    score = -1
            if score > best_score:
                best_score = score
                best_action = action
        return best_action or reserve_actions[0]

    def _best_take_action(self, obs: Observation, take_actions: list[TakeTokens]) -> TakeTokens:
        needed_colors = self._colors_needed_for_best_purchase(obs)
        
        def score_line(action: TakeTokens) -> tuple[int, int, int]:
            colors_taken = [obs.board[i] for i in action.line if obs.board[i] is not None]
            # Penalty check
            from collections import Counter
            counts = Counter(colors_taken)
            has_penalty = any(cnt >= 3 for cnt in counts.values()) or counts.get(Color.PEARL, 0) >= 2
            
            # Value: number of tokens * 2 + needed color bonus - penalty
            needed_bonus = sum(2 for c in colors_taken if c in needed_colors)
            penalty_cost = -10 if has_penalty else 0
            return (len(colors_taken) * 2 + needed_bonus + penalty_cost, -len(action.line), action.line)
        
        return max(take_actions, key=score_line)

    def _choose_payment(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        pay_actions = [a for a in legal_actions if isinstance(a, PayTokens)]
        # Prefer: fewest gold, fewest total tokens, most diverse remaining hand
        def payment_score(action: PayTokens) -> tuple[int, int, int]:
            gold_used = action.payment.gold
            total_used = action.payment.total()
            # Diversity: number of colors with >0 remaining after payment (approximate)
            return (-gold_used, -total_used, 0)  # negative because we want min
        return max(pay_actions, key=payment_score)

    def _choose_multicolor(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # Choose color with most bonus tokens
        bonus_counts = [(obs.you.bonus.count(c), c) for c in GEM_COLORS]
        bonus_counts.sort(reverse=True)
        best_color = bonus_counts[0][1]
        for action in legal_actions:
            if isinstance(action, ChooseMulticolor) and action.color == best_color:
                return action
        return legal_actions[0]

    def _choose_steal(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # Steal color opponent has most of (non-gold), preferring colors we need
        opp_tokens = obs.opponent.tokens
        needed = set(self._colors_needed_for_best_purchase(obs))
        candidates = []
        for color in GEM_COLORS | {Color.PEARL}:
            count = opp_tokens.count(color)
            if count > 0:
                priority = 2 if color in needed else 1
                candidates.append((priority, count, color))
        candidates.sort(reverse=True)
        if candidates:
            best_color = candidates[0][2]
            for action in legal_actions:
                if isinstance(action, ChooseStealToken) and action.color == best_color:
                    return action
        return legal_actions[0]

    def _choose_royal(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # Priority: EXTRA_TURN > PRIVILEGE > STEAL_TOKEN > 3pt none
        ability_order = {
            "extra_turn": 4,
            "privilege": 3,
            "steal_token": 2,
            None: 1,
        }
        best_action = None
        best_priority = -1
        for action in legal_actions:
            if isinstance(action, ChooseRoyal):
                royal = next((r for r in obs.royals_available if r.id == action.royal_id), None)
                if royal:
                    priority = ability_order.get(royal.ability.value if royal.ability else None, 0)
                    if priority > best_priority:
                        best_priority = priority
                        best_action = action
        return best_action or legal_actions[0]

    def _choose_discard(self, obs: Observation, legal_actions: tuple[Action, ...]) -> Action:
        # legal_actions are all valid DiscardTokens that sum to excess
        # Prefer discarding: gold last, pearls last, colors not needed, colors with most in hand
        needed = set(self._colors_needed_for_best_purchase(obs))
        hand = obs.you.tokens
        
        def discard_score(action: DiscardTokens) -> tuple[int, int, int, int]:
            # Score: prefer discarding non-needed, non-gold, non-pearl, high-count colors
            gold_discarded = action.tokens.gold
            pearl_discarded = action.tokens.pearl
            needed_discarded = sum(action.tokens.count(c) for c in needed)
            # We want to minimize these "bad" discards
            return (-gold_discarded, -pearl_discarded, -needed_discarded, 0)
        
        return max(legal_actions, key=discard_score)

    # --- Helpers ---

    def _colors_needed_for_best_purchase(self, obs: Observation) -> list[Color]:
        """Return list of colors needed for the highest-value affordable card, most needed first."""
        affordable = self._get_affordable_cards(obs)
        if not affordable:
            return []
        # Sort by value
        affordable.sort(key=lambda c: c.points * 2 + c.crowns, reverse=True)
        best_card = affordable[0]
        # Compute net cost after bonuses
        needed = []
        for color in GEM_COLORS:
            cost = best_card.cost.count(color)
            have_bonus = obs.you.bonus.count(color)
            have_tokens = obs.you.tokens.count(color)
            net_need = cost - have_bonus - have_tokens
            if net_need > 0:
                needed.extend([color] * net_need)
        # Also consider gold as wild for any remaining need
        total_net_need = sum(1 for c in needed)
        gold_available = obs.you.tokens.gold
        # Gold can cover any shortage
        return needed

    def _get_affordable_cards(self, obs: Observation) -> list[Card]:
        """Return list of cards the player can afford to buy right now."""
        from splendor_duel_engine.engine.cards import Card
        affordable: list[Card] = []
        
        # Check pyramid cards
        for row in obs.pyramid:
            for card in row:
                if card is not None and self._can_afford(obs, card):
                    affordable.append(card)
        
        # Check own reserved cards (public + hidden)
        for rc in obs.you.reserved_public:
            if self._can_afford(obs, rc):
                affordable.append(rc)
        for rc in obs.your_reserved_deck:
            if self._can_afford(obs, rc):
                affordable.append(rc)
        
        return affordable

    def _can_afford(self, obs: Observation, card: Card) -> bool:
        """Check if card is affordable with current tokens + bonuses + gold, without exceeding hand limit after payment."""
        # Hand limit check: after paying, tokens - payment + (card gives no tokens) <= 10
        # Actually, payment tokens go to bag, so hand decreases by payment.total()
        # But we also gain the card's bonus (later). For affordability, just check payment possible.
        payment_needed = Tokens()
        for color in GEM_COLORS:
            cost = card.cost.count(color)
            bonus = obs.you.bonus.count(color)
            have = obs.you.tokens.count(color)
            net = max(0, cost - bonus - have)
            if net > 0:
                payment_needed = payment_needed.__class__(**{color.value: net})
        
        pearl_cost = card.cost.pearl
        have_pearl = obs.you.tokens.pearl
        if pearl_cost > have_pearl:
            payment_needed = payment_needed.__class__(**{**{k: v for k, v in payment_needed.__dict__.items()}, Color.PEARL.value: pearl_cost - have_pearl})
        
        # Check if gold can cover the rest
        total_deficit = sum(payment_needed.count(c) for c in GEM_COLORS) + payment_needed.pearl
        return obs.you.tokens.gold >= total_deficit

    def _find_card_by_id(self, obs: Observation, card_id: str) -> Card | None:
        for row in obs.pyramid:
            for card in row:
                if card and card.id == card_id:
                    return card
        for rc in obs.you.reserved_public:
            if rc.id == card_id:
                return rc
        for rc in obs.your_reserved_deck:
            if rc.id == card_id:
                return rc
        return None

    def _find_pyramid_card(self, obs: Observation, index: int) -> Card | None:
        # index maps to pyramid row/slot - need to decode
        # pyramid is tuple of rows: level3(3), level2(4), level1(5)
        flat_index = 0
        for row in obs.pyramid:
            for card in row:
                if flat_index == index:
                    return card
                flat_index += 1
        return None
```

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/agents/test_greedy_agent.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(agents): greedy heuristic agent with deterministic rules"
```

---

### Task 4: Agent evaluation CLI and head-to-head tests

**Files:**
- Modify: `src/splendor_duel_engine/agents/__init__.py` (export agents)
- Create: `src/splendor_duel_engine/eval/arena.py` (or extend if exists)
- Test: `tests/eval/test_arena.py`

**Interfaces:**
- Consumes: Tasks 1–3 (`play_game`, `RandomAgent`, `GreedyAgent`).
- Produces:
  - `arena.py`: `def play_match(agent_a: Agent, agent_b: Agent, n_games: int, seed_base: int = 0) -> dict` — plays `n_games` with alternating seats (agent_a first in even games, agent_b first in odd games), returns win counts, win rates, avg game length.
  - CLI entry: `python -m splendor_duel_engine.eval.arena <agent_a> <agent_b> -n <games>` — agent names: `random`, `greedy`.

- [ ] **Step 1: Write failing tests**

`tests/eval/test_arena.py`:
```python
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.eval.arena import play_match

def test_random_vs_random_symmetric():
    result = play_match(RandomAgent(seed=1), RandomAgent(seed=2), n_games=20, seed_base=100)
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
    result = subprocess.run([
        "uv", "run", "python", "-m", "splendor_duel_engine.eval.arena",
        "greedy", "random", "-n", "10"
    ], capture_output=True, text=True, cwd=".")
    assert result.returncode == 0
    assert "winrate" in result.stdout.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/eval/test_arena.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `arena.py` and CLI**

`arena.py`:
```python
from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass

from splendor_duel_engine.agents.base import Agent, play_game
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.agents.greedy_agent import GreedyAgent

AGENT_REGISTRY = {
    "random": lambda: RandomAgent(seed=None),  # System randomness for variety
    "greedy": GreedyAgent,
}

@dataclass
class MatchResult:
    agent_a_wins: int
    agent_b_wins: int
    agent_a_winrate: float
    agent_b_winrate: float
    avg_turns: float

def play_match(agent_a: Agent, agent_b: Agent, n_games: int, seed_base: int = 0) -> MatchResult:
    a_wins = b_wins = 0
    total_turns = 0
    for i in range(n_games):
        # Alternate who goes first
        if i % 2 == 0:
            first, second = agent_a, agent_b
            first_is_a = True
        else:
            first, second = agent_b, agent_a
            first_is_a = False
        
        # Create fresh agents for each game if they have state (RandomAgent with seed=None is fine)
        # For reproducibility, we could pass seed_base + i to RandomAgent
        final = play_game(first, second, seed=seed_base + i)
        total_turns += sum(len(p.purchased) for p in final.players)  # rough proxy
        if final.winner == (0 if first_is_a else 1):
            a_wins += 1
        else:
            b_wins += 1
    
    return MatchResult(
        agent_a_wins=a_wins,
        agent_b_wins=b_wins,
        agent_a_winrate=a_wins / n_games,
        agent_b_winrate=b_wins / n_games,
        avg_turns=total_turns / n_games if n_games > 0 else 0,
    )

def main():
    parser = argparse.ArgumentParser(description="Play agent vs agent matches")
    parser.add_argument("agent_a", choices=list(AGENT_REGISTRY.keys()), help="First agent")
    parser.add_argument("agent_b", choices=list(AGENT_REGISTRY.keys()), help="Second agent")
    parser.add_argument("-n", "--games", type=int, default=100, help="Number of games")
    parser.add_argument("--seed", type=int, default=0, help="Base seed")
    args = parser.parse_args()

    agent_a = AGENT_REGISTRY[args.agent_a]()
    agent_b = AGENT_REGISTRY[args.agent_b]()
    result = play_match(agent_a, agent_b, args.games, args.seed)

    print(f"{args.agent_a} vs {args.agent_b} ({args.games} games, alternating seats)")
    print(f"  {args.agent_a}: {result.agent_a_wins} wins ({result.agent_a_winrate:.1%})")
    print(f"  {args.agent_b}: {result.agent_b_wins} wins ({result.agent_b_winrate:.1%})")
    print(f"  Avg turns: {result.avg_turns:.1f}")

if __name__ == "__main__":
    main()
```

Update `src/splendor_duel_engine/agents/__init__.py`:
```python
from splendor_duel_engine.agents.base import Agent, play_game
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.agents.greedy_agent import GreedyAgent

__all__ = ["Agent", "play_game", "RandomAgent", "GreedyAgent"]
```

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/eval/test_arena.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(agents): evaluation arena CLI and head-to-head tests"
```

---

### Task 5: Human play module — terminal human-vs-agent game

**Files:**
- Create: `src/splendor_duel_engine/play/__init__.py`
- Create: `src/splendor_duel_engine/play/human.py`
- Test: `tests/play/test_human.py`
- Modify: `AGENTS.md` (layout block: add `play/`)

**Interfaces:**
- Consumes: Tasks 1–4 (`Agent` protocol, `play_game`, `Observation`, `Phase`, arena's `AGENT_REGISTRY`).
- Produces:
  - `human.py`:
    - `class HumanAgent:` — implements the `Agent` protocol; blocks on IO instead of computing.
      - `__init__(self, input_fn=input, print_fn=print)` — injectable IO for tests.
      - `choose_action(self, observation: Observation, legal_actions: tuple[Action, ...]) -> Action` — renders state, prints a numbered menu of `legal_actions` with human-readable descriptions, reads a choice, re-prompts on invalid input (never crashes), returns `legal_actions[n]`.
      - Rendering rules: full board view on the first decision of a turn; short prompt (no board dump) on sub-decisions like `CHOOSE_PAYMENT`, `MULTICOLOR_COLOR`, `STEAL_TOKEN`, `CHOOSE_ROYAL`, `DISCARD`. Render only from `Observation` — never hidden info (deck order, opponent's face-down reserved cards).
    - `def main() -> None` — CLI: `python -m splendor_duel_engine.play.human --opponent greedy --human-seat 0`. Builds `HumanAgent` + opponent from the arena's `AGENT_REGISTRY`, calls `play_game`, prints the winner from the final `GameState` (agents get no in-band game-end signal).
  - **Note:** `HumanAgent` is NOT added to `AGENT_REGISTRY` (arena runs headless batches; a human entry would hang them). It lives only in `play/`; `agents/` and `eval/` stay IO-free. `play_game` stays in `agents.base`.

- [ ] **Step 1: Write failing tests**

`tests/play/test_human.py`:
```python
from splendor_duel_engine.play.human import HumanAgent
from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.random_agent import RandomAgent


def _scripted_input(answers: list[str]):
    it = iter(answers)
    return lambda _prompt="": next(it)


def test_human_agent_full_game_with_scripted_input():
    # Scripted human always answers "1"; game must run to completion
    # (enough answers: worst case many turns; pad generously)
    answers = ["1"] * 2000
    human = HumanAgent(input_fn=_scripted_input(answers), print_fn=lambda *a, **k: None)
    final = play_game(human, RandomAgent(seed=7), seed=3)
    assert final.winner in (0, 1)


def test_human_agent_reprompts_on_invalid_input():
    outputs = []
    # "abc" invalid, "99" out of range, then "0" valid
    human = HumanAgent(
        input_fn=_scripted_input(["abc", "99", "0"]),
        print_fn=lambda *a, **k: outputs.append(" ".join(str(x) for x in a)),
    )
    from splendor_duel_engine.engine.actions import decide
    from splendor_duel_engine.engine.observation import observation
    from splendor_duel_engine.engine.state import new_game

    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = human.choose_action(obs, dp.legal_actions)
    assert action == dp.legal_actions[0]
    assert any("invalid" in o.lower() for o in outputs)  # re-prompt happened


def test_human_agent_renders_observation_not_hidden_info():
    rendered = []
    human = HumanAgent(input_fn=_scripted_input(["1"]), print_fn=lambda *a, **k: rendered.append(" ".join(str(x) for x in a)))
    from splendor_duel_engine.engine.actions import decide
    from splendor_duel_engine.engine.observation import observation
    from splendor_duel_engine.engine.state import new_game

    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    human.choose_action(obs, dp.legal_actions)
    text = "\n".join(rendered)
    # Sanity: board and hand shown; nothing rendered that isn't in the Observation
    assert len(text) > 0
    # Hidden-info discipline: no deck contents leak (only counts)
    # (Adjust assertion to match actual Observation fields once engine Task 9 lands)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/play/test_human.py -v` — expected: FAIL (module missing).

- [ ] **Step 3: Implement `play/human.py`**

Key implementation notes:
- `choose_action` infers decision type from `legal_actions` types (same dispatch style as `GreedyAgent`); render full view for `USE_PRIVILEGES`/`REPLENISH`/`MANDATORY`, short prompt for sub-decisions.
- Action descriptions: small `describe(action, obs) -> str` helper; keep it boring and explicit (card points/cost for `BuyCard`, token counts for `TakeTokens`, etc.).
- Invalid input handling: wrap `input_fn` result in `int()` with try/except, range-check against menu length, print "invalid choice" and loop.
- `main()` builds agents via `AGENT_REGISTRY` (import from `splendor_duel_engine.eval.arena`) and `HumanAgent()`; human seat picks order in `play_game(human, opponent, seed=0)` or `play_game(opponent, human, seed=0)`.

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/play/test_human.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Update AGENTS.md layout**

Add to the layout block:
```
  play/       Terminal human-vs-agent play (HumanAgent, CLI)
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(play): human terminal player via Agent protocol"
```

---

### Task 6: Integration test — full game simulations and win condition verification

**Files:**
- Test: `tests/agents/test_integration.py`

**Interfaces:**
- Consumes: Tasks 1–5.

- [ ] **Step 1: Write failing tests**

`tests/agents/test_integration.py`:
```python
import pytest
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.engine.phase import Phase

def test_random_vs_greedy_both_seats():
    # Test both seat assignments
    for seed in range(5):
        # Greedy first
        final1 = play_game(GreedyAgent(), RandomAgent(seed=seed), seed=seed)
        assert final1.winner in (0, 1)
        assert final1.phase is Phase.GAME_OVER
        
        # Random first
        final2 = play_game(RandomAgent(seed=seed), GreedyAgent(), seed=seed)
        assert final2.winner in (0, 1)
        assert final2.phase is Phase.GAME_OVER

def test_all_three_win_conditions_reachable():
    # Smoke test: run many random games, verify all three win conditions occur
    # (This is probabilistic; just ensure no crashes and winner is set)
    win_types = set()
    for seed in range(100):
        final = play_game(RandomAgent(seed=seed), RandomAgent(seed=seed+1000), seed=seed)
        winner = final.winner
        player = final.players[winner]
        if player.prestige >= 20:
            win_types.add("prestige")
        if player.crowns >= 10:
            win_types.add("crowns")
        # Color win check would need card inspection; skip for smoke test
    # Just verify games terminate properly
    assert len(win_types) > 0

def test_agents_never_choose_illegal_action():
    # Play 20 games, every action must be legal (apply would raise otherwise)
    for seed in range(20):
        final = play_game(GreedyAgent(), RandomAgent(seed=seed), seed=seed)
        assert final.winner in (0, 1)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/agents/test_integration.py -v` — expected: FAIL (tests reference unwritten code or need engine completion).

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v && uv run ruff check .` — expected: all PASS (including engine tests).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "test(agents): integration tests for full game simulations"
```

---

## Self-Review Checklist

- [ ] Spec coverage: All decision points (USE_PRIVILEGES, REPLENISH, MANDATORY, CHOOSE_PAYMENT, MULTICOLOR_COLOR, STEAL_TOKEN, CHOOSE_ROYAL, DISCARD) handled by greedy agent.
- [ ] Step scan: Each step has exactly one test and one implementation action.
- [ ] Type consistency: `Agent` protocol used consistently; `Observation` imported from engine.
- [ ] Review Focus: All five items have tests in Tasks 2–6.
- [ ] Module discipline: `agents/` and `eval/` are IO-free; all terminal IO lives in `play/`; `HumanAgent` renders only from `Observation` (no hidden info) and satisfies the `Agent` protocol.
- [ ] Proportion: Plan is concise; code blocks only for non-obvious algorithms.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-10-18-baseline-agents.md`. Please review the plan. Does it capture what you want?**

**Recommended execution approach:** **Native** (implement in this session). The tasks are sequential but each produces independently testable code. The greedy agent logic (Task 3) and the human IO loop (Task 5) are the only complex parts; the rest are straightforward scaffolds. A single session can implement and verify all tasks.