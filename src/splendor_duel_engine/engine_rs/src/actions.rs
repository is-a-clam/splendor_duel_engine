//! Game actions and the legal-action mask.
//!
//! Mirrors `engine/actions.py` one-for-one. The action enum is the pure-Rust
//! counterpart of the Python dataclasses; `py.rs` wraps each variant in a
//! `#[pyclass]` for the boundary. Everything here is a pure function of the
//! state: no heuristics, no RNG.

use crate::board::SPIRAL;
use crate::cards::{Ability, Card};
use crate::colors::{Color, Tokens, GEM_COLORS};
use crate::helpers;
use crate::phase::Phase;
use crate::state::{GameState, PlayerState, PurchasedCard, ReservedCard};
use std::collections::HashSet;
use std::rc::Rc;

pub use crate::state::{BuyCard, ReserveCard};

const BOARD_SIZE: usize = 25;
const BOARD_SIDE: i32 = 5;

/// The eight neighbouring directions, in the pinned Python order
/// (`_DIRECTIONS_8` in `engine/actions.py`).
const DIRECTIONS_8: [(i32, i32); 8] = [
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
];

/// One decision the active player may take at a decision point.
///
/// The shape matches the Python dataclasses; `BuyCard` and `ReserveCard` are
/// the state types from `state.rs` (shared with `pending_buy`/`pending_reserve`).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Action {
    UsePrivilege { index: usize },
    DoneWithPrivileges,
    Replenish,
    DoneWithReplenish,
    TakeTokens { line: Vec<usize> },
    BuyCard(BuyCard),
    PayTokens { payment: Tokens },
    ReserveCard(ReserveCard),
    ChooseGold { index: usize },
    ChooseMulticolor { color: Color },
    ChooseStealToken { color: Color },
    ChooseMatchingToken { index: usize },
    ChooseRoyal { royal_id: String },
    DiscardTokens { tokens: Tokens },
}

/// The legal actions for the state's current phase.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecisionPoint {
    pub phase: Phase,
    pub legal_actions: Vec<Action>,
}

/// Enumerate the legal actions for `state`, exactly as Python's `decide`.
///
/// Action order is part of the contract: non-take actions keep their build
/// order (reserves, then buys) and take-token lines come last, sorted by
/// `(len, line)`.
pub fn decide(state: &GameState) -> Result<DecisionPoint, &'static str> {
    if state.winner.is_some() {
        return Err("game is over");
    }

    if state.phase == Phase::USE_PRIVILEGES {
        let active = &state.players[state.current_player];
        let mut legal_actions = Vec::new();
        if active.privileges > 0 {
            // A privilege may take any non-gold, non-empty token from the board.
            for (idx, color) in state.board.iter().enumerate() {
                if let Some(color) = color {
                    if *color != Color::GOLD {
                        legal_actions.push(Action::UsePrivilege { index: idx });
                    }
                }
            }
        }
        legal_actions.push(Action::DoneWithPrivileges);
        return Ok(DecisionPoint {
            phase: Phase::USE_PRIVILEGES,
            legal_actions,
        });
    }

    if state.phase == Phase::REPLENISH {
        let mut legal_actions = Vec::new();
        if state.bag.total() > 0 {
            legal_actions.push(Action::Replenish);
        }
        legal_actions.push(Action::DoneWithReplenish);
        return Ok(DecisionPoint {
            phase: Phase::REPLENISH,
            legal_actions,
        });
    }

    if state.phase == Phase::CHOOSE_GOLD {
        let mut legal_actions = Vec::new();
        for (idx, color) in state.board.iter().enumerate() {
            if *color == Some(Color::GOLD) {
                legal_actions.push(Action::ChooseGold { index: idx });
            }
        }
        return Ok(DecisionPoint {
            phase: Phase::CHOOSE_GOLD,
            legal_actions,
        });
    }

    if state.phase == Phase::MANDATORY {
        let takes: Vec<Action> = legal_take_token_lines(&state.board)
            .into_iter()
            .map(|line| Action::TakeTokens { line })
            .collect();
        let reserves: Vec<Action> = get_reserve_actions(state)
            .into_iter()
            .map(Action::ReserveCard)
            .collect();
        let buys: Vec<Action> = get_buyable_cards(state)
            .into_iter()
            .map(Action::BuyCard)
            .collect();

        // Forced replenish: only when there is no take, reserve or buy action.
        if takes.is_empty() && reserves.is_empty() && buys.is_empty() && state.bag.total() > 0 {
            return Ok(DecisionPoint {
                phase: Phase::REPLENISH,
                legal_actions: vec![Action::Replenish],
            });
        }

        // Python appends takes, reserves, buys then stable-sorts non-takes
        // first (keep order) and takes by `(len, line)`; reproduce that
        // effective order directly.
        let mut legal_actions = Vec::with_capacity(reserves.len() + buys.len() + takes.len());
        legal_actions.extend(reserves);
        legal_actions.extend(buys);
        legal_actions.extend(takes);
        return Ok(DecisionPoint {
            phase: Phase::MANDATORY,
            legal_actions,
        });
    }

    if state.phase == Phase::CHOOSE_PAYMENT {
        let Some(pending) = &state.pending_buy else {
            return Ok(DecisionPoint {
                phase: Phase::CHOOSE_PAYMENT,
                legal_actions: Vec::new(),
            });
        };
        let active = &state.players[state.current_player];
        let legal_actions = helpers::legal_payments(&pending.card, active.tokens, active.bonus)
            .into_iter()
            .map(|payment| Action::PayTokens { payment })
            .collect();
        return Ok(DecisionPoint {
            phase: Phase::CHOOSE_PAYMENT,
            legal_actions,
        });
    }

    if state.phase == Phase::MULTICOLOR_COLOR {
        if state.pending_buy.is_none() {
            return Ok(DecisionPoint {
                phase: Phase::MULTICOLOR_COLOR,
                legal_actions: Vec::new(),
            });
        }
        let active = &state.players[state.current_player];
        let legal_actions = GEM_COLORS
            .iter()
            .filter(|&&color| active.bonus.count(color) > 0)
            .map(|&color| Action::ChooseMulticolor { color })
            .collect();
        return Ok(DecisionPoint {
            phase: Phase::MULTICOLOR_COLOR,
            legal_actions,
        });
    }

    if state.phase == Phase::STEAL_TOKEN {
        if state.pending_ability != Some(Ability::STEAL_TOKEN) {
            return Ok(DecisionPoint {
                phase: Phase::STEAL_TOKEN,
                legal_actions: Vec::new(),
            });
        }
        let opponent = &state.players[1 - state.current_player];
        let legal_actions = GEM_COLORS
            .iter()
            .filter(|&&color| opponent.tokens.count(color) > 0)
            .map(|&color| Action::ChooseStealToken { color })
            .collect();
        return Ok(DecisionPoint {
            phase: Phase::STEAL_TOKEN,
            legal_actions,
        });
    }

    if state.phase == Phase::TAKE_MATCHING_TOKEN {
        if state.pending_ability != Some(Ability::TAKE_MATCHING_TOKEN) {
            return Ok(DecisionPoint {
                phase: Phase::TAKE_MATCHING_TOKEN,
                legal_actions: Vec::new(),
            });
        }
        // The purchased card is kept in `pending_buy` for the ability resolution.
        let Some(pending) = &state.pending_buy else {
            return Ok(DecisionPoint {
                phase: Phase::TAKE_MATCHING_TOKEN,
                legal_actions: Vec::new(),
            });
        };
        let Some(bonus_color) = pending.card.bonus else {
            return Ok(DecisionPoint {
                phase: Phase::TAKE_MATCHING_TOKEN,
                legal_actions: Vec::new(),
            });
        };
        let legal_actions = state
            .board
            .iter()
            .enumerate()
            .filter(|(_, color)| **color == Some(bonus_color))
            .map(|(idx, _)| Action::ChooseMatchingToken { index: idx })
            .collect();
        return Ok(DecisionPoint {
            phase: Phase::TAKE_MATCHING_TOKEN,
            legal_actions,
        });
    }

    if state.phase == Phase::CHOOSE_ROYAL {
        let legal_actions = state
            .royals_available
            .iter()
            .map(|royal| Action::ChooseRoyal {
                royal_id: royal.id.clone(),
            })
            .collect();
        return Ok(DecisionPoint {
            phase: Phase::CHOOSE_ROYAL,
            legal_actions,
        });
    }

    if state.phase == Phase::DISCARD {
        let active = &state.players[state.current_player];
        let excess = i64::from(active.tokens.total()) - i64::from(helpers::TOKEN_LIMIT);
        let legal_actions = helpers::discard_subsets(active.tokens, excess)
            .into_iter()
            .map(|tokens| Action::DiscardTokens { tokens })
            .collect();
        return Ok(DecisionPoint {
            phase: Phase::DISCARD,
            legal_actions,
        });
    }

    Ok(DecisionPoint {
        phase: state.phase,
        legal_actions: Vec::new(),
    })
}

/// Convert a board index to (row, column) in the 5x5 grid.
pub fn index_to_rc(index: usize) -> (usize, usize) {
    (index / 5, index % 5)
}

/// Convert a (row, column) to a board index, or `None` when out of bounds.
pub fn rc_to_index(row: i32, col: i32) -> Option<usize> {
    if row < 0 || row >= BOARD_SIDE || col < 0 || col >= BOARD_SIDE {
        return None;
    }
    Some((row * BOARD_SIDE + col) as usize)
}

/// Return whether `line` is a contiguous straight run of 1-3 distinct cells.
pub fn is_straight_line(line: &[usize]) -> bool {
    if line.is_empty() || line.len() > 3 {
        return false;
    }
    if line.iter().collect::<HashSet<_>>().len() != line.len() {
        return false;
    }
    if line.len() == 1 {
        return true;
    }
    let (r0, c0) = index_to_rc(line[0]);
    let (r1, c1) = index_to_rc(line[1]);
    let step = (r1 as i32 - r0 as i32, c1 as i32 - c0 as i32);
    if !DIRECTIONS_8.contains(&step) {
        return false;
    }
    for pair in line.windows(2) {
        let (ra, ca) = index_to_rc(pair[0]);
        let (rb, cb) = index_to_rc(pair[1]);
        if (rb as i32 - ra as i32, cb as i32 - ca as i32) != step {
            return false;
        }
    }
    true
}

/// Enumerate each distinct straight line of 1-3 non-gold tokens once.
///
/// Matches Python: scan from every start cell in all eight directions,
/// canonicalise each candidate to the lexicographic minimum of the line and
/// its reverse, deduplicate, then sort by `(len, line)`.
pub fn legal_take_token_lines(board: &[Option<Color>; BOARD_SIZE]) -> Vec<Vec<usize>> {
    let mut result: HashSet<Vec<usize>> = HashSet::new();
    for (start, color) in board.iter().enumerate() {
        let Some(color) = color else {
            continue;
        };
        if *color == Color::GOLD {
            continue;
        }
        result.insert(vec![start]);
        let (row, col) = index_to_rc(start);
        for (dr, dc) in DIRECTIONS_8 {
            let Some(idx2) = rc_to_index(row as i32 + dr, col as i32 + dc) else {
                continue;
            };
            if !is_takeable(board, idx2) {
                continue;
            }
            result.insert(if start < idx2 {
                vec![start, idx2]
            } else {
                vec![idx2, start]
            });
            let Some(idx3) = rc_to_index(row as i32 + dr * 2, col as i32 + dc * 2) else {
                continue;
            };
            if !is_takeable(board, idx3) {
                continue;
            }
            let line = vec![start, idx2, idx3];
            let reversed: Vec<usize> = line.iter().rev().copied().collect();
            result.insert(if line <= reversed { line } else { reversed });
        }
    }

    let mut lines: Vec<Vec<usize>> = result.into_iter().collect();
    lines.sort_by(|a, b| a.len().cmp(&b.len()).then_with(|| a.cmp(b)));
    lines
}

/// A cell is takeable when it holds a non-gold token.
fn is_takeable(board: &[Option<Color>; BOARD_SIZE], index: usize) -> bool {
    matches!(board[index], Some(color) if color != Color::GOLD)
}

/// Enumerate all legal `ReserveCard` actions for the active player.
pub fn get_reserve_actions(state: &GameState) -> Vec<ReserveCard> {
    let active = &state.players[state.current_player];
    if !helpers::can_reserve(&state.board, active.reserved.len() as i64) {
        return Vec::new();
    }

    let mut actions = Vec::new();

    // Public pyramid cards, row-major.
    for (row_idx, row) in state.pyramid.iter().enumerate() {
        for (col_idx, card) in row.iter().enumerate() {
            if card.is_some() {
                actions.push(ReserveCard {
                    source: "pyramid".to_string(),
                    index: row_idx * 10 + col_idx,
                });
            }
        }
    }

    // Deck tops (hidden cards): decks are stored level 3, 2, 1.
    for (deck_idx, deck) in state.decks.iter().enumerate() {
        if !deck.is_empty() {
            let level = 3 - deck_idx;
            actions.push(ReserveCard {
                source: format!("deck_{}", level),
                index: 0,
            });
        }
    }

    actions
}

/// Return `BuyCard` actions for cards the active player can afford.
///
/// Sources are `"reserved"` or `"pyramid_r_c"`. Deduplicates by card id,
/// keeping the first inserted position (reserved before pyramid), exactly like
/// Python's insertion-ordered dict.
pub fn get_buyable_cards(state: &GameState) -> Vec<BuyCard> {
    let active = &state.players[state.current_player];
    let mut buyable: Vec<(Card, String)> = Vec::new();

    // Own reserved cards first, so they take precedence.
    for reserved in &active.reserved {
        let card = &reserved.card;
        if helpers::can_afford_card(card, active.tokens, active.bonus) {
            insert_by_id(&mut buyable, card.clone(), "reserved".to_string());
        }
    }

    // Pyramid cards.
    for (row_idx, row) in state.pyramid.iter().enumerate() {
        for (col_idx, card) in row.iter().enumerate() {
            let Some(card) = card else {
                continue;
            };
            if buyable.iter().any(|(seen, _)| seen.id == card.id) {
                continue;
            }
            if helpers::can_afford_card(card, active.tokens, active.bonus) {
                insert_by_id(
                    &mut buyable,
                    card.clone(),
                    format!("pyramid_{}_{}", row_idx, col_idx),
                );
            }
        }
    }

    buyable
        .into_iter()
        .map(|(card, source)| BuyCard { card, source })
        .collect()
}

/// Insert `card` under its id, replacing an existing entry in place (Python
/// dict assignment order) or appending a new one.
fn insert_by_id(entries: &mut Vec<(Card, String)>, card: Card, source: String) {
    if let Some(slot) = entries.iter_mut().find(|(seen, _)| seen.id == card.id) {
        *slot = (card, source);
    } else {
        entries.push((card, source));
    }
}

// ===== State transitions =====

/// The seven colours in Python's `Color` declaration order (`for color in Color`).
const COLOR_ORDER: [Color; 7] = [
    Color::WHITE,
    Color::BLUE,
    Color::GREEN,
    Color::RED,
    Color::BLACK,
    Color::PEARL,
    Color::GOLD,
];

/// Add `amount` tokens of `color` in place.
fn add_color(tokens: &mut Tokens, color: Color, amount: u8) {
    match color {
        Color::WHITE => tokens.white = tokens.white.wrapping_add(amount),
        Color::BLUE => tokens.blue = tokens.blue.wrapping_add(amount),
        Color::GREEN => tokens.green = tokens.green.wrapping_add(amount),
        Color::RED => tokens.red = tokens.red.wrapping_add(amount),
        Color::BLACK => tokens.black = tokens.black.wrapping_add(amount),
        Color::PEARL => tokens.pearl = tokens.pearl.wrapping_add(amount),
        Color::GOLD => tokens.gold = tokens.gold.wrapping_add(amount),
    }
}

/// Subtract `amount` tokens of `color` in place (wrapping, like Python's ints
/// for the validated paths, which never underflow).
fn sub_color(tokens: &mut Tokens, color: Color, amount: u8) {
    match color {
        Color::WHITE => tokens.white = tokens.white.wrapping_sub(amount),
        Color::BLUE => tokens.blue = tokens.blue.wrapping_sub(amount),
        Color::GREEN => tokens.green = tokens.green.wrapping_sub(amount),
        Color::RED => tokens.red = tokens.red.wrapping_sub(amount),
        Color::BLACK => tokens.black = tokens.black.wrapping_sub(amount),
        Color::PEARL => tokens.pearl = tokens.pearl.wrapping_sub(amount),
        Color::GOLD => tokens.gold = tokens.gold.wrapping_sub(amount),
    }
}

/// A token count holding exactly one token of `color`.
fn token_of(color: Color) -> Tokens {
    let mut tokens = Tokens::new();
    add_color(&mut tokens, color, 1);
    tokens
}

// --- Private ports of the `GameState` update methods in `engine/state.py` ---

/// Replace one player. Matches `GameState.replace_player`.
fn replace_player(state: &mut GameState, player_idx: usize, new_player: PlayerState) {
    state.players[player_idx] = new_player;
}

/// Update a single board index. Matches `GameState.update_board`.
fn update_board(state: &mut GameState, idx: usize, new_color: Option<Color>) {
    state.board[idx] = new_color;
}

/// Set a board index to `None`. Matches `GameState.remove_from_board`.
fn remove_from_board(state: &mut GameState, idx: usize) {
    state.board[idx] = None;
}

/// Add tokens to the bag. Matches `GameState.add_to_bag`.
fn add_to_bag(state: &mut GameState, tokens: Tokens) {
    state.bag = state.bag.add_tokens(tokens);
}

/// Pop the top card from a deck. Matches `GameState.pop_deck`.
fn pop_deck(state: &mut GameState, deck_idx: usize) -> Option<Card> {
    state.decks.get_mut(deck_idx).and_then(|deck| deck.pop())
}

/// Take a pyramid card and refill its slot from the matching deck.
/// Matches `GameState.take_pyramid_card`.
fn take_pyramid_card(state: &mut GameState, row_idx: usize, col_idx: usize) -> Option<Card> {
    let card = state.pyramid.get(row_idx)?.get(col_idx)?.clone();
    let row = state.pyramid.get_mut(row_idx)?;
    let slot = row.get_mut(col_idx)?;
    *slot = None;
    if let Some(deck) = state.decks.get_mut(row_idx) {
        if let Some(next) = deck.pop() {
            *slot = Some(next);
        }
    }
    card
}

/// Grant one privilege from the supply, else steal one from the other player.
/// Matches `GameState.grant_privilege`.
fn grant_privilege(state: &mut GameState, recipient: usize) {
    let other = 1 - recipient;
    if state.privileges_supply > 0 {
        state.privileges_supply -= 1;
        state.players[recipient].privileges += 1;
    } else if state.players[other].privileges > 0 {
        state.players[other].privileges -= 1;
        state.players[recipient].privileges += 1;
    }
}

/// Return whether `recipient`'s opponent holds any stealable (gem) token.
fn has_stealable_tokens(state: &GameState, recipient: usize) -> bool {
    let opponent = &state.players[1 - recipient];
    GEM_COLORS
        .iter()
        .any(|&color| opponent.tokens.count(color) > 0)
}

/// Apply `action` to `state`, returning a new state. Never mutates `state`.
///
/// Validation order matches Python: the decision point is computed first (so a
/// finished game reports "game is over"), then the action must be one of the
/// legal actions.
pub fn apply(state: &GameState, action: Action) -> Result<GameState, &'static str> {
    let decision = decide(state)?;
    if !decision.legal_actions.contains(&action) {
        return Err("illegal action");
    }
    dispatch(state, &action)
}

/// Route a validated action to its transition.
fn dispatch(state: &GameState, action: &Action) -> Result<GameState, &'static str> {
    match action {
        Action::UsePrivilege { index } => apply_use_privilege(state, *index),
        Action::DoneWithPrivileges => {
            let mut next = state.clone();
            next.phase = Phase::REPLENISH;
            Ok(next)
        }
        Action::Replenish => apply_replenish(state),
        Action::DoneWithReplenish => {
            // If the extra-turn flag is set, consume it and stay with the same
            // player (there was no replenish to do).
            let mut next = state.clone();
            next.phase = Phase::MANDATORY;
            if next.extra_turn {
                next.extra_turn = false;
            }
            Ok(next)
        }
        Action::TakeTokens { line } => apply_take_tokens(state, line),
        Action::ReserveCard(reserve) => apply_reserve_card(state, reserve),
        Action::ChooseGold { index } => apply_choose_gold(state, *index),
        Action::BuyCard(buy) => apply_buy_card(state, buy),
        Action::PayTokens { payment } => apply_pay_tokens(state, *payment),
        Action::ChooseMulticolor { color } => apply_choose_multicolor(state, *color),
        Action::ChooseStealToken { color } => apply_choose_steal_token(state, *color),
        Action::ChooseMatchingToken { index } => apply_choose_matching_token(state, *index),
        Action::ChooseRoyal { royal_id } => apply_choose_royal(state, royal_id),
        Action::DiscardTokens { tokens } => apply_discard_tokens(state, *tokens),
    }
}

/// Spend a privilege to take one non-gold token from the board.
fn apply_use_privilege(state: &GameState, index: usize) -> Result<GameState, &'static str> {
    let active = state.current_player;
    if state.players[active].privileges == 0 {
        return Err("player does not have privilege");
    }
    if index >= BOARD_SIZE {
        return Err("invalid board index");
    }
    let Some(color) = state.board[index] else {
        return Err("no non-gold token at index");
    };
    if color == Color::GOLD {
        return Err("no non-gold token at index");
    }

    let mut state = state.clone();
    remove_from_board(&mut state, index);
    let token = token_of(color);
    state.players[active].tokens = state.players[active].tokens.add_tokens(token);
    state.players[active].privileges -= 1;

    state.current_player = active;
    state.phase = if state.players[active].privileges > 0 {
        Phase::USE_PRIVILEGES
    } else {
        Phase::REPLENISH
    };
    Ok(state)
}

/// Shuffle the bag into the empty board spaces and hand the opponent a privilege.
///
/// The shuffle uses a *fork* of the state's RNG: `apply` never mutates its
/// input, and the advanced copy is stored in the returned state so replaying
/// the same action sequence yields the same draws.
fn apply_replenish(state: &GameState) -> Result<GameState, &'static str> {
    let active = state.current_player;
    let opponent = 1 - active;

    // Collect all tokens from the bag in declaration order.
    let mut token_colors: Vec<Color> = Vec::new();
    for color in COLOR_ORDER {
        let count = state.bag.count(color);
        token_colors.extend(std::iter::repeat(color).take(usize::from(count)));
    }

    // Fork the RNG before shuffling; never draw from `state.rng` directly.
    let mut local_rng = (*state.rng).clone();
    local_rng.shuffle(&mut token_colors);

    let empty_indices: Vec<usize> = SPIRAL
        .iter()
        .copied()
        .filter(|&idx| state.board[idx].is_none())
        .collect();

    let mut state = state.clone();
    let placed_count = token_colors.len().min(empty_indices.len());
    for i in 0..placed_count {
        update_board(&mut state, empty_indices[i], Some(token_colors[i]));
    }

    // All tokens are placed on the board; the bag is empty.
    state.bag = Tokens::new();
    grant_privilege(&mut state, opponent);

    state.current_player = active;
    state.phase = Phase::MANDATORY;
    state.rng = Rc::new(local_rng);
    Ok(state)
}

/// Take a straight line of 1-3 non-gold tokens from the board.
fn apply_take_tokens(state: &GameState, line: &[usize]) -> Result<GameState, &'static str> {
    if !is_straight_line(line) || line.is_empty() || line.len() > 3 {
        return Err("line must be contiguous straight of length 1-3");
    }

    let mut state = state.clone();
    let mut taken_colors: Vec<Color> = Vec::new();
    for &idx in line {
        match state.board[idx] {
            None => return Err("cannot take gold or empty cell"),
            Some(Color::GOLD) => return Err("cannot take gold or empty cell"),
            Some(color) => taken_colors.push(color),
        }
        remove_from_board(&mut state, idx);
    }

    let active = state.current_player;
    let mut taken_tokens = Tokens::new();
    for &color in &taken_colors {
        add_color(&mut taken_tokens, color, 1);
    }
    state.players[active].tokens = state.players[active].tokens.add_tokens(taken_tokens);

    if helpers::take_penalty(&taken_colors) {
        grant_privilege(&mut state, 1 - active);
    }

    end_of_turn(state, active, false)
}

/// Validate a reserve and enter `CHOOSE_GOLD`.
fn apply_reserve_card(state: &GameState, action: &ReserveCard) -> Result<GameState, &'static str> {
    let active = state.current_player;
    if !helpers::can_reserve(&state.board, state.players[active].reserved.len() as i64) {
        return Err("cannot reserve card");
    }

    if action.source == "pyramid" {
        let row_idx = action.index / 10;
        let col_idx = action.index % 10;
        if row_idx >= state.pyramid.len() || col_idx >= state.pyramid[row_idx].len() {
            return Err("invalid pyramid index");
        }
        if state.pyramid[row_idx][col_idx].is_none() {
            return Err("empty pyramid slot");
        }
    } else if let Some(level_str) = action.source.strip_prefix("deck_") {
        let level: i64 = level_str.parse().map_err(|_| "invalid deck level")?;
        let deck_idx = 3 - level;
        if !(0..state.decks.len() as i64).contains(&deck_idx) {
            return Err("invalid deck index");
        }
        if state.decks[deck_idx as usize].is_empty() {
            return Err("deck empty");
        }
    } else {
        return Err("unknown reserve source");
    }

    let mut next = state.clone();
    next.pending_reserve = Some(action.clone());
    next.phase = Phase::CHOOSE_GOLD;
    Ok(next)
}

/// Take the chosen gold token and complete the reserve in one step.
fn apply_choose_gold(state: &GameState, index: usize) -> Result<GameState, &'static str> {
    let active = state.current_player;
    let Some(pending) = state.pending_reserve.clone() else {
        return Err("no pending reserve action");
    };
    if index >= BOARD_SIZE {
        return Err("invalid board index");
    }
    if state.board[index] != Some(Color::GOLD) {
        return Err("no gold token at index");
    }

    let mut state = state.clone();
    remove_from_board(&mut state, index);
    let gold = token_of(Color::GOLD);
    state.players[active].tokens = state.players[active].tokens.add_tokens(gold);

    let (card, from_deck) = if pending.source == "pyramid" {
        let row_idx = pending.index / 10;
        let col_idx = pending.index % 10;
        (take_pyramid_card(&mut state, row_idx, col_idx), false)
    } else if let Some(level_str) = pending.source.strip_prefix("deck_") {
        let level: i64 = level_str.parse().map_err(|_| "invalid deck level")?;
        let deck_idx = 3 - level;
        if !(0..state.decks.len() as i64).contains(&deck_idx) {
            return Err("invalid deck index");
        }
        (pop_deck(&mut state, deck_idx as usize), true)
    } else {
        return Err("unknown reserve source");
    };
    let Some(card) = card else {
        return Err("card not found");
    };

    state.players[active]
        .reserved
        .push(ReservedCard { card, from_deck });

    state.pending_reserve = None;
    end_of_turn(state, active, false)
}

/// Validate a buy and enter `CHOOSE_PAYMENT`.
fn apply_buy_card(state: &GameState, action: &BuyCard) -> Result<GameState, &'static str> {
    let active = state.current_player;
    let ap = &state.players[active];
    let card = &action.card;
    let source = &action.source;

    if source == "reserved" {
        if !ap.reserved.iter().any(|r| r.card.id == card.id) {
            return Err("card not in reserved");
        }
    } else if source.starts_with("pyramid_") {
        let parts: Vec<&str> = source.split('_').collect();
        if parts.len() != 3 {
            return Err("invalid pyramid source");
        }
        let row_idx: usize = parts[1].parse().map_err(|_| "invalid pyramid source")?;
        let col_idx: usize = parts[2].parse().map_err(|_| "invalid pyramid source")?;
        if row_idx >= state.pyramid.len() || col_idx >= state.pyramid[row_idx].len() {
            return Err("invalid pyramid index");
        }
        match &state.pyramid[row_idx][col_idx] {
            Some(pyr_card) if pyr_card.id == card.id => {}
            _ => return Err("card not at pyramid source"),
        }
    } else {
        return Err("unknown buy source");
    }

    if !helpers::can_afford_card(card, ap.tokens, ap.bonus) {
        return Err("cannot afford card");
    }

    let mut next = state.clone();
    next.pending_buy = Some(action.clone());
    next.phase = Phase::CHOOSE_PAYMENT;
    Ok(next)
}

/// Pay for the pending card, then run the crown/royal/ability flow.
fn apply_pay_tokens(state: &GameState, payment: Tokens) -> Result<GameState, &'static str> {
    let active = state.current_player;
    let Some(pending) = state.pending_buy.clone() else {
        return Err("no pending card to pay for");
    };
    let card = pending.card.clone();
    let source = pending.source.clone();

    let ap = &state.players[active];
    if !helpers::can_afford_card(&card, payment, ap.bonus) {
        return Err("insufficient payment");
    }
    for color in COLOR_ORDER {
        if payment.count(color) > ap.tokens.count(color) {
            return Err("payment exceeds tokens");
        }
    }

    let mut state = state.clone();
    add_to_bag(&mut state, payment);

    let mut new_ap = state.players[active].clone();
    new_ap.tokens = new_ap.tokens.sub_tokens(payment);

    if source == "reserved" {
        if let Some(i) = new_ap.reserved.iter().position(|r| r.card.id == card.id) {
            new_ap.reserved.remove(i);
        }
    } else if source.starts_with("pyramid_") {
        let parts: Vec<&str> = source.split('_').collect();
        if parts.len() != 3 {
            return Err("invalid pyramid source");
        }
        let row_idx: usize = parts[1].parse().map_err(|_| "invalid pyramid source")?;
        let col_idx: usize = parts[2].parse().map_err(|_| "invalid pyramid source")?;
        let taken = take_pyramid_card(&mut state, row_idx, col_idx);
        match taken {
            None => return Err("card not found"),
            Some(from_pyramid) if from_pyramid.id != card.id => {
                return Err("card not at pyramid source")
            }
            Some(_) => {}
        }
    } else {
        return Err("unknown buy source");
    }

    new_ap.purchased.push(PurchasedCard {
        card: card.clone(),
        chosen_color: None,
    });

    let old_crowns = new_ap.crowns;
    if let Some(bonus_color) = card.bonus {
        new_ap.bonus = new_ap.bonus.add_tokens(token_of(bonus_color));
    }
    new_ap.prestige += u32::from(card.points);
    new_ap.crowns += u32::from(card.crowns);
    let new_crowns = new_ap.crowns;

    replace_player(&mut state, active, new_ap);

    // Crossing the 3rd or 6th crown threshold (from below) earns one royal pick.
    // A multicolor card cannot pick yet: its colour choice comes first.
    let crossed_royal = (old_crowns < 3 && 3 <= new_crowns) || (old_crowns < 6 && 6 <= new_crowns);

    if crossed_royal && !state.royals_available.is_empty() {
        state.pending_buy = Some(pending);
        state.winner = None;
        state.current_player = active;
        state.phase = Phase::CHOOSE_ROYAL;
        state.extra_turn = false;
        state.pending_ability = None;
        if card.is_multicolor {
            state.phase = Phase::MULTICOLOR_COLOR;
            state.pending_royal = true;
        }
        return Ok(state);
    }

    if card.is_multicolor {
        state.pending_buy = Some(pending);
        state.winner = None;
        state.current_player = active;
        state.phase = Phase::MULTICOLOR_COLOR;
        state.extra_turn = false;
        state.pending_ability = None;
        return Ok(state);
    }

    state.pending_buy = Some(pending);
    state.winner = None;
    state.current_player = active;
    state.phase = Phase::USE_PRIVILEGES;
    state.extra_turn = false;
    state.pending_ability = None;
    resolve_abilities(state, &card, active)
}

/// Resolve the card's single ability (if any). Returns the final state.
fn resolve_abilities(
    mut state: GameState,
    card: &Card,
    active: usize,
) -> Result<GameState, &'static str> {
    match card.ability {
        Some(Ability::STEAL_TOKEN) => {
            if has_stealable_tokens(&state, active) {
                state.phase = Phase::STEAL_TOKEN;
                state.pending_ability = Some(Ability::STEAL_TOKEN);
                Ok(state)
            } else {
                // No tokens to steal: normal turn end.
                end_of_turn(state, active, false)
            }
        }
        Some(Ability::TAKE_MATCHING_TOKEN) => run_take_matching_token(state, card, active),
        Some(Ability::PRIVILEGE) => {
            state.pending_buy = None;
            grant_privilege(&mut state, active);
            end_of_turn(state, active, false)
        }
        Some(Ability::EXTRA_TURN) => {
            state.pending_buy = None;
            end_of_turn(state, active, true)
        }
        None => {
            state.pending_buy = None;
            end_of_turn(state, active, false)
        }
    }
}

/// Enter `TAKE_MATCHING_TOKEN` when the board has a token of the card's colour.
fn run_take_matching_token(
    state: GameState,
    card: &Card,
    active: usize,
) -> Result<GameState, &'static str> {
    if let Some(bonus_color) = card.bonus {
        if state.board.iter().any(|color| *color == Some(bonus_color)) {
            let mut state = state;
            // Keep `pending_buy` for the decision phase to read the bonus colour.
            state.phase = Phase::TAKE_MATCHING_TOKEN;
            state.pending_ability = Some(Ability::TAKE_MATCHING_TOKEN);
            return Ok(state);
        }
    }
    end_of_turn(state, active, false)
}

/// Move the chosen excess tokens to the bag, then finish the turn.
fn apply_discard_tokens(state: &GameState, tokens: Tokens) -> Result<GameState, &'static str> {
    let active = state.current_player;
    let ap = &state.players[active];
    let excess = i64::from(ap.tokens.total()) - i64::from(helpers::TOKEN_LIMIT);

    for color in COLOR_ORDER {
        if u32::from(tokens.count(color)) > u32::from(ap.tokens.count(color)) {
            return Err("cannot discard more than held");
        }
    }
    if i64::from(tokens.total()) != excess {
        return Err("discard must remove exactly the excess tokens");
    }

    let mut state = state.clone();
    add_to_bag(&mut state, tokens);
    state.players[active].tokens = state.players[active].tokens.sub_tokens(tokens);

    // The pending seat decision was stashed in `extra_turn` by `end_of_turn`.
    let pending_extra_turn = state.extra_turn;
    finish_turn(state, active, pending_extra_turn)
}

/// Resolve the chosen colour for a multicolor card, then its ability.
fn apply_choose_multicolor(state: &GameState, color: Color) -> Result<GameState, &'static str> {
    let active = state.current_player;
    let Some(pending) = state.pending_buy.clone() else {
        return Err("no pending card for multicolor resolution");
    };
    let card = pending.card.clone();
    if !card.is_multicolor {
        return Err("card is not multicolor");
    }

    let mut state = state.clone();
    let ap = &mut state.players[active];
    let Some(last_pc) = ap.purchased.last_mut() else {
        return Err("purchased card mismatch");
    };
    if last_pc.card.id != card.id {
        return Err("purchased card mismatch");
    }
    last_pc.chosen_color = Some(color);
    add_color(&mut ap.bonus, color, card.bonus_count);

    state.pending_ability = None;
    resolve_abilities(state, &card, active)
}

/// Steal one token of `color` from the opponent.
fn apply_choose_steal_token(state: &GameState, color: Color) -> Result<GameState, &'static str> {
    if state.pending_ability != Some(Ability::STEAL_TOKEN) {
        return Err("not in steal token phase");
    }

    let active = state.current_player;
    let opponent = 1 - active;
    if state.players[opponent].tokens.count(color) == 0 {
        return Err("opponent has no tokens to steal");
    }

    let mut state = state.clone();
    sub_color(&mut state.players[opponent].tokens, color, 1);
    add_color(&mut state.players[active].tokens, color, 1);
    state.pending_ability = None;
    end_of_turn(state, active, false)
}

/// Take the matching token from the board (`TAKE_MATCHING_TOKEN` ability).
fn apply_choose_matching_token(state: &GameState, index: usize) -> Result<GameState, &'static str> {
    if state.pending_ability != Some(Ability::TAKE_MATCHING_TOKEN) {
        return Err("not in take matching token phase");
    }
    let active = state.current_player;
    let Some(pending) = state.pending_buy.clone() else {
        return Err("no pending card for take matching token");
    };
    let Some(bonus_color) = pending.card.bonus else {
        return Err("card has no bonus color");
    };
    if index >= BOARD_SIZE {
        return Err("invalid board index");
    }
    if state.board[index] != Some(bonus_color) {
        return Err("no matching token at index");
    }

    let mut state = state.clone();
    state.board[index] = None;
    add_color(&mut state.players[active].tokens, bonus_color, 1);
    state.pending_ability = None;
    state.pending_buy = None;
    end_of_turn(state, active, false)
}

/// Grant the chosen royal (prestige only), resolve its ability, end the turn.
fn apply_choose_royal(state: &GameState, royal_id: &str) -> Result<GameState, &'static str> {
    let active = state.current_player;
    let Some(pos) = state
        .royals_available
        .iter()
        .position(|royal| royal.id == royal_id)
    else {
        return Err("royal not available");
    };

    let mut state = state.clone();
    let royal = state.royals_available.remove(pos);
    state.players[active].prestige += u32::from(royal.points);

    match royal.ability {
        Some(Ability::STEAL_TOKEN) => {
            if has_stealable_tokens(&state, active) {
                state.phase = Phase::STEAL_TOKEN;
                state.pending_ability = Some(Ability::STEAL_TOKEN);
                Ok(state)
            } else {
                end_of_turn(state, active, false)
            }
        }
        Some(Ability::PRIVILEGE) => {
            grant_privilege(&mut state, active);
            end_of_turn(state, active, false)
        }
        Some(Ability::EXTRA_TURN) => end_of_turn(state, active, true),
        _ => end_of_turn(state, active, false),
    }
}

/// Run the end-of-turn sequence for `active` (spec §End of turn and victory).
///
/// Order: abilities and royals have already resolved, so this performs the
/// deferred royal pick, then discard (if over the token limit), then the win
/// check, then hands the turn over (or keeps it on an extra turn).
fn end_of_turn(
    mut state: GameState,
    active: usize,
    extra_turn: bool,
) -> Result<GameState, &'static str> {
    state.current_player = active;
    state.pending_buy = None;
    state.pending_reserve = None;
    state.pending_ability = None;

    // Deferred royal pick (multicolor purchase that crossed a crown threshold):
    // abilities have resolved by now. The flag is one-shot; clear it whether or
    // not royals remain available.
    if state.pending_royal {
        state.pending_royal = false;
        if !state.royals_available.is_empty() {
            state.phase = Phase::CHOOSE_ROYAL;
            return Ok(state);
        }
    }

    if u32::from(state.players[active].tokens.total()) > helpers::TOKEN_LIMIT {
        // Defer the win check until after the discard; `extra_turn` carries the
        // pending seat decision across the DISCARD decision point.
        state.phase = Phase::DISCARD;
        state.extra_turn = extra_turn;
        return Ok(state);
    }

    finish_turn(state, active, extra_turn)
}

/// Check victory, then end the turn (an extra turn keeps the seat).
fn finish_turn(
    mut state: GameState,
    active: usize,
    extra_turn: bool,
) -> Result<GameState, &'static str> {
    if helpers::is_winner(&state.players[active]) {
        state.winner = Some(active);
        state.current_player = active;
        state.phase = Phase::GAME_OVER;
        state.extra_turn = false;
        return Ok(state);
    }
    if extra_turn {
        state.current_player = active;
        state.phase = Phase::USE_PRIVILEGES;
        state.extra_turn = true;
    } else {
        state.current_player = 1 - active;
        state.phase = Phase::USE_PRIVILEGES;
        state.extra_turn = false;
    }
    Ok(state)
}
