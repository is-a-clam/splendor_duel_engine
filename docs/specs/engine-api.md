# Engine Helper API

This document is the contract for the engine's public helper API — the free
rule-query functions in `splendor_duel_engine.engine.helpers`. It is the
contract the Rust port (`engine_rs/`) mirrors: the Rust crate must produce the
same answers, in the same order, for the same inputs. Every helper here answers
**"what does the rule say"** and never **"what is good"**: there is no
heuristic, no preference, and no evaluation of a position anywhere in this
module. The helpers are free functions over state *fragments* (a hand, a
board, a pyramid), not over a whole `GameState`, so a caller can ask about a
hypothetical hand without constructing a game.

The authoritative rules live in [`splendor-duel-rules.md`](splendor-duel-rules.md);
section references below point at it.

## Constants

| Constant | Value | Rule it encodes |
| --- | --- | --- |
| `TOKEN_LIMIT` | `10` | A player may hold at most 10 tokens at the end of their turn; the excess goes to the bag (§End of turn and victory). |
| `MAX_RESERVED` | `3` | A player may hold at most 3 reserved cards (§Privileges). |
| `PRESTIGE_WIN` | `20` | A player wins by reaching 20 prestige points (§End of turn and victory). |
| `CROWNS_WIN` | `10` | A player wins by reaching 10 crowns (§End of turn and victory). |
| `COLOR_WIN_POINTS` | `10` | A player wins by holding 10 prestige points in a single gem colour (§End of turn and victory). |

## Helpers

### `cost_deficits`

```python
def cost_deficits(cost: Tokens, bonus: Tokens, paid: Tokens) -> dict[Color, int]
```

Reports how many tokens of each colour are still missing.

- `cost: Tokens` — the card's printed cost.
- `bonus: Tokens` — the player's colour bonuses (gem counts only).
- `paid: Tokens` — tokens already accounted for; typically the player's hand,
  or a candidate payment.
- Returns a `dict[Color, int]` mapping each colour with a positive shortfall to
  the number of tokens still missing.

Semantics:

- For each of the five gem colours the required count is
  `max(0, cost.count(colour) - bonus.count(colour))` — a bonus reduces that
  colour's cost by 1 per bonus token, never below 0, and never refunding.
- The shortfall for that colour is `max(0, required - paid.count(colour))`.
- **Pearls are never discounted by a bonus**: a pearl cost is never reduced, so
  the pearl shortfall is `max(0, cost.pearl - paid.pearl)`.
- **Gold is ignored entirely**: gold is never a card cost, so gold never
  appears in the result. Gold is only ever a wild *payment* token, and the
  shortfall it must cover is the sum of the returned values.
- Only colours with a shortfall greater than zero appear in the result; a
  covered colour is omitted rather than reported as `0`.
- Ordering is guaranteed — see [Ordering guarantees](#ordering-guarantees).

### `can_afford_card`

```python
def can_afford_card(card: Card, tokens: Tokens, bonus: Tokens) -> bool
```

Answers the single affordability question: **may this player buy this card
right now?**

- `card: Card` — the card to buy.
- `tokens: Tokens` — the player's hand.
- `bonus: Tokens` — the player's colour bonuses.
- Returns `True` when the purchase is allowed, `False` otherwise.

Semantics:

- **The multicolor rule is folded into this answer.** A multicolor (joker)
  card may only be bought when the player holds a bonus token in some gem
  colour; that colour must then be chosen at purchase time. If
  `card.is_multicolor` and the player holds no bonus token in any gem colour,
  the answer is `False` regardless of how many tokens they hold.
- Otherwise the answer is
  `sum(cost_deficits(card.cost, bonus, tokens).values()) <= tokens.gold`:
  the shortfall after bonuses and coloured payment must be covered by gold.
- **Gold is wild** — it covers any shortfall, in any gem colour or for pearls.
- Pearls are never discounted by a bonus, so a pearl cost is payable only with
  pearls or with wild gold.
- An ordinary card needs no bonus to be bought.

This is the only affordability question; callers that also need the payment
options should use `legal_payments`, which is empty exactly when this returns
`False`.

### `legal_payments`

```python
def legal_payments(card: Card, tokens: Tokens, bonus: Tokens) -> list[Tokens]
```

Enumerates the payments by which the player can buy `card`.

- `card: Card` — the card to buy.
- `tokens: Tokens` — the player's hand.
- `bonus: Tokens` — the player's colour bonuses.
- Returns a `list[Tokens]` of payments, empty when the card cannot be bought.

Semantics:

- **Empty exactly when `can_afford_card(card, tokens, bonus)` is `False`** —
  including the multicolor case, where the card is unaffordable because no
  colour may be chosen. This keeps `decide()` and `apply()` in agreement: a
  payment is offered if and only if it would be accepted.
- Otherwise every combination of coloured tokens and pearls the player may
  spend is considered, bounded per colour by
  `min(tokens.count(colour), remaining.count(colour))`, where `remaining` is
  the cost after bonuses.
- **Only minimum gold is yielded.** Each payment spends the minimum number of
  gold tokens needed to cover the remaining shortfall of its coloured
  combination, and only payments using the least gold of all the legal
  combinations are returned — spending more gold than necessary is never
  beneficial and would bloat the action space.
- The result is ordered: the white, blue, green, red, black and pearl loops
  nest in that order, because `decide()` offers payments in that order.

### `take_penalty`

```python
def take_penalty(colors: Iterable[Color]) -> bool
```

Answers whether taking these tokens grants the opponent a privilege.

- `colors: Iterable[Color]` — the colours of the tokens taken.
- Returns `True` when the take is penalised, `False` otherwise.

Semantics:

- `True` when any colour appears **three or more** times.
- `True` when **pearl** appears **two or more** times.
- Every colour given is counted; there is no restriction on taking two
  same-colour gems.

### `color_points`

```python
def color_points(purchased: Iterable[PurchasedCard], color: Color) -> int
```

Returns the prestige a player holds in one gem colour.

- `purchased: Iterable[PurchasedCard]` — the player's purchased cards.
- `color: Color` — the gem colour to total.
- Returns the number of points in that colour.

Semantics:

- An ordinary card counts toward its bonus colour (`card.bonus`).
- A multicolor card counts toward the colour chosen at purchase
  (`purchased_card.chosen_color`).
- Colourless cards (`bonus is None` and not multicolor) and royals count
  toward no colour.
- **Card points only.** Bonus tokens are not points in a colour, so
  `card.bonus_count` is *not* added here.

### `discard_subsets`

```python
def discard_subsets(tokens: Tokens, excess: int) -> list[Tokens]
```

Enumerates the ways to discard exactly `excess` tokens.

- `tokens: Tokens` — the player's hand.
- `excess: int` — how many tokens must be discarded (hand size minus
  `TOKEN_LIMIT`).
- Returns a `list[Tokens]` of distinct discard subsets.

Semantics:

- Every distinct subset of `tokens` whose per-colour counts sum to `excess` is
  returned. The empty subset is excluded.
- Gold and pearls may be discarded like any other token.
- The result is deduplicated and in a deterministic order.

### `can_reserve`

```python
def can_reserve(board: tuple[Color | None, ...], reserved_count: int) -> bool
```

Answers whether a player may reserve a card.

- `board: tuple[Color | None, ...]` — the 25 board slots; `None` marks an
  empty slot.
- `reserved_count: int` — how many cards the player already has reserved.
- Returns `True` when reserving is legal, `False` otherwise.

Semantics:

- A gold token must be on the board — reserving is the only way to gain gold.
- The player must hold fewer than `MAX_RESERVED` reserved cards.
- Both conditions are required. The gold test lives inside this function;
  there is no separate "is there gold on the board" helper, because every
  caller of that question is asking this question.

### `visible_cards`

```python
def visible_cards(
    pyramid: tuple[tuple[Card | None, ...], ...],
    reserved_public: tuple[Card, ...],
    reserved_deck: tuple[Card, ...],
) -> list[Card]
```

Returns the cards a player can see.

- `pyramid: tuple[tuple[Card | None, ...], ...]` — the pyramid rows; a slot is
  `None` only when its deck is exhausted.
- `reserved_public: tuple[Card, ...]` — the player's own reservations made
  from the pyramid (public — the opponent sees them too).
- `reserved_deck: tuple[Card, ...]` — the player's own reservations made from
  a deck top (hidden from the opponent).
- Returns a `list[Card]`.

Semantics:

- The result contains the pyramid cards in row order (skipping `None` slots),
  then `reserved_public`, then `reserved_deck`.
- **This order is part of the contract** — see
  [Ordering guarantees](#ordering-guarantees).

## Ordering guarantees

Two helpers are order-sensitive and their order is part of the API contract:

- **`cost_deficits`** returns the five gem colours in `GEM_COLORS` order
  (white, blue, green, red, black), then pearl. Colours with no shortfall are
  omitted, but the relative order of the ones that remain is fixed.
- **`visible_cards`** returns the pyramid cards in row order, then the player's
  own public reservations (taken from the pyramid), then the player's own
  hidden deck reservations.

## Not part of the API

- `_remaining_cost(cost: Tokens, bonus: Tokens) -> Tokens` is private to
  `helpers.py`. It computes the cost after bonuses (per gem colour
  `max(0, cost - bonus)`, pearl unchanged, gold zero) and exists only to serve
  `legal_payments`; it is not part of the public surface.
- The helpers hold **no heuristics**. They answer mechanical questions about
  the rules and never suggest, rank, or prefer an action. Where a rule leaves a
  choice to the player (which colour to take, which card to buy, which
  combination of tokens to pay with), the helpers report the options; they do
  not choose.
