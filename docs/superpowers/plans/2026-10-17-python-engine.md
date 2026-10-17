# Python Deterministic Game Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete, deterministic, pure-Python Splendor Duel reference engine: setup, every rule, every decision point with legal-action enumeration, all three win conditions.

**Architecture:** Immutable frozen-dataclass state; every mutation is a pure `apply(state, action) -> state` returning a new state. An external loop drives turns through a step API: `decide(state) -> DecisionPoint` describes the current decision point (whose legal actions it carries), the caller chooses, `apply` advances. A `random.Random` instance lives inside `GameState` (excluded from equality); all randomness happens in `new_game` and in the future agents-stage `determinize`, never inside `apply`.

**Tech Stack:** Python 3.11+, stdlib only (no runtime deps), pytest + ruff via uv dev dependency group.

**Spec:** `docs/specs/splendor-duel-rules.md` — every task cites it. All card data in `src/splendor_duel_engine/engine/cards.json` is field-verified against the official BGA implementation; **no** edit to it is sanctioned (Ruling R3: the file stays byte-identical to baseline, and multicolor is modelled in the loader instead).

## Global Constraints

- Python 3.11+; **no new runtime dependencies** (spec + AGENTS.md: dependencies need a reason; this engine needs none).
- All state types are frozen dataclasses / NamedTuples. `apply` must never mutate its input; tests assert the input state is unchanged after `apply`.
- `GameState.rng: random.Random` is `field(compare=False, repr=False)`. Given a seed, `new_game(seed)` is byte-for-byte reproducible; `apply` is fully deterministic and never consults the RNG.
- Board indices are row-major 0–24 on a 5×5 grid. `SPIRAL = (12, 7, 8, 13, 18, 17, 16, 11, 6, 1, 2, 3, 4, 9, 14, 19, 24, 23, 22, 21, 20, 15, 10, 5, 0)` (verified against physical board art).
- Deck order convention: `decks[level][-1]` is the top card (pop from the end).
- Type hints on all public functions; ruff clean (`uv run ruff check . && uv run ruff format .`); tests pass (`uv run pytest`).
- No end-game bonus scoring, no tiebreaker, no purse (spec: verified absent).
- `cards.json` values are immutable data; **no** edit to it is sanctioned. Multicolor is modelled in the loader as `Card.is_multicolor`, derived from `"bonus": "joker"` (Ruling R3).

## Review Focus

These are the failure modes no single task naturally exercises; each is pinned to the task that owns the code.

1. **Gold lifecycle** — gold enters hands only via reserving; spent/discarded gold goes to the bag and may return to the board via replenish (spec TODO-flagged, conservation holds either way). A user would expect gold to never appear in the bag; pinned to the fuzz conservation tests in Task 10 plus the reserve→buy→replenish chain test in Task 5.
2. **Deadlock-freedom** — a mandatory action always exists (spec §Resolved ambiguities 4: bag empty ⟹ board ≥ 5 tokens ⟹ ≥ 2 non-gold ⟹ a length-1 take is legal). A user would expect `decide()` to always offer ≥1 legal action before game end; pinned to the fuzz assertion in Task 10.
3. **Multicolor double duty** — the chosen color affects both future discounts *and* the 10-points-one-color win, consistently, and copies only the bonus never an ability (spec). Pinned to Task 6's accounting tests.
4. **Hidden-info leaks** — `observation()` must not reveal opponent *deck-reserved* card identities, deck orders, or leaked hidden state; pyramid-reserved cards and bag counts are public (spec). Pinned to Task 9.
5. **Win-check timing** — checked only at end of the active player's turn, after abilities, royal picks, and discard to 10; an extra turn does not defer the check; game ends immediately with no opponent final turn (spec). Pinned to Task 8.

---

### Task 1: Scaffolding, card data schema, and card loader

**Files:**
- Modify: `pyproject.toml` (remove `[project.scripts]`, add dev group)
- Modify: none — `cards.json` is verified data and stays byte-identical; multicolor is already encoded by `bonus: "joker"` (Ruling R3)
- Create: `src/splendor_duel_engine/engine/colors.py`
- Create: `src/splendor_duel_engine/engine/cards.py`
- Test: `tests/test_cards.py`

**Interfaces:**
- Produces (consumed by every later task):
  - `class Color(enum.Enum)`: `WHITE, BLUE, GREEN, RED, BLACK, PEARL, GOLD` (str values matching cards.json keys).
  - `GEM_COLORS: tuple[Color, ...]` — the 5 gems, no pearl/gold.
  - `@dataclass(frozen=True, slots=True) class Tokens`: fields `white, blue, green, red, black, pearl, gold: int = 0`; methods `count(color: Color) -> int`, `total() -> int`, `__add__(other: Tokens) -> Tokens`, `__sub__(other: Tokens) -> Tokens`. Hashable (used in state and action types).
  - `class Ability(enum.Enum)`: `EXTRA_TURN, TAKE_MATCHING_TOKEN, STEAL_TOKEN, PRIVILEGE` (str values matching cards.json). Multicolor is deliberately **not** a member: it is orthogonal to the four printed abilities (Ruling R3).
  - `@dataclass(frozen=True, slots=True) class Card`: `id: str, level: int, points: int, crowns: int, bonus: Color | None, bonus_count: int, ability: Ability | None, is_multicolor: bool, cost: Tokens`. `bonus is None` covers both multicolor cards (`is_multicolor=True`, `bonus_count >= 1`) and colorless no-bonus cards (`is_multicolor=False`, `bonus_count == 0`).
  - `@dataclass(frozen=True, slots=True) class RoyalCard`: `id: str, points: int, ability: Ability | None`.
  - `def load_cards() -> tuple[tuple[Card, ...], tuple[RoyalCard, ...]]` — jewel cards in file order, then royals. Raises `ValueError` on any validation failure.

- [ ] **Step 1: Write failing loader tests**

`tests/test_cards.py`:

```python
def test_deck_composition():
    jewels, royals = load_cards()
    assert len(jewels) == 67                    # spec: 67 jewel cards
    assert [sum(1 for c in jewels if c.level == n) for n in (1, 2, 3)] == [30, 24, 13]
    assert sum(c.crowns for c in jewels) == 28  # spec: total crowns
    assert sum(c.points for c in jewels) == 92  # spec: total prestige

def test_multicolor_cards():
    jewels, _ = load_cards()
    multi = [c for c in jewels if c.is_multicolor]
    assert len(multi) == 9                      # spec: 9 copy-bonus cards
    assert all(c.bonus is None and c.bonus_count >= 1 for c in multi)
    # multicolor is orthogonal to abilities: L3-01 is multicolor AND extra_turn (Ruling R3)
    assert [c.id for c in multi if c.ability is not None] == ["L3-01"]
    # the colorless no-bonus cards have no colour bonus and are not multicolor
    colorless = [c for c in jewels if not c.is_multicolor and c.bonus is None]
    assert sorted(c.id for c in colorless) == ["L1-29", "L2-23", "L3-12"]
    assert all(c.bonus_count == 0 for c in colorless)

def test_royal_cards():
    _, royals = load_cards()
    assert len(royals) == 4
    assert sorted((r.points, r.ability) for r in royals) == [
        (2, Ability.EXTRA_TURN), (2, Ability.PRIVILEGE), (2, Ability.STEAL_TOKEN), (3, None)
    ]

def test_load_cards_rejects_bad_data(tmp_path, monkeypatch): ...  # monkeypatch cards.json path to a mutated copy (e.g. drop one card) and assert ValueError

def test_tokens_are_hashable_and_arithmetic():
    assert hash(Tokens(white=2, pearl=1)) is not None
    assert (Tokens(white=3) - Tokens(white=1)).white == 2
    assert Tokens(white=1).total() == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cards.py -v` — expected: FAIL (imports missing).

- [ ] **Step 3: Edit `pyproject.toml` and `cards.json`; implement `colors.py` and `cards.py`**

pyproject: delete the `[project.scripts]` section (no `main` exists); add `[dependency-groups] dev = ["pytest>=8", "ruff>=0.1"]`. `cards.json` is **not** edited: it is field-verified data and multicolor is already encoded as `bonus: "joker"` (Ruling R3); the loader maps `"joker"` → `bonus=None, is_multicolor=True`. It validates the counts in the two tests above plus "cost keys ⊆ colors ∪ {pearl}" and "id uniqueness", raising `ValueError` with the failing expectation in the message.

- [ ] **Step 4: Run tests, lint**

Run: `uv sync && uv run pytest tests/test_cards.py -v && uv run ruff check .` — expected: PASS, no lint errors.

- [ ] **Step 5: Init repo and commit**

```bash
git init && printf '.venv/\n__pycache__/\n*.egg-info/\n.pytest_cache/\n.ruff_cache/\n' > .gitignore
git add -A && git commit -m "feat: card schema, loader, and dev tooling (spec: docs/specs/splendor-duel-rules.md)"
```

---

### Task 2: Board, state, and deterministic setup

**Files:**
- Create: `src/splendor_duel_engine/engine/board.py`
- Create: `src/splendor_duel_engine/engine/state.py`
- Test: `tests/test_setup.py`

**Interfaces:**
- Consumes: Task 1 (`Color`, `Tokens`, `Card`, `RoyalCard`, `load_cards`).
- Produces:
  - `board.py`: `SPIRAL: tuple[int, ...]` (the 25-index tuple from Global Constraints); `def neighbors...` not needed yet — only `SPIRAL` is required here.
  - `state.py`:
    - `@dataclass(frozen=True, slots=True) class PurchasedCard`: `card: Card`, `chosen_color: Color | None` (Task 6 uses `chosen_color`; set `None` at purchase for now).
    - `@dataclass(frozen=True, slots=True) class ReservedCard`: `card: Card`, `from_deck: bool` (True when reserved from a deck top — hidden; False when reserved from the pyramid — public, spec §Hidden information).
    - `@dataclass(frozen=True, slots=True) class PlayerState`: `tokens: Tokens`, `bonus: Tokens`, `prestige: int`, `crowns: int`, `reserved: tuple[ReservedCard, ...]`, `purchased: tuple[PurchasedCard, ...]`, `privileges: int`.
    - `@dataclass(frozen=True, slots=True) class GameState`: `players: tuple[PlayerState, PlayerState]`, `board: tuple[Color | None, ...]` (25 entries, row-major), `bag: Tokens`, `decks: tuple[tuple[Card, ...], tuple[Card, ...], tuple[Card, ...]]`, `pyramid: tuple[tuple[Card | None, ...], ...]` (rows of 3, 4, 5 for levels 3, 2, 1), `royals_available: tuple[RoyalCard, ...]`, `privileges_supply: int`, `current_player: int`, `winner: int | None`, `rng: random.Random` (`field(compare=False, repr=False)`).
    - `def new_game(seed: int) -> GameState` — full setup per spec.

- [ ] **Step 1: Write failing setup tests**

`tests/test_setup.py`:

```python
def test_setup_matches_spec():
    st = new_game(seed=0)
    assert st.board[12] is not None and all(c is not None for c in st.board)  # board full (25 tokens)
    assert st.bag.total() == 0                    # spec: all 25 tokens on board, bag empty
    assert [len(d) for d in st.decks] == [10, 20, 25]   # 13/24/30 minus pyramid 3/4/5
    assert [sum(1 for c in row if c is not None) for row in st.pyramid] == [3, 4, 5]
    assert len(st.royals_available) == 4
    assert st.privileges_supply == 2              # 3 minus 1 given to second player
    assert st.players[st.current_player].privileges == 0
    assert st.players[1 - st.current_player].privileges == 1

def test_token_census_on_board():
    st = new_game(seed=0)
    from collections import Counter
    census = Counter(st.board)
    assert census[Color.GOLD] == 3 and census[Color.PEARL] == 2
    assert all(census[c] == 4 for c in GEM_COLORS)

def test_setup_is_deterministic_given_seed():
    a, b = new_game(seed=42), new_game(seed=42)
    assert a == b
    assert a.board == b.board and a.decks == b.decks
    assert new_game(seed=43).board != a.board  # different seed shuffles differently (extremely likely)

def test_first_player_is_random_but_reproducible():
    assert new_game(seed=1).current_player == new_game(seed=1).current_player
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_setup.py -v` — expected: FAIL (modules missing).

- [ ] **Step 3: Implement `SPIRAL` and `new_game`**

`new_game(seed)`: build `rng = random.Random(seed)`; shuffle each deck; deal pyramid (levels 3/2/5 rows: 3 level-3, 4 level-2, 5 level-1); place the 25 shuffled tokens onto the board in `SPIRAL` order (spec setup); first player `rng.randrange(2)`; second player gets 1 privilege. Keep the card tuples immutable (shuffle a list, convert to tuple).

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/test_setup.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: deterministic game setup (spec: setup section)"
```

---

### Task 3: Step API and the take-tokens action

**Files:**
- Modify: `src/splendor_duel_engine/engine/state.py` (add `phase`, `pending`)
- Create: `src/splendor_duel_engine/engine/actions.py`
- Test: `tests/test_take_tokens.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces (consumed by Tasks 4–10):
  - `class Phase(enum.Enum)`: `USE_PRIVILEGES, REPLENISH, MANDATORY, CHOOSE_PAYMENT, MULTICOLOR_COLOR, STEAL_TOKEN, CHOOSE_ROYAL, DISCARD, GAME_OVER`. (Tasks 4–8 add transitions into the phases; Task 3 only uses `MANDATORY` and `GAME_OVER`.)
  - Action dataclasses (all frozen): `UsePrivilege(color: Color)`, `DoneWithPrivileges()`, `Replenish()`, `DoneWithReplenish()`, `TakeTokens(line: tuple[int, ...])`, `BuyCard(card_id: str)`, `PayTokens(payment: Tokens)`, `ReserveCard(source: str, index: int)` (`"pyramid"` or `"deck"` + row/slot or level), `ChooseMulticolor(color: Color)`, `ChooseStealToken(color: Color)`, `ChooseRoyal(royal_id: str)`, `DiscardTokens(tokens: Tokens)`.
  - `@dataclass(frozen=True, slots=True) class DecisionPoint`: `phase: Phase`, `legal_actions: tuple[Action, ...]`. The legal-actions tuple *is* the mask source (AGENTS.md); every decision point enumerates it exhaustively.
  - `def decide(state: GameState) -> DecisionPoint` — raises `ValueError` if `state.winner is not None`.
  - `def apply(state: GameState, action: Action) -> GameState` — raises `ValueError` if the action is not in `decide(state).legal_actions`.
  - `GameState` gains: `phase: Phase`, `pending: Card | None` (card awaiting payment, Task 5; `None` otherwise).
- Note: royal acquisition, discard, abilities, and win checks do not exist yet; `apply` on `MANDATORY` performs the action and returns to `USE_PRIVILEGES` for the next player (Tasks 6–8 refine the end-of-turn sequence).

- [ ] **Step 1: Write failing tests**

`tests/test_take_tokens.py`:

```python
def take_first_legal(st):  # helper reused across tasks 3-4
    from splendor_duel_engine.engine.actions import apply, decide
    dp = decide(st)
    assert len(dp.legal_actions) > 0
    return apply(st, dp.legal_actions[0])

def test_legal_lines_are_contiguous_straight_length_1_to_3():
    # hand-build a GameState (via dataclasses.replace on new_game) with a known board:
    # row 0: [RED, RED, RED, GOLD, None...], rest empty/bag full
    st = board_state(...)
    dp = decide(st)
    lines = {a.line for a in dp.legal_actions if isinstance(a, TakeTokens)}
    assert (0,) in lines and (0, 1) in lines and (0, 1, 2) in lines
    assert (0, 1, 2, 3) not in lines                 # length cap 3
    assert (0, 2) not in lines                       # not contiguous
    assert (1, 5) not in lines                       # adjacent but horizontal-vs-vertical turn, not straight
    assert all(Color.GOLD not in (st.board[i] for i in ln) for ln in lines)  # gold blocks and is untakeable

def test_diagonal_lines_legal():
    # board with tokens at 0, 7, 14 (main diagonal) -> assert (0, 7, 14) in lines

def test_take_removes_tokens_and_applies_penalty():
    # 3 same-color line -> opponent gains 1 privilege (spec: penalty)
    st = apply(st, TakeTokens((0, 1, 2)))            # three REDs
    assert st.board[0] is None
    assert st.players[1].tokens.red == 3
    assert st.players[1].privileges == old + 1

def test_two_pearl_take_penalizes():
    # board with both pearls adjacent -> TakeTokens of the 2-pearl line -> opponent +1 privilege (spec)

def test_two_same_color_no_penalty():
    # line of exactly 2 same-color gems -> no privilege transfer (spec: only 3-same or 2-pearl penalize)

def test_apply_rejects_illegal_action():
    with pytest.raises(ValueError): apply(st, TakeTokens((0, 2)))   # non-contiguous

def test_apply_does_not_mutate_input():
    before = st
    apply(st, TakeTokens((0,)))
    assert st == before
```

(Adjust the diagonal assertion to a genuinely diagonal pair, e.g. `(0, 6)` is vertical-adjacent on row-major 5-wide — use indices 0, 7, 14 for the main diagonal. The implementer writes these boards via a small helper that replaces `board`/`bag` on `new_game(0)` with `dataclasses.replace`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_take_tokens.py -v` — expected: FAIL (no `actions` module).

- [ ] **Step 3: Implement `actions.py` line enumeration and `TakeTokens`**

Enumererate all contiguous straight segments of length 1–3 over the 8 directions whose cells are all non-`None` and non-gold. `decide` in `MANDATORY` phase returns all take-token lines plus (later tasks) buy/reserve actions. `apply(TakeTokens)`: remove tokens, add to active player, apply penalty (opponent +1 privilege from supply, else stolen from the taker — spec) when the taken set is 3-of-one-color or contains both pearls; then `replace` state with the next player's `USE_PRIVILEGES` turn (no win check yet — Task 8).

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/test_take_tokens.py -v && uv run ruff check .` — expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: step API and take-tokens action with penalty (spec: action A)"
```

---

### Task 4: Privileges, replenish, and forced replenish

**Files:**
- Modify: `src/splendor_duel_engine/engine/actions.py`
- Test: `tests/test_privileges_replenish.py`

**Interfaces:**
- Consumes: Task 3 (`decide`, `apply`, `Phase`, action types).
- Produces: turn-opening sequence in `decide`: `USE_PRIVILEGES` → (optional) `REPLENISH` → `MANDATORY`. Forced replenish per spec: when `MANDATORY` would have zero legal actions and the bag is non-empty, `decide` returns the `REPLENISH` phase with only `Replenish` legal.

- [ ] **Step 1: Write failing tests**

`tests/test_privileges_replenish.py`:

```python
def test_use_privilege_takes_one_chosen_non_gold_board_token():
    st = ...  # player holds 1 privilege
    dp = decide(st)
    assert dp.phase is Phase.USE_PRIVILEGES
    take = next(a for a in dp.legal_actions if isinstance(a, UsePrivilege))
    assert Color.GOLD not in {a.color for a in dp.legal_actions if isinstance(a, UsePrivilege)}
    st2 = apply(st, take)
    assert st2.players[st.current_player].privileges == 0
    # chosen token moved board -> hand

def test_multiple_privileges_used_one_at_a_time():
    # player with 2 privileges: UsePrivilege twice, then DoneWithPrivileges

def test_done_with_privileges_advances_to_replenish():
    # bag non-empty -> REPLENISH phase with Replenish and DoneWithReplenish both legal

def test_replenish_fills_from_bag_along_spiral_and_grants_opponent_privilege():
    # board with 3 empty slots, bag with 3 tokens
    st2 = apply(st, Replenish())
    filled = [i for i in SPIRAL if st.board[i] is None][:3]   # first empties along spiral (center-out)
    assert all(st2.board[i] is not None for i in filled)
    assert st2.bag.total() == 0
    assert st2.players[1 - st.current_player].privileges == old + 1  # spec: opponent takes 1

def test_replenish_illegal_when_bag_empty():
    dp = decide(state_with_empty_bag)
    assert not any(isinstance(a, Replenish) for a in dp.legal_actions)

def test_forced_replenish_when_no_mandatory_action():
    # construct: nothing affordable, no gold on board, bag non-empty, board almost empty
    st2 = decide(st)
    assert st2.phase is Phase.REPLENISH
    assert [type(a) for a in st2.legal_actions] == [Replenish]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_privileges_replenish.py -v` — expected: FAIL (no such phases/transitions).

- [ ] **Step 3: Implement privilege and replenish transitions**

Wire the `USE_PRIVILEGES` and `REPLENISH` phases into `decide`/`apply`. Replenish draws from the bag onto empty spaces in `SPIRAL` order until the bag is empty or the board is full, then grants the opponent 1 privilege (from supply, else stolen from the replenisher — same privilege-acquisition helper as Task 3's penalty; factor it into `_grant_privilege(players, recipient) -> players`). Forced-replenish: in `MANDATORY`, compute the legal mandatory actions (take lines for now); if empty and `bag.total() > 0`, return `REPLENISH` with only `Replenish`.

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest tests/test_privileges_replenish.py tests/test_take_tokens.py -v && uv run ruff check .` — expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: privilege usage, replenish, forced replenish (spec: turn structure)"
```

---

### Task 5: Reserve and buy (with payment step)

**Files:**
- Modify: `src/splendor_duel_engine/engine/actions.py`
- Test: `tests/test_reserve.py`, `tests/test_buy.py`

**Interfaces:**
- Consumes: Tasks 3–4.
- Produces:
  - `MANDATORY` now also enumerates `BuyCard(card_id)` (affordable cards from own reserved + pyramid) and `ReserveCard(source, index)`.
  - New phase `CHOOSE_PAYMENT`: `BuyCard` sets `pending` to the chosen card; `decide` then enumerates `PayTokens(payment)` for every legal payment. A payment is legal iff, after subtracting per-gem bonuses (`min 0` per color, pearls never reduced), the remaining cost is covered by the payment's gold count. Gold is wild: `PayTokens` is validated against all possible gold assignments.
  - Pyramid purchase refills the slot from that deck (if any); reserve takes gold from the board *first* (only gold source), then a pyramid card (slot refills) or a deck top card (no refill). Multicolor purchase *restriction* is enforced here (cannot buy without an owned colored bonus); the chosen-color decision arrives in Task 6.

- [ ] **Step 1: Write failing tests**

`tests/test_reserve.py`:

```python
def test_reserve_requires_gold_on_board(): ...        # no gold -> ReserveCard not in legal actions
def test_reserve_takes_gold_then_pyramid_card_and_refills(): ...
def test_reserve_from_deck_top_does_not_refill(): ...
def test_reserve_illegal_at_three_reserved(): ...
def test_reserved_cards_are_in_own_player_state_and_turn_passes(): ...
def test_multicolor_may_be_reserved_without_owning_bonus(): ...  # spec: restriction applies at purchase only
```

`tests/test_buy.py`:

```python
def test_payment_respects_bonuses_and_never_goes_below_zero(): ...
def test_pearl_cost_never_reduced(): ...
def test_gold_pays_as_any_color_or_pearl(): ...
def test_pyramid_purchase_refills_from_deck_or_stays_empty_when_deck_empty(): ...
def test_reserved_purchase_does_not_refill(): ...
def test_spent_tokens_go_to_bag(): ...               # spec: hand -> bag, including gold
def test_buy_grants_bonus_prestige_crowns(): ...
def test_multicolor_cannot_be_bought_without_colored_bonus(): ...  # spec
def test_choose_payment_phase_offers_only_legal_payments():
    # assert every offered PayTokens satisfies the above; assert at least one exists for an affordable card
def test_reserve_buy_chain_gold_reaches_bag_and_board_refill_can_redeploy_it():
    # Review Focus 1: reserve (gold to hand) -> buy with gold -> gold in bag -> replenish -> gold back on board
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_reserve.py tests/test_buy.py -v` — expected: FAIL.

- [ ] **Step 3: Implement reserve, buy, and the payment decision point**

Add buyable-card enumeration (own reserved + pyramid; affordability = `cost - bonus` per gem color covered by hand incl. wild gold; multicolor requires an owned colored bonus). `ReserveCard`: validate gold-on-board and `< 3` reserved, take gold from board, take the card, wrap it in `ReservedCard(card, from_deck=<source is a deck top>)`, refill the pyramid slot if source was the pyramid. `PayTokens`: validate as described, move spent tokens to the bag, hand the card to `purchased` (`PurchasedCard(card, chosen_color=None)`), add bonus/prestige/crowns, refill pyramid slot on pyramid buys, then return to `USE_PRIVILEGES` with the player unchanged (Task 6 inserts ability resolution here).

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest -v && uv run ruff check .` — expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: reserve and buy with payment decision point (spec: actions B, C)"
```

---

### Task 6: Card abilities and multicolor accounting

**Files:**
- Modify: `src/splendor_duel_engine/engine/actions.py`, `src/splendor_duel_engine/engine/state.py` (add `extra_turn: bool` to `GameState`, default `False`)
- Test: `tests/test_abilities.py`

**Interfaces:**
- Consumes: Tasks 3–5.
- Produces: after a purchase, ability resolution runs before the turn passes:
  - `EXTRA_TURN`: set `extra_turn=True`; at turn end the same player starts again (cleared on use). Royal `EXTRA_TURN` (Task 7) sets the same flag.
  - `TAKE_MATCHING_TOKEN`: auto-take 1 board token of the card's bonus color if present (no decision point; ignored otherwise — spec).
  - `PRIVILEGE`: `_grant_privilege` on the buyer.
  - `STEAL_TOKEN`: new phase `STEAL_TOKEN` enumerating `ChooseStealToken(color)` for each non-gold token color the opponent holds; gold immune (spec).
  - `is_multicolor` (a card property, not an `Ability`; Ruling R3): new phase `MULTICOLOR_COLOR` enumerating `ChooseMulticolor(color)` for each color with `bonus.count(color) > 0`; sets `PurchasedCard.chosen_color`, which adds `bonus_count` of that color to the buyer's bonus and makes the card's prestige count toward that color's 10-point total (Task 8 win check reads `chosen_color`).

- [ ] **Step 1: Write failing tests**

`tests/test_abilities.py`:

```python
def test_extra_turn_same_player_plays_again(): ...
def test_take_matching_token_auto_taken_or_ignored_when_absent(): ...
def test_privilege_ability_grants_privilege(): ...
def test_steal_takes_chosen_non_gold_opponent_token_and_cannot_steal_gold(): ...
def test_steal_ignored_when_opponent_has_no_tokens(): ...
def test_multicolor_choose_color_adds_bonus_and_counts_for_that_color():
    # after ChooseMulticolor(RED): buyer bonus.red += card.bonus_count; card prestige counts toward RED (Task 8 reads this)
def test_multicolor_copies_only_bonus_not_ability():
    # multicolor copies the bonus, never an ability: a multicolor-only card fires no
    # extra ability, while L3-01 (multicolor + extra_turn) still plays again (Ruling R3)
def test_bought_card_ability_resolves_before_next_player_turns(): ...
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_abilities.py -v` — expected: FAIL.

- [ ] **Step 3: Implement ability resolution chain**

After `PayTokens` succeeds: resolve abilities in a fixed order — multicolor colour choice (if `card.is_multicolor`; decision point) / `STEAL_TOKEN` (decision point) / `TAKE_MATCHING_TOKEN` / `PRIVILEGE` (immediate) / `EXTRA_TURN` (flag) — then return to `USE_PRIVILEGES`. If a decision point phase is entered, store enough in `pending`/a new `pending_ability` field (add `pending_ability: Ability | None` to `GameState`) to resume after the choice. On `extra_turn`, the end-of-turn transition (still the simple one from Task 3) keeps `current_player` and clears the flag; otherwise advance the seat.

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest -v && uv run ruff check .` — expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: four card abilities plus multicolor chosen-color accounting (spec: abilities)"
```

---

### Task 7: Royal cards at 3rd and 6th crowns

**Files:**
- Modify: `src/splendor_duel_engine/engine/actions.py`
- Test: `tests/test_royals.py`

**Interfaces:**
- Consumes: Tasks 3–6.
- Produces: after a purchase (and after a royal's own ability? no — royals are picked during the end-of-turn sequence starting Task 8; for now, on crowns crossing 3 or 6) enter `CHOOSE_ROYAL` enumerating `ChooseRoyal(royal_id)` over `royals_available` (empty tuple ⇒ phase skipped, nothing happens — spec "take 1 available royal"). Taking a royal: remove from `royals_available`, add to player, resolve its ability immediately (`STEAL_TOKEN`/`EXTRA_TURN`/`PRIVILEGE` reuse Task 6 machinery; the 3-point royal has none). Royals add prestige but no crowns and no color bonus.

- [ ] **Step 1: Write failing tests**

`tests/test_royals.py`:

```python
def test_third_crown_grants_royal_choice(): ...
def test_sixth_crown_grants_second_royal(): ...
def test_max_two_royals_per_player(): ...      # 9-crown... no 9-crown trigger exists; assert crossing 6 from <6 grants exactly one more
def test_royal_ability_resolves(): ...          # e.g. steal royal -> STEAL_TOKEN phase
def test_royal_gives_prestige_but_neither_crown_nor_bonus(): ...
def test_no_royal_available_skips_choice(): ...
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_royals.py -v` — expected: FAIL.

- [ ] **Step 3: Implement royal triggers**

Track crowns before/after the purchase; for each threshold in `(3, 6)` crossed, enter `CHOOSE_ROYAL`. `ChooseRoyal` applies the royal and its ability, then resumes.

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest -v && uv run ruff check .` — expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: royal card acquisition and abilities (spec: royal cards)"
```

---

### Task 8: End-of-turn sequence and win conditions

**Files:**
- Modify: `src/splendor_duel_engine/engine/actions.py`
- Test: `tests/test_win_conditions.py`, `tests/test_discard.py`

**Interfaces:**
- Consumes: Tasks 3–7.
- Produces: the spec's end-of-turn order as phases after a mandatory purchase — abilities (Task 6) → royal picks (Task 7) → `DISCARD` if `tokens.total() > 10` (enumerate `DiscardTokens(t)` for every subset summing to the excess, any colors incl. gold; excess goes to the bag) → win check → next player or extra turn. Win check (spec, exact): `prestige >= 20` OR `crowns >= 10` OR `sum of prestige of purchased cards whose effective color == c` `>= 10` for some gem color `c` (effective color = `chosen_color` for multicolor, `bonus` otherwise; colorless/gray and royal cards count toward no color). On win: `winner = current_player`, `phase = GAME_OVER`, `decide` raises thereafter. No bonus scoring, no tiebreaker, immediate end.

- [ ] **Step 1: Write failing tests**

`tests/test_win_conditions.py` (AGENTS.md: test all three):

```python
def test_win_at_20_prestige_checked_only_at_end_of_own_turn():
    # player at 19 prestige buys a 1-point card mid-turn while holding >10 tokens: no win yet
def test_win_at_10_crowns(): ...
def test_win_at_10_points_in_one_color():
    # includes a multicolor card whose chosen_color pushes the total to 10 (Review Focus 3)
def test_royal_and_colorless_cards_do_not_count_for_color_win_but_do_for_20(): ...
def test_game_ends_immediately_no_opponent_final_turn(): ...
def test_extra_turn_does_not_defer_win_check(): ...
def test_no_endgame_bonus_scoring(): ...   # reaching 20 with pearls/privileges left over adds nothing
```

`tests/test_discard.py`:

```python
def test_discard_required_when_over_ten_after_ability_grant(): ...
def test_discard_subset_sum_equals_excess_and_tokens_reach_bag(): ...
def test_under_ten_no_discard_phase(): ...
def test_mid_turn_gain_over_ten_is_fine_until_end_of_turn(): ...  # spec: no purse, end-of-turn check only
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_win_conditions.py tests/test_discard.py -v` — expected: FAIL.

- [ ] **Step 3: Implement end-of-turn sequence and win check**

Reorder the post-mandatory transition to: abilities → royals → discard (if needed) → win check → seat advance or extra turn. The win check is a small pure helper `def winner_of(state: GameState) -> int | None`. `TAKE_TOKENS`-only turns also pass through discard + win check (taking tokens can exceed 10).

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest -v && uv run ruff check .` — expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: end-of-turn sequence and all three win conditions (spec: victory)"
```

---

### Task 9: Observation API (hidden information)

**Files:**
- Create: `src/splendor_duel_engine/engine/observation.py`
- Test: `tests/test_observation.py`

**Interfaces:**
- Consumes: Tasks 1–8.
- Produces:
  - `@dataclass(frozen=True, slots=True) class PlayerView`: everything public about a player — `tokens: Tokens`, `bonus: Tokens`, `prestige: int`, `crowns: int`, `reserved_public: tuple[Card, ...]` (that player's pyramid-reserved cards — public), `reserved_deck_count: int` (how many deck-reserved cards they hold — the identities stay hidden), `purchased: tuple[PurchasedCard, ...]`, `privileges: int`.
  - `@dataclass(frozen=True, slots=True) class Observation`: `you: PlayerView`, `opponent: PlayerView`, `board: tuple[Color | None, ...]`, `pyramid`, `royals_available: tuple[RoyalCard, ...]`, `privileges_supply: int`, `deck_counts: tuple[int, int, int]`, `bag: Tokens` (public by deduction, spec), `current_player: int`, `winner: int | None`, `your_reserved_deck: tuple[Card, ...]` (the viewer's own hidden reservations, `from_deck=True`).
  - `def observation(state: GameState, player: int) -> Observation`.

- [ ] **Step 1: Write failing tests**

`tests/test_observation.py`:

```python
def test_own_deck_reserved_visible_to_self_only():
    # player 0 reserves from a deck top; observation(st, 0).your_reserved_deck contains it;
    # observation(st, 1) contains that Card identity nowhere (Review Focus 4)

def test_pyramid_reserved_is_public():
    # player 1 reserves a specific pyramid card;
    # assert that Card id appears in observation(st, 0).opponent.reserved_public

def test_deck_reserved_identity_hidden_from_opponent():
    # player 1 reserves from a deck top;
    # assert observation(st, 0).opponent.reserved_deck_count == 1
    # and the card's id appears nowhere in observation(st, 0)

def test_deck_order_hidden_but_counts_and_bag_visible():
    obs = observation(st, 0)
    assert obs.deck_counts == tuple(len(d) for d in st.decks)   # counts only, spec
    assert obs.bag == st.bag                                    # bag is public by deduction, spec

def test_public_info_matches_state(): ...
def test_observation_is_immutable(): ...
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_observation.py -v` — expected: FAIL.

- [ ] **Step 3: Implement `observation`**

Project the state: public info verbatim (board, pyramid, royals, privileges, hands, purchases, the bag, and pyramid-reserved cards); hidden info reduced — deck-reserved identities appear only in the viewer's own `your_reserved_deck`, and deck order is never exposed (only counts). Build the dataclasses so an opponent's deck-reserved card *cannot* be represented: `PlayerView.reserved_public` carries only `from_deck=False` cards.

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest -v && uv run ruff check .` — expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: observation API with explicit hidden info (spec: hidden information)"
```

---

### Task 10: Seeded random-play invariant fuzz harness

**Files:**
- Create: `tests/fuzz_helpers.py` (or a `conftest.py` fixture)
- Test: `tests/test_fuzz_invariants.py`

**Interfaces:**
- Consumes: Tasks 1–9 (`decide`, `apply`, `new_game`, `observation`).
- Produces: a reusable `play_random_game(seed: int) -> GameState` driver that plays a full game by taking a uniformly random legal action at each `decide()` (games are finite because every mandatory action either removes board tokens or moves toward a purchase... if a runaway is detected, bias toward `TakeTokens`; document the choice), asserting invariants at every ply.

- [ ] **Step 1: Write failing fuzz tests**

`tests/test_fuzz_invariants.py`:

```python
SEEDS = range(50)

@pytest.mark.parametrize("seed", SEEDS)
def test_invariants_hold_through_random_play(seed):
    st = new_game(seed)
    # after every apply:
    # 1. token conservation: board + bag + both hands == 25 tokens, and gold total == 3 (spec census)
    # 2. card conservation: decks + pyramid + reserved + purchased == 67 jewels, ids unique across all
    # 3. 0 <= privileges_supply + p0.privileges + p1.privileges <= 3
    # 4. decide() returns >= 1 legal action unless winner is not None  (Review Focus 2: no deadlock)
    # 5. state.rng not consulted by apply: replay the same action sequence on a clone -> identical states

@pytest.mark.parametrize("seed", SEEDS)
def test_random_games_terminate_with_exactly_one_winner(seed):
    st = play_random_game(seed)
    assert st.winner in (0, 1)
    assert st.phase is Phase.GAME_OVER
    # winner satisfies one of the three conditions (recheck independently of winner_of)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_fuzz_invariants.py -v` — expected: FAIL (harness missing).

- [ ] **Step 3: Implement `play_random_game` and invariant assertions**

Driver as described; invariants as a helper `assert_invariants(st)` so later Rust fuzzing can import the same predicates. If invariant 4 trips, that is a real deadlock bug — fix the engine, do not weaken the assertion.

- [ ] **Step 4: Run tests, lint**

Run: `uv run pytest -v && uv run ruff check .` — expected: all PASS, including all prior tasks.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: seeded random-play invariant fuzz harness"
```
