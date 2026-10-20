# SDD ledger — plan: docs/superpowers/plans/2026-10-17-python-engine.md

Spec: docs/specs/splendor-duel-rules.md (read; binding authority)
Branch: feat/python-engine (repo git-initialized this session; baseline commit 47a828f)

## Todos

- [x] Task 1: Scaffolding, card data schema, card loader
- [x] Task 2: Board, state, deterministic setup
- [x] Task 3: Step API and take-tokens action
- [x] Task 4: Privileges, replenish, forced replenish
- [x] Task 5: Reserve and buy (with payment step)
- [x] Task 6: Card abilities and multicolor accounting
- [x] Task 7: Royal cards at 3rd and 6th crowns
- [ ] Task 8: End-of-turn sequence and win conditions
- [ ] Task 9: Observation API (hidden information)
- [ ] Task 10: Seeded random-play invariant fuzz harness
- [ ] Final whole-branch review

## Pre-flight conflict scan

### Pairwise (tasks sharing a file or interface)

| Pair | Producer → Consumer | Found |
|------|--------------------|-------|
| T1 → T2 | `Color`, `Tokens`, `Card`, `RoyalCard`, `load_cards` → setup/state | clean; cards.json cost keys match `Tokens` field names |
| T1 → T10 | card constants → conservation invariants | clean (67/30/24/13, 28 crowns, 92 points used consistently) |
| T2 → T3 | `GameState`, `PlayerState`, `SPIRAL`, `new_game` | **conflict-1**: T3 adds `phase`; `new_game` (T2) must set it |
| T2 → T5 | `ReservedCard(card, from_deck)` | clean; T5 wraps reservations only after T2 defines the type |
| T3 → T4 | `actions.py`, `Phase`, `decide`/`apply` | clean; T4 adds transitions, reuses `_grant_privilege` |
| T3 → T5 | `actions.py`, `BUY`, `ReserveCard`, `pending` | clean |
| T3 → T8 | simple pass-turn transition vs end-of-turn sequence | **intentional staging** (not a conflict): T8 rewires; T3's tests survive (≤10 tokens, no win) |
| T5 → T6 | `pending`, `PurchasedCard.chosen_color` | clean |
| T6 → T7 | `extra_turn`, steal/multicolor phase machinery, `pending_ability` | clean; T7 reuses |
| T7 → T8 | royal picks slot into the end-of-turn order (spec: ability → royal → discard → win) | clean |
| T8 → T9 | `winner`, `Phase.GAME_OVER` read by observation | clean |
| T9 → T10 | `Observation` unused by fuzz (fuzz uses full state) | clean |

### Per-task self-consistency

| Task | Tests vs code it specifies | Found |
|------|---------------------------|-------|
| T1 | loader tests vs `load_cards()` signature | **conflict-2**: bad-data test monkeypatches the JSON path, but the interface has no path parameter |
| T2 | setup tests vs `new_game` | clean (sizes 10/20/25, 3/4/5, 2 privileges left), except conflict-1 forward reference to `phase` |
| T3 | line-enumeration tests vs `TakeTokens` | clean; `board_state(...)` helper is to be written by the implementer (noted) |
| T4 | privilege/replenish tests vs transitions | clean; forced-replenish test constructed from T4-available actions only (take lines) |
| T5 | reserve/buy tests vs `PayTokens` | clean |
| T6 | ability tests vs resolution chain | clean |
| T7 | royal tests vs triggers | clean |
| T8 | win/discard tests vs sequence | clean |
| T9 | observation tests vs dataclasses | clean |
| T10 | fuzz tests vs driver | clean |

### Rulings on scan findings

- **Ruling (conflict-1)**: Task 3 must also update `new_game` in `state.py` to set the initial `phase` (`Phase.USE_PRIVILEGES` for the first player). Cost if wrong: a one-line fix in a later task.
- **Ruling (conflict-2)**: Task 1 implements `load_cards(path: Path | None = None)` — optional path defaulting to the packaged `cards.json` — so the bad-data test can point at a mutated copy. Cost if wrong: trivially reversible signature widening; no production caller passes a path.
- **Noted (non-ruling)**: T3's simple pass-turn transition is deliberately replaced by T8's end-of-turn sequence; T8 must keep T3–T7 tests green.

### Rulings made during execution

- **Ruling R3 (Task 1 report, concern 1 — plan defect)**: my Task 1 mandate to write `ability: "multicolor"` over the nine `bonus: "joker"` cards was lossy: `L3-01` (3 pts, cost 8 red) is multicolor **and** carries `ability: extra_turn` in the verified data, so the overwrite silently deleted a real ability. Ruling: `cards.json` reverts to the verified baseline untouched; multicolor is modelled as `Card.is_multicolor` (derived from `"bonus": "joker"`), and `Ability` keeps only the four printed abilities. Task 1 tests, plan Task 6, and spec §Card abilities updated accordingly. Cost if wrong: cosmetic — a schema field rename plus one test.
- **Ruling R4 (Task 1 report, concern 2)**: the plan's stated invariant "`bonus is None` iff multicolor" was wrong — the three colorless no-bonus cards (`L1-29`, `L2-23`, `L3-12`) also have no coloured bonus. Correct invariant: `bonus is None` ⟺ (`is_multicolor` and `bonus_count >= 1`) or (`not is_multicolor` and `bonus_count == 0`). Implementer's correction accepted verbatim.
- **Noted (Task 1 report, concern 3)**: `.gitignore` pre-existed with the required entries; `docs/` excluded from `ruff format` (prevents formatter churn on plan/spec prose). No action.

## Progress

Task 1: complete (commits 47a828f..b930b9f, review clean)
Task 1: minor (deferred): enum `str(member)` != `.value` — f-stringing a `Color`/`Ability` yields `"Color.WHITE"`. Loader is correct (uses `.value`); watch Tasks 6 and 9.
Task 1: minor (deferred): `Tokens.__add__`/`__sub__` are near-duplicated 6-line comprehensions; `__sub__` is unguarded for negatives (a `_combine` helper or a docstring note would do).
Task 1: minor (deferred): coverage — no bad-data tests for the loader's bonus/bonus_count rules or the royal-count rule; `Tokens.__add__` never exercised; nothing asserts `len(Ability) == 4` (the guard that pins Ruling R3).
Task 1: minor (deferred): unrequested but justified `[tool.ruff] extend-exclude = ["docs"]` (ruff 0.17.1 reformats markdown code fences). Kept deliberately.
Task 1: minor (deferred): the royal `(points, ability)` sort is data-fragile — safe only because exactly one royal has 3 points, so `Ability` never gets compared against `None`.
Task 1: ⚠️ from review, resolved by controller: `ruff check .` and `ruff format --check .` re-run on the final tree after `extend-exclude` landed → clean.


Task 3: complete (commits 21cec25..19e64b9, review clean)
Task 3: minor (deferred): none from review. Phase enum, step API, take-tokens line enumeration/penalty all correct and tested.

Task 4: complete (commits f9d4ff2..a627427, review clean)
Task 4: minor (deferred): `.vscode/settings.json` was committed; removed from index and added to `.gitignore` in follow-up. `_grant_privilege` type hint tightened; bag draw order documented.

Task 5: complete (commits 24e4df6..e0e8722, review clean after 1 fix round)
Task 5: minor (deferred): Payment enumeration complexity noted; win condition per-color check iterates purchased cards each time (could cache). No functional issues.

**Post-Task 5 Refactoring** (commit b2f5348): Complete refactor of actions.py per code review feedback:
- `UsePrivilege` now index-based (not color-based)
- `BuyCard` includes full Card and source
- New `CHOOSE_GOLD` phase for reserve gold selection
- `pending` → `pending_buy` + `pending_reserve`
- `_apply_take_tokens` uses `_grant_privilege`
- `_apply_replenish` uses RNG for token draw, SPIRAL order for placement
- All 64 tests pass, lint clean

Task 6: complete (commits 9f906c2..cff57d6, review clean after 2 fix rounds)
Task 6: minor (deferred): `tests/agents/test_base.py` historical deletion (agents module not yet implemented); not blocking.

Task 7: complete (commits e60143b..a553b28, review clean)
Task 7: minor (deferred): None from implementation. Royal triggers check crown thresholds (crossing 3 or 6), CHOOSE_ROYAL phase enumerates available royals, royal abilities resolved with existing machinery. All 84 tests pass including new royal tests.
