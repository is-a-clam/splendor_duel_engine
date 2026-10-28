//! Rule helper functions.
//!
//! Pure functions over state fragments, mirroring `engine/helpers.py`
//! one-for-one. They answer "what does the rule say", never "what is good",
//! and they contain no Python types: `py.rs` wraps them for the boundary.

use crate::cards::Card;
use crate::colors::{Color, Tokens, GEM_COLORS};
use crate::state::{PlayerState, PurchasedCard};
use std::collections::HashSet;

/// Token limit at end of turn (spec §End of turn and victory).
pub const TOKEN_LIMIT: u32 = 10;
/// Maximum reserved cards (spec §Privileges).
pub const MAX_RESERVED: u32 = 3;
/// Prestige win threshold (spec §End of turn and victory).
pub const PRESTIGE_WIN: u32 = 20;
/// Crowns win threshold (spec §End of turn and victory).
pub const CROWNS_WIN: u32 = 10;
/// color-based prestige win threshold (spec §End of turn and victory).
pub const COLOR_WIN_POINTS: u32 = 10;

/// Every color in declaration order, matching Python's `tuple(Color)`.
const ALL_COLORS: [Color; 7] = [
    Color::WHITE,
    Color::BLUE,
    Color::GREEN,
    Color::RED,
    Color::BLACK,
    Color::PEARL,
    Color::GOLD,
];

/// Compute remaining cost after applying bonuses (min 0 per color, pearls
/// never reduced).
///
/// Gold is never a card cost per the rules; it is only a wild payment token.
fn remaining_cost(cost: Tokens, bonus: Tokens) -> Tokens {
    Tokens {
        white: cost.white.saturating_sub(bonus.white),
        blue: cost.blue.saturating_sub(bonus.blue),
        green: cost.green.saturating_sub(bonus.green),
        red: cost.red.saturating_sub(bonus.red),
        black: cost.black.saturating_sub(bonus.black),
        pearl: cost.pearl, // pearls never reduced
        gold: 0,           // gold is never a card cost
    }
}

/// Report missing tokens per color after bonuses and payment.
///
/// For each gem color: `max(0, max(0, cost - bonus) - paid)`. Pearls are never
/// reduced by a bonus. Gold is ignored entirely. Only colors with deficit > 0
/// are included, in `GEM_COLORS` order then pearl (the caller relies on that
/// order for the Python dict).
pub fn cost_deficits(cost: Tokens, bonus: Tokens, paid: Tokens) -> Vec<(Color, u8)> {
    let mut deficits = Vec::new();
    for color in GEM_COLORS {
        let required = cost.count(color).saturating_sub(bonus.count(color));
        let missing = required.saturating_sub(paid.count(color));
        if missing > 0 {
            deficits.push((color, missing));
        }
    }
    let pearl_missing = cost.pearl.saturating_sub(paid.pearl);
    if pearl_missing > 0 {
        deficits.push((Color::PEARL, pearl_missing));
    }
    deficits
}

/// Return whether the player may buy this card right now.
///
/// Gold is wild and covers any shortfall. The multicolor rule is folded into
/// this answer: a multicolor card may not be bought unless the player holds a
/// bonus token in some gem color.
pub fn can_afford_card(card: &Card, tokens: Tokens, bonus: Tokens) -> bool {
    if card.is_multicolor && !GEM_COLORS.iter().any(|&color| bonus.count(color) > 0) {
        return false;
    }
    let shortfall: u32 = cost_deficits(card.cost, bonus, tokens)
        .iter()
        .map(|(_, missing)| u32::from(*missing))
        .sum();
    shortfall <= u32::from(tokens.gold)
}

/// Enumerate legal payments for buying `card`, in the pinned loop order
/// (white, blue, green, red, black, pearl).
///
/// For each combination of colored tokens and pearls the player may spend,
/// only the minimum gold needed to cover that combination's shortfall is
/// yielded. The result is empty exactly when [`can_afford_card`] is false.
pub fn legal_payments(card: &Card, tokens: Tokens, bonus: Tokens) -> Vec<Tokens> {
    if !can_afford_card(card, tokens, bonus) {
        return Vec::new();
    }
    let remaining = remaining_cost(card.cost, bonus);
    let mut legal: Vec<Tokens> = Vec::new();

    for white in 0..=tokens.white.min(remaining.white) {
        for blue in 0..=tokens.blue.min(remaining.blue) {
            for green in 0..=tokens.green.min(remaining.green) {
                for red in 0..=tokens.red.min(remaining.red) {
                    for black in 0..=tokens.black.min(remaining.black) {
                        for pearl in 0..=tokens.pearl.min(remaining.pearl) {
                            let paid = Tokens {
                                white,
                                blue,
                                green,
                                red,
                                black,
                                pearl,
                                gold: 0,
                            };
                            let deficit: u32 = cost_deficits(card.cost, bonus, paid)
                                .iter()
                                .map(|(_, missing)| u32::from(*missing))
                                .sum();
                            if deficit <= u32::from(tokens.gold) {
                                legal.push(Tokens {
                                    white,
                                    blue,
                                    green,
                                    red,
                                    black,
                                    pearl,
                                    gold: deficit as u8,
                                });
                            }
                        }
                    }
                }
            }
        }
    }

    // Deduplicate, keeping first occurrence (enumeration should not produce
    // duplicates, but Python filters them the same way).
    let mut seen: HashSet<Tokens> = HashSet::new();
    legal
        .into_iter()
        .filter(|payment| seen.insert(*payment))
        .collect()
}

/// Return true if taking these colors triggers a penalty.
///
/// True when any color occurs three or more times, or when pearl occurs two
/// or more times.
pub fn take_penalty(colors: &[Color]) -> bool {
    for &color in &ALL_COLORS {
        let count = colors.iter().filter(|&&other| other == color).count();
        if color == Color::PEARL {
            if count >= 2 {
                return true;
            }
        } else if count >= 3 {
            return true;
        }
    }
    false
}

/// Sum card points for purchased cards of effective color `color`.
///
/// A multicolor card's effective color is its `chosen_color`; any other
/// card's is its printed `bonus`. colorless cards contribute nothing. Card
/// points only: bonus tokens are not points in a color.
pub fn color_points(purchased: &[PurchasedCard], color: Color) -> u32 {
    let mut points = 0;
    for purchased_card in purchased {
        let card = &purchased_card.card;
        let effective_bonus = if card.is_multicolor {
            purchased_card.chosen_color
        } else {
            card.bonus
        };
        if effective_bonus == Some(color) {
            points += u32::from(card.points);
        }
    }
    points
}

/// Enumerate distinct discard subsets of `tokens` summing to `excess`.
///
/// Any colors count, including gold and pearls. The order matches the Python
/// recursion: `tuple(Color)` order, with each color's take count descending.
pub fn discard_subsets(tokens: Tokens, excess: i64) -> Vec<Tokens> {
    let mut results = Vec::new();
    let mut seen: HashSet<[u8; 7]> = HashSet::new();
    let mut counts = [0u8; 7];
    discard_recurse(0, &mut counts, excess, &tokens, &mut results, &mut seen);
    results
}

fn discard_recurse(
    idx: usize,
    counts: &mut [u8; 7],
    remaining: i64,
    tokens: &Tokens,
    results: &mut Vec<Tokens>,
    seen: &mut HashSet<[u8; 7]>,
) {
    if remaining == 0 {
        if seen.insert(*counts) {
            results.push(Tokens {
                white: counts[0],
                blue: counts[1],
                green: counts[2],
                red: counts[3],
                black: counts[4],
                pearl: counts[5],
                gold: counts[6],
            });
        }
        return;
    }
    if remaining < 0 || idx == ALL_COLORS.len() {
        return;
    }
    let held = i64::from(tokens.count(ALL_COLORS[idx]));
    let max_take = held.min(remaining);
    for take in (0..=max_take).rev() {
        counts[idx] = take as u8;
        discard_recurse(idx + 1, counts, remaining - take, tokens, results, seen);
    }
    counts[idx] = 0;
}

/// Return true if the player may reserve: gold on the board and fewer than
/// `MAX_RESERVED` reserved cards.
pub fn can_reserve(board: &[Option<Color>], reserved_count: i64) -> bool {
    let has_gold = board.iter().any(|&color| color == Some(Color::GOLD));
    has_gold && reserved_count < i64::from(MAX_RESERVED)
}

/// Return all visible cards in contract order: pyramid rows in order (skipping
/// `None` slots), then own public reservations, then own hidden deck
/// reservations.
pub fn visible_cards(
    pyramid: &[Vec<Option<Card>>],
    reserved_public: &[Card],
    reserved_deck: &[Card],
) -> Vec<Card> {
    let mut result = Vec::new();
    for row in pyramid {
        for card in row {
            if let Some(card) = card {
                result.push(card.clone());
            }
        }
    }
    result.extend(reserved_public.iter().cloned());
    result.extend(reserved_deck.iter().cloned());
    result
}

/// Return true if this player meets any win condition: 20 prestige, 10 crowns,
/// or 10 card points in a single gem color.
pub fn is_winner(player: &PlayerState) -> bool {
    if player.prestige >= PRESTIGE_WIN || player.crowns >= CROWNS_WIN {
        return true;
    }
    GEM_COLORS
        .iter()
        .any(|&color| color_points(&player.purchased, color) >= COLOR_WIN_POINTS)
}
