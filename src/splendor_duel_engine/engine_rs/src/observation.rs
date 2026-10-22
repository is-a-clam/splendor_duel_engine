//! Observation and PlayerView types.

use crate::cards::{Ability, Card, RoyalCard};
use crate::colors::{Color, Tokens};
use crate::phase::Phase;
use crate::state::{BuyCard, GameState, PurchasedCard, ReserveCard};

/// Everything public about a player.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PlayerView {
    pub tokens: Tokens,
    pub bonus: Tokens,
    pub prestige: u32,
    pub crowns: u32,
    pub reserved_public: Vec<Card>,  // pyramid-reserved cards (public)
    pub reserved_deck_count: usize,  // number of deck-reserved cards (hidden identities)
    pub purchased: Vec<PurchasedCard>,
    pub privileges: u32,
}

/// Observation of the game from the active player's perspective.
///
/// **Invariant:** an observation handed to an agent is always taken from the
/// active player's perspective — `you` is the player to move, and
/// `current_player` is that player's seat index.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Observation {
    pub you: PlayerView,
    pub opponent: PlayerView,
    pub board: [Option<Color>; 25],
    pub pyramid: [Vec<Option<Card>>; 3],
    pub royals_available: Vec<RoyalCard>,
    pub privileges_supply: u32,
    pub deck_counts: [usize; 3],
    pub bag: Tokens,
    pub current_player: usize,
    pub winner: Option<usize>,
    pub your_reserved_deck: Vec<Card>,  // own hidden deck reservations
    pub phase: Phase,
    // Pending action fields for sub-decision phases
    pub pending_buy: Option<BuyCard>,
    pub pending_reserve: Option<ReserveCard>,
    pub pending_ability: Option<Ability>,
    pub pending_royal: bool,
    pub extra_turn: bool,
}

/// Create an observation of the state from the given player's perspective.
///
/// Production callers pass `state.current_player`; the function accepts any
/// seat so that tests can inspect a position from either side.
pub fn observation(state: &GameState, player: usize) -> Observation {
    assert!(player < 2, "player must be 0 or 1");

    let you = &state.players[player];
    let opp = &state.players[1 - player];

    // Build your view
    let your_reserved_public: Vec<Card> = you.reserved.iter().filter(|r| !r.from_deck).map(|r| r.card.clone()).collect();
    let your_reserved_deck: Vec<Card> = you.reserved.iter().filter(|r| r.from_deck).map(|r| r.card.clone()).collect();
    let you_view = PlayerView {
        tokens: you.tokens,
        bonus: you.bonus,
        prestige: you.prestige,
        crowns: you.crowns,
        reserved_public: your_reserved_public,
        reserved_deck_count: you.reserved.iter().filter(|r| r.from_deck).count(),
        purchased: you.purchased.clone(),
        privileges: you.privileges,
    };

    // Build opponent view
    let opp_reserved_public: Vec<Card> = opp.reserved.iter().filter(|r| !r.from_deck).map(|r| r.card.clone()).collect();
    let opp_view = PlayerView {
        tokens: opp.tokens,
        bonus: opp.bonus,
        prestige: opp.prestige,
        crowns: opp.crowns,
        reserved_public: opp_reserved_public,
        reserved_deck_count: opp.reserved.iter().filter(|r| r.from_deck).count(),
        purchased: opp.purchased.clone(),
        privileges: opp.privileges,
    };

    // Convert pyramid to array of vecs
    let mut pyramid_arr: [Vec<Option<Card>>; 3] = [Vec::new(), Vec::new(), Vec::new()];
    for i in 0..3 {
        pyramid_arr[i] = state.pyramid[i].clone();
    }

    // Convert deck counts
    let deck_counts = [
        state.decks[0].len(),
        state.decks[1].len(),
        state.decks[2].len(),
    ];

    Observation {
        you: you_view,
        opponent: opp_view,
        board: state.board,
        pyramid: pyramid_arr,
        royals_available: state.royals_available.clone(),
        privileges_supply: state.privileges_supply,
        deck_counts,
        bag: state.bag,
        current_player: state.current_player,
        winner: state.winner,
        your_reserved_deck,
        phase: state.phase,
        pending_buy: state.pending_buy.clone(),
        pending_reserve: state.pending_reserve.clone(),
        pending_ability: state.pending_ability,
        pending_royal: state.pending_royal,
        extra_turn: state.extra_turn,
    }
}