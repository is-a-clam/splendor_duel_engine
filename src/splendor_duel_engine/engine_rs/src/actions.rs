//! Game actions and the legal-action mask.
//!
//! Mirrors `engine/actions.py` one-for-one. The action enum is the pure-Rust
//! counterpart of the Python dataclasses; `py.rs` wraps each variant in a
//! `#[pyclass]` for the boundary. Everything here is a pure function of the
//! state: no heuristics, no RNG.

use crate::cards::{Ability, Card};
use crate::colors::{Color, Tokens, GEM_COLORS};
use crate::helpers;
use crate::phase::Phase;
use crate::state::GameState;
use std::collections::HashSet;

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
