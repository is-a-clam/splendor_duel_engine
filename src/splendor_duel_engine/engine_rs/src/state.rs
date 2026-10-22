//! Game state types.

use crate::board::{PYRAMID_LAYOUT, SPIRAL};
use crate::cards::{Ability, Card, RoyalCard, load_cards};
use crate::colors::{Color, Tokens};
use crate::phase::Phase;
use crate::rng::Random;
use std::rc::Rc;

/// A card a player has bought, plus its multicolor choice if any.
/// `chosen_color` is `Some` when a multicolor card is purchased; `None` for ordinary purchases.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PurchasedCard {
    pub card: Card,
    pub chosen_color: Option<Color>,
}

/// A card a player holds in reserve.
/// `from_deck` is `true` when reserved from a deck top (identity hidden from opponent)
/// and `false` when reserved from the pyramid (public).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ReservedCard {
    pub card: Card,
    pub from_deck: bool,
}

/// One player's full state.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PlayerState {
    pub tokens: Tokens,
    /// Colour bonuses. Only gem counts are allowed; pearl/gold must stay 0.
    pub bonus: Tokens,
    pub prestige: u32,
    pub crowns: u32,
    pub reserved: Vec<ReservedCard>,
    pub purchased: Vec<PurchasedCard>,
    pub privileges: u32,
}

/// The complete, immutable state of a game.
///
/// - `board` is 25 row-major entries (`None` only ever marks an empty token space).
/// - `decks` is indexed 0/1/2 for levels 3/2/1 with the top card last (dealt by popping the end).
/// - `pyramid` rows are levels 3, 2, 1 (lengths 3, 4, 5); a slot is `None` only when its deck is exhausted.
/// - The RNG is held behind an `Rc` so that `apply` shares it instead of copying 2.5 KB per MCTS node.
#[derive(Debug, Clone)]
pub struct GameState {
    pub players: [PlayerState; 2],
    pub board: [Option<Color>; 25],
    pub bag: Tokens,
    pub decks: [Vec<Card>; 3],
    pub pyramid: [Vec<Option<Card>>; 3],
    pub royals_available: Vec<RoyalCard>,
    pub privileges_supply: u32,
    pub current_player: usize,
    pub winner: Option<usize>,
    pub phase: Phase,
    pub pending_buy: Option<BuyCard>,
    pub pending_reserve: Option<ReserveCard>,
    /// True when the current player has earned an extra turn (via EXTRA_TURN ability or royal).
    /// Cleared when the extra turn is consumed.
    pub extra_turn: bool,
    /// Stores the ability being resolved during a decision point phase (STEAL_TOKEN).
    /// `None` otherwise.
    pub pending_ability: Option<Ability>,
    /// True when a purchase crossed a crown threshold but the royal pick was deferred
    /// because the card was multicolor (its color must be chosen first).
    /// Cleared when the royal step runs in `_end_of_turn`.
    pub pending_royal: bool,
    /// The RNG is behind an `Rc` so it can be shared across `apply` calls.
    /// `apply` forks it at replenish (see Task 7).
    pub rng: Rc<Random>,
}

/// Action to buy a card.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct BuyCard {
    pub card: Card,
    pub source: String,
}

/// Action to reserve a card.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ReserveCard {
    pub source: String,
    pub index: usize,
}

/// Total privilege scrolls in the game (spec §Privileges); the second player
/// starts with one, leaving the rest in the supply.
const TOTAL_PRIVILEGES: u32 = 3;

/// Total tokens of each gem colour in the game (spec §Components and setup).
const GEM_TOTAL: u8 = 4;
/// Total pearl tokens in the game (spec §Components and setup).
const PEARL_TOTAL: u8 = 2;
/// Total gold tokens in the game (spec §Components and setup).
const GOLD_TOTAL: u8 = 3;

/// The 25-token supply in the order it is shuffled at setup (spec: 4 each of
/// the five gems, 2 pearls, 3 gold). Pinned so the deal is reproducible.
const TOKEN_SUPPLY: [Color; 25] = [
    Color::WHITE, Color::WHITE, Color::WHITE, Color::WHITE,
    Color::BLUE, Color::BLUE, Color::BLUE, Color::BLUE,
    Color::GREEN, Color::GREEN, Color::GREEN, Color::GREEN,
    Color::RED, Color::RED, Color::RED, Color::RED,
    Color::BLACK, Color::BLACK, Color::BLACK, Color::BLACK,
    Color::PEARL, Color::PEARL,
    Color::GOLD, Color::GOLD, Color::GOLD,
];

/// Create a fresh player with the given number of privileges.
fn fresh_player(privileges: u32) -> PlayerState {
    PlayerState {
        tokens: Tokens::new(),
        bonus: Tokens::new(),
        prestige: 0,
        crowns: 0,
        reserved: Vec::new(),
        purchased: Vec::new(),
        privileges,
    }
}

/// Return a fresh game set up deterministically from `seed`.
///
/// RNG consumption is pinned for reproducibility:
/// (a) shuffle decks level 1, then 2, then 3;
/// (b) deal the pyramid;
/// (c) shuffle the 25-token supply and deal it along SPIRAL;
/// (d) choose the first player.
pub fn new_game(seed: i64) -> GameState {
    let mut rng = Random::from_seed(seed);
    let (jewels, royals) = load_cards().expect("card data must be valid");

    // (a) Shuffle each deck separately, level 1 then 2 then 3 (pinned RNG order).
    // Each shuffled list is stored so decks[0/1/2] is level 3/2/1,
    // matching the pyramid rows; the deck top is the last element.
    let mut shuffled: [Vec<Card>; 3] = [Vec::new(), Vec::new(), Vec::new()];
    for level in [1, 2, 3] {
        let mut level_cards: Vec<Card> = jewels.iter().filter(|c| c.level == level).cloned().collect();
        rng.shuffle(&mut level_cards);
        // level 1 -> index 2, level 2 -> index 1, level 3 -> index 0
        shuffled[3 - level as usize] = level_cards;
    }
    let mut decks = shuffled;

    // (b) Deal the pyramid, each row left-to-right from its deck's top (pop from end).
    let mut pyramid: [Vec<Option<Card>>; 3] = [Vec::new(), Vec::new(), Vec::new()];
    for (row_idx, (row_length, deck_index)) in PYRAMID_LAYOUT.iter().enumerate() {
        pyramid[row_idx] = (0..*row_length)
            .map(|_| decks[*deck_index].pop())
            .collect();
    }

    // (c) Shuffle the token supply once and deal it along the spiral.
    let mut supply = TOKEN_SUPPLY;
    rng.shuffle(&mut supply);
    let mut board = [None; 25];
    for (spiral_idx, color) in SPIRAL.iter().zip(supply.iter()) {
        board[*spiral_idx] = Some(*color);
    }

    // (d) Pick the first player.
    let current_player = rng.randrange(2) as usize;

    // Build the two PlayerStates with one privilege for the non-first player.
    let players = [
        fresh_player(if current_player == 0 { 0 } else { 1 }),
        fresh_player(if current_player == 1 { 0 } else { 1 }),
    ];

    GameState {
        players,
        board,
        bag: Tokens::new(),
        decks,
        pyramid,
        royals_available: royals,
        privileges_supply: TOTAL_PRIVILEGES - 1, // second player took one
        current_player,
        winner: None,
        phase: Phase::USE_PRIVILEGES,
        pending_buy: None,
        pending_reserve: None,
        extra_turn: false,
        pending_ability: None,
        pending_royal: false,
        rng: Rc::new(rng),
    }
}