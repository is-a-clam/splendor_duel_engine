# Implementation Plan: Actions.py Refactoring (Post-Task 5 Fixes)

This document describes the necessary refactoring of `actions.py` based on code review feedback after Task 5 completion. These changes should be applied before or during Task 6.

## Summary of Changes

| # | Change | Files Affected |
|---|--------|----------------|
| 1 | Refactor `_apply_take_tokens` to use `_grant_privilege` | `actions.py` |
| 2 | Change `UsePrivilege` action from color-based to index-based | `actions.py`, `phase.py` (no), tests |
| 3 | Make `_apply_replenish` use RNG for random placement, empty bag | `actions.py` |
| 4 | Add `CHOOSE_GOLD` phase for reserve gold selection | `actions.py`, `phase.py`, tests |
| 5 | Update `BuyCard` to include `Card` and `source` | `actions.py`, tests |
| 6 | Store full `BuyCard` action in `pending` instead of just `Card` | `actions.py`, `state.py` |
| 7 | Multicolor bonus grant (deferred to Task 6) | `actions.py` (Task 6) |

---

## Detailed Changes

### 1. Refactor `_apply_take_tokens` to use `_grant_privilege`

**Current problem**: Lines 507-538 in `_apply_take_tokens` duplicate the privilege-granting logic that exists in `_grant_privilege`.

**Fix**: After determining a penalty applies, call `_grant_privilege(players, opp, privileges_supply)` to get the updated players and supply. This matches how `_apply_replenish` already does it.

```python
# In _apply_take_tokens, replace lines 519-538 with:
if penalty:
    new_players, new_priv_supply = _grant_privilege(
        tuple(new_players_list), opp, state.privileges_supply
    )
    new_players_list = list(new_players)
else:
    new_priv_supply = state.privileges_supply
```

---

### 2. Change `UsePrivilege` to Index-Based Selection

**Current**: `UsePrivilege(color: Color)` - player chooses a color, engine picks first token of that color.

**New**: `UsePrivilege(index: int)` - player chooses exact board index.

**Changes**:
- `UsePrivilege` dataclass: change `color: Color` to `index: int`
- `_apply_use_privilege(state, index)`: validate index has non-gold token, take it
- `decide` in `USE_PRIVILEGES`: enumerate all board indices where `board[i] is not None and board[i] != Color.GOLD` (not distinct colors)

**Rationale**: Gives the player full control over which specific token to take.

---

### 3. Make Replenish Random Using RNG

**Current**: Fills empty slots along SPIRAL order using fixed color order (WHITE, BLUE, GREEN, RED, BLACK, PEARL, GOLD).

**New**: 
- Collect all tokens from bag into a list
- Shuffle the list using `state.rng`
- Collect all empty board indices **in SPIRAL order** (not shuffled)
- Place tokens from shuffled list onto empty slots in SPIRAL order (up to min(len(tokens), len(empty_slots)))
- Bag becomes empty (all tokens placed since total = 25)

**Note**: Since total tokens = 25 and board size = 25, after replenish the bag should always be empty. The current code tries to handle partial fills but that's impossible by conservation.

---

### 4. Add CHOOSE_GOLD Phase for Reserve

**Current**: `_apply_reserve_card` automatically takes the first gold token found.

**New Flow**:
1. `ReserveCard` action executed in `MANDATORY` → sets `pending_reserve = ReserveCard(...)` and enters `CHOOSE_GOLD` phase
2. `decide` in `CHOOSE_GOLD`: enumerate all board indices with gold tokens → `ChooseGold(index)` actions
3. `ChooseGold(index)` executed → takes that gold, completes the reserve (moves card to reserved, refills pyramid if needed), advances to `USE_PRIVILEGES` for opponent

**New Types**:
```python
@dataclass(frozen=True, slots=True)
class ChooseGold:
    index: int

# Add to Phase enum:
CHOOSE_GOLD = "choose_gold"

# Add to GameState:
pending_reserve: ReserveCard | None = None
```

**ReserveCard source format**: Keep as-is (`"pyramid"` with encoded row/col, or `"deck_3"`/`"deck_2"`/`"deck_1"`).

---

### 5. Update BuyCard Action to Include Card and Source

**Current**: `BuyCard(card_id: str)` - requires searching in `_apply_buy_card` and `_apply_pay_tokens`.

**New**: `BuyCard(card: Card, source: str)` where source is `"reserved"` or `"pyramid_r_c"` (e.g., `"pyramid_0_2"`).

**Changes**:
- `BuyCard` dataclass: add `card: Card`, `source: str` fields
- `_get_buyable_cards` returns `list[BuyCard]` instead of `list[tuple[str, Card, str]]`
- `decide` in `MANDATORY`: add `BuyCard` actions directly
- `_apply_buy_card`: no search needed, just set `pending_buy = action` (the BuyCard)
- `_apply_pay_tokens`: get card and source from `pending_buy`

---

### 6. Store Full BuyCard in Pending

**Current**: `pending: Card | None` - only stores the Card.

**New**: `pending_buy: BuyCard | None` - stores the full action with card and source.

**Changes in `state.py`**:
- Change `pending: Card | None` to `pending_buy: BuyCard | None`
- Add `pending_reserve: ReserveCard | None` for the CHOOSE_GOLD phase

**Rationale**: Eliminates redundant searches, makes code cleaner and less error-prone.

---

### 7. Multicolor Bonus (Task 6)

**Current**: Multicolor cards grant no bonus (line 734 skips bonus for `bonus=None`).

**Task 6 Fix**: When `ChooseMulticolor(color)` is resolved:
- Set `PurchasedCard.chosen_color = color`
- Add `bonus_count` of that color to player's bonus
- The win check in `_apply_pay_tokens` already reads `chosen_color` for color points

---

## Updated Phase Enum (phase.py)

```python
class Phase(enum.Enum):
    USE_PRIVILEGES = "use_privileges"
    REPLENISH = "replenish"
    MANDATORY = "mandatory"
    CHOOSE_PAYMENT = "choose_payment"
    CHOOSE_GOLD = "choose_gold"           # NEW
    MULTICOLOR_COLOR = "multicolor_color"
    STEAL_TOKEN = "steal_token"
    CHOOSE_ROYAL = "choose_royal"
    DISCARD = "discard"
    GAME_OVER = "game_over"
```

---

## Updated GameState Fields (state.py)

```python
@dataclass(frozen=True, slots=True)
class GameState:
    # ... existing fields ...
    pending_buy: BuyCard | None = None      # REPLACES pending: Card | None
    pending_reserve: ReserveCard | None = None  # NEW for CHOOSE_GOLD
    rng: random.Random = field(compare=False, repr=False)
```

---

## Test Updates Required

All tests that construct `UsePrivilege`, `BuyCard`, `ReserveCard` actions need updates. Specifically:

- `test_privileges_replenish.py`: `UsePrivilege` now takes index
- `test_reserve.py`: New CHOOSE_GOLD phase flow
- `test_buy.py`: `BuyCard` includes card and source
- `test_take_tokens.py`: No changes (TakeTokens unchanged)
- New test file for CHOOSE_GOLD phase

---

## Order of Implementation

1. **Phase enum + GameState changes** (`phase.py`, `state.py`)
2. **Action type changes** (`UsePrivilege`, `BuyCard`, add `ChooseGold`) in `actions.py`
3. **Refactor `_apply_take_tokens`** to use `_grant_privilege`
4. **Rewrite `_apply_replenish`** with RNG
5. **Rewrite reserve flow** with CHOOSE_GOLD phase
6. **Rewrite buy flow** with BuyCard in pending
7. **Update decide/apply** for new phases
8. **Update all tests**
9. **Run full test suite**

---

## Notes on Determinism

- All RNG usage must go through `state.rng` 
- Replenish: shuffle tokens list AND shuffle empty indices for true randomness
- CHOOSE_GOLD: player chooses index, no RNG needed
- The RNG stream must remain reproducible for fuzzing (Task 10)