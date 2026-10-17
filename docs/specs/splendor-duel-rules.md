# Splendor Duel — Rules Specification

Authoritative rules reference for the engine in `src/splendor_duel_engine/engine/`.
The engine and its tests cite this document. When the rulebook is ambiguous,
the ambiguity is recorded in "Resolved ambiguities" with its resolution.

Sources (accessed 2026-10-17):

- **[S1]** Official rulebook PDF, Space Cowboys, SCSPL2P01EN (© 2022), all 12 pages.
- **[S2]** 64 Oz Games transcription of the official rulebook.
- **[S3]** Dized digital rulebook (officially maintained/verified by Space Cowboys), incl. FAQ.
- **[S4]** Board Game Arena official game help for Splendor Duel.
- **[S5]** BGA official implementation source (`github.com/thoun/splendorduel`).
- **[S6]** Independent fan implementations used for card-data cross-checks.

Card data in `src/splendor_duel_engine/engine/cards.json` was cross-checked
field-by-field against S5 and two independent fan databases: **zero discrepancies**.

## Components and setup [S1]

- 67 jewel cards: **30 level-1, 24 level-2, 13 level-3**; **4 royal cards**.
- **25 tokens**: 4 each of blue, white, green, black, red; **2 pearls**; **3 gold**.
- **1 bag**, **3 privilege scrolls**, victory tile.
- Setup order: shuffle the three decks separately; reveal **3 level-3, 4 level-2,
  5 level-1** cards face-up as the pyramid; place the board and all 25 tokens on
  the **5×5 grid** (25 spaces, completely full at setup) following the printed
  spiral starting at the center; 3 privileges to the supply; all 4 royal cards
  face up; choose the first player randomly, **the second player takes 1 privilege**.
- **Spiral order** (row-major indices, verified against the physical board art):
  `12, 7, 8, 13, 18, 17, 16, 11, 6, 1, 2, 3, 4, 9, 14, 19, 24, 23, 22, 21, 20, 15, 10, 5, 0`.

## Turn structure [S1, S3]

On your turn, in this fixed order:

1. **Optional: use privileges.** Return 1 or more privilege scrolls to the supply;
   for each, take 1 gem or pearl token of your choice **from the board**. Cannot
   take gold. Does not end the turn. Must be the first thing on your turn.
2. **Optional: replenish the board.** Illegal if the bag is empty. Draw from the
   bag onto empty spaces following the spiral until the bag is empty or the board
   is full. **The opponent then takes 1 privilege.**
3. **Mandatory: exactly one action** — take tokens (A), buy a card (B), or
   reserve a card (C).

**Forced replenish:** if no mandatory action is possible (no legal token line,
nothing affordable, and reservation illegal), the player **must** perform
replenish first (if the bag is non-empty), then still perform a mandatory action.

## Mandatory action A — Take tokens [S1]

Take **1, 2, or 3** tokens in an **uninterrupted straight line** (horizontal,
vertical, or diagonal; 8 directions) from the board. Single tokens are legal.
Gold tokens cannot be taken this way and block a line.

**Penalty:** if this action takes **3 tokens of one color** or **2 pearls**
(including both pearls taken as part of a longer line), the **opponent takes
1 privilege** immediately. No other token take has a penalty; there is no
restriction on taking 2 same-color gems [S1, S3 FAQ].

## Mandatory action B — Buy a card [S1]

Buy from the pyramid or from your own reserved cards. Payment:

- Card **bonuses** of a color reduce that color's cost by 1 per bonus token,
  **never below 0** (no refunds). Pearls are never reduced.
- **Gold tokens are wild**: usable as any gem or pearl.
- Tokens are taken from your hand only; there is no purse. **Spent tokens go
  into the bag** (including gold).
- Pyramid purchases refill their slot from the corresponding deck (if any cards
  remain; otherwise the slot stays empty). Reserved-card purchases refill nothing.

## Mandatory action C — Reserve a card [S1, S3]

Take **1 gold token** (the only way to gain gold) and reserve 1 card: either a
pyramid card (its slot refills from that deck if non-empty) or the top card of
any deck. Illegal if there is **no gold on the board** or you already have
**3 reserved cards**. Reserved cards have no effect until purchased and incur
no end-game penalty. Visibility differs by source (checked against the physical
game): a card reserved **from the pyramid stays public** (the opponent sees
which card it is); a card reserved **from a deck top is hidden** (the opponent
knows only how many deck-reserved cards you hold). A multicolor card may be
reserved before you own any bonus; the restriction applies only at purchase.

## Card abilities [S1, S3, S5]

Abilities resolve **immediately on purchase**. Five abilities exist:

| Ability | Effect |
|---|---|
| `extra_turn` | Take another full turn immediately after this one ends. |
| `multicolor` | Copy bonus: at purchase, choose a color in which you already own a bonus; this card counts as that color for discounts and the 10-points-one-color win. **Cannot be purchased unless you own a colored bonus card.** Copies only the bonus, never an ability. |
| `take_matching_token` | Take 1 token of this card's bonus color from the board. Ignored if none. |
| `privilege` | Take 1 privilege from the supply; if none, take 1 from the opponent. |
| `steal_token` | Take 1 gem or pearl token of your choice from the opponent. Gold cannot be stolen. Ignored if the opponent has none. |

## Privileges [S1, S3]

Exactly **3 scrolls** exist. Earned: setup (second player), opponent replenishes,
opponent's token-take penalty, `privilege` card abilities, royal abilities.
Taking a privilege with an empty supply: take 1 from the opponent; if the
opponent has none either (which happens when you already hold all 3),
nothing happens. A player may hold all 3. Usage only as the turn's first
optional step.

## Royal cards [S1, S3]

Upon acquiring your **3rd crown**, take one available royal card and resolve
its ability; upon your **6th crown**, take another. Not an action. Max 2 per
player; no trigger at 9 crowns. The 4 royals: *2 points + steal*, *2 points +
extra turn*, *2 points + privilege*, *3 points, no ability*. Royals are
**colorless**: their points count toward the 20-point win but **not** toward the
10-points-one-color win [S3 FAQ].

## End of turn and victory [S1]

End-of-turn sequence, in order: resolve the purchased card's ability → royal
card picks (3rd/6th crowns) → **discard down to 10 tokens** (all token types
count; excess goes to the bag) → check victory conditions.

Victory is checked **only at the end of the active player's turn** (extra turns
included). If one or more conditions hold, that player wins **immediately**;
there is no final opponent turn:

1. **≥ 20 prestige points**, or
2. **≥ 10 crowns**, or
3. **≥ 10 prestige points on cards of one color** (multicolor cards count as
   their chosen color; colorless no-bonus cards and royals do not count).

There is **no end-game bonus scoring and no tiebreaker** [S1 all pages, S3 FAQ,
S4]: the game ends the moment a condition is met and that player wins. Excess
tokens are gone; pearls and privileges are worth nothing at game end.

## Hidden information

**Only deck order is hidden.** Everything else is derivable from public
information and is therefore public state:

- The **board** and both players' **hands**, **purchases** (including multicolor
  chosen colors), **privileges**, the **pyramid**, and available **royals** are
  visible.
- The **bag's contents are public by deduction** — the token census is fixed
  (4 each of the 5 gems, 2 pearls, 3 gold) and every token is on the board, in a
  hand, or in the bag, so the bag is exactly the remainder. Replenish draws
  blindly in the physical game, but the *set* is known.
- **Reserved cards**: a card reserved **from the pyramid stays public**; a card
  reserved **from a deck top is hidden** (the opponent knows only how many
  deck-reserved cards a player holds).

Deck order is the only genuinely hidden information, and only a deck-top
reserve reveals any of it (to the reserving player).

## Resolved ambiguities

1. **Spiral order** is printed on the board, not described in [S1]. Verified
   against the physical board art (center, then clockwise outward); sequence in
   Setup above.
2. **Penalty scope**: [S1] attaches the 3-same-color/2-pearls penalty to the
   take-tokens action only; privilege-token takes are never penalized.
3. **Gold into the bag**: [S1] says spent tokens go to the bag with no carve-out
   for gold, so gold paid or discarded may return to the board via replenish.
   Marked TODO in tests: confirm against a physical game or BGA play log; the
   invariant harness enforces conservation either way.
4. **No-deadlock**: a mandatory action always exists. If the bag is non-empty,
   forced replenish applies. If the bag is empty, then board + hands hold all 25
   tokens; hands are capped at 10 each, so the board holds ≥ 5 tokens, and since
   only 3 gold exist in total the board always has ≥ 2 non-gold tokens — a
   length-1 take is therefore always legal. The fuzz harness asserts this.

## Out of scope

The **Counterfeiters** expansion (paste-gem tokens, extra cards and royals,
changed setup) is out of scope. Base game only.
