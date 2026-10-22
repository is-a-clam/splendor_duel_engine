//! Card data and types.

use crate::colors::{Color, Tokens, GEM_COLORS};
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::fmt;

/// A printed card ability; values match the keys in `cards.json`.
#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Ability {
    EXTRA_TURN,
    TAKE_MATCHING_TOKEN,
    STEAL_TOKEN,
    PRIVILEGE,
}

impl Ability {
    /// Return the lowercase string value matching `cards.json`.
    pub fn value(&self) -> &'static str {
        match self {
            Ability::EXTRA_TURN => "extra_turn",
            Ability::TAKE_MATCHING_TOKEN => "take_matching_token",
            Ability::STEAL_TOKEN => "steal_token",
            Ability::PRIVILEGE => "privilege",
        }
    }

    /// Parse an ability from its lowercase string value.
    pub fn from_value(s: &str) -> Option<Ability> {
        match s {
            "extra_turn" => Some(Ability::EXTRA_TURN),
            "take_matching_token" => Some(Ability::TAKE_MATCHING_TOKEN),
            "steal_token" => Some(Ability::STEAL_TOKEN),
            "privilege" => Some(Ability::PRIVILEGE),
            _ => None,
        }
    }
}

impl fmt::Display for Ability {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.value())
    }
}

/// A jewel card.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Card {
    pub id: String,
    pub level: u8,
    pub points: u8,
    pub crowns: u8,
    pub bonus: Option<Color>,
    pub bonus_count: u8,
    pub ability: Option<Ability>,
    pub is_multicolor: bool,
    pub cost: Tokens,
}

/// A royal card: prestige and at most one ability, never a colour.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RoyalCard {
    pub id: String,
    pub points: u8,
    pub ability: Option<Ability>,
}

/// Embedded card data JSON.
const CARDS_JSON: &str = include_str!("../../data/cards.json");

/// Expected counts for validation (matching Python engine/cards.py).
const EXPECTED_JEWEL_CARDS: usize = 67;
const EXPECTED_LEVEL_COUNTS: [(u8, usize); 3] = [(1, 30), (2, 24), (3, 13)];
const EXPECTED_TOTAL_CROWNS: u32 = 28;
const EXPECTED_TOTAL_POINTS: u32 = 92;
const EXPECTED_MULTICOLOR_CARDS: usize = 9;
const EXPECTED_ROYAL_CARDS: usize = 4;

/// Raw JSON structure for deserialization.
#[derive(Deserialize)]
struct CardsFile {
    jewel_cards: Vec<RawJewelCard>,
    royal_cards: Vec<RawRoyalCard>,
}

#[derive(Deserialize)]
struct RawJewelCard {
    id: String,
    level: u8,
    points: u8,
    crowns: u8,
    bonus: Option<String>, // "joker" or color string or null
    bonus_count: u8,
    ability: Option<String>,
    cost: Tokens,
}

#[derive(Deserialize)]
struct RawRoyalCard {
    id: String,
    points: u8,
    ability: Option<String>,
}

/// Load and validate the card data.
/// Returns `(jewel_cards, royal_cards)` in file order.
/// Raises `PyValueError` on any validation failure.
pub fn load_cards() -> PyResult<(Vec<Card>, Vec<RoyalCard>)> {
    let raw: CardsFile = serde_json::from_str(CARDS_JSON)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("Invalid JSON: {}", e)))?;

    // Parse jewel cards
    let mut jewels = Vec::with_capacity(raw.jewel_cards.len());
    let mut seen_ids = std::collections::HashSet::new();

    for entry in raw.jewel_cards {
        // Check duplicate IDs
        if !seen_ids.insert(entry.id.clone()) {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "duplicate card id {:?}",
                entry.id
            )));
        }

        let card = parse_jewel_card(entry)?;
        jewels.push(card);
    }

    // Parse royal cards
    let mut royals = Vec::with_capacity(raw.royal_cards.len());
    seen_ids.clear();

    for entry in raw.royal_cards {
        if !seen_ids.insert(entry.id.clone()) {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "duplicate royal card id {:?}",
                entry.id
            )));
        }

        let royal = parse_royal_card(entry)?;
        royals.push(royal);
    }

    // Validate jewel deck
    validate_jewel_deck(&jewels)?;

    // Validate royal count
    if royals.len() != EXPECTED_ROYAL_CARDS {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "expected {} royal cards, got {}",
            EXPECTED_ROYAL_CARDS,
            royals.len()
        )));
    }

    Ok((jewels, royals))
}

fn parse_jewel_card(entry: RawJewelCard) -> PyResult<Card> {
    let where_str = format!("card {}", entry.id);

    // Validate level
    if entry.level < 1 || entry.level > 3 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "{}: level must be 1, 2 or 3, got {}",
            where_str, entry.level
        )));
    }

    // Parse bonus and is_multicolor
    let (bonus, is_multicolor) = parse_bonus(entry.bonus, &where_str)?;

    // Validate bonus_count vs bonus/is_multicolor
    if is_multicolor {
        if bonus.is_some() {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "{}: multicolor card must have no bonus",
                where_str
            )));
        }
        if entry.bonus_count < 1 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "{}: multicolor card must have bonus_count >= 1, got {}",
                where_str, entry.bonus_count
            )));
        }
    } else if bonus.is_none() {
        if entry.bonus_count != 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "{}: colorless card must have bonus_count 0, got {}",
                where_str, entry.bonus_count
            )));
        }
    } else if entry.bonus_count < 1 {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "{}: card with a {:?} bonus must have bonus_count >= 1",
            where_str,
            bonus.unwrap().value()
        )));
    }

    // Parse ability
    let ability = parse_ability(entry.ability, &where_str)?;

    Ok(Card {
        id: entry.id,
        level: entry.level,
        points: entry.points,
        crowns: entry.crowns,
        bonus,
        bonus_count: entry.bonus_count,
        ability,
        is_multicolor,
        cost: entry.cost,
    })
}

fn parse_royal_card(entry: RawRoyalCard) -> PyResult<RoyalCard> {
    let where_str = format!("royal {}", entry.id);
    let ability = parse_ability(entry.ability, &where_str)?;
    Ok(RoyalCard {
        id: entry.id,
        points: entry.points,
        ability,
    })
}

fn parse_bonus(value: Option<String>, where_str: &str) -> PyResult<(Option<Color>, bool)> {
    match value.as_deref() {
        None => Ok((None, false)),
        Some("joker") => Ok((None, true)),
        Some(s) => {
            let bonus = Color::from_value(s).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("{}: unknown bonus {:?}", where_str, s))
            })?;
            if !GEM_COLORS.contains(&bonus) {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "{}: bonus must be a gem color, got {:?}",
                    where_str, s
                )));
            }
            Ok((Some(bonus), false))
        }
    }
}

fn parse_ability(value: Option<String>, where_str: &str) -> PyResult<Option<Ability>> {
    match value.as_deref() {
        None => Ok(None),
        Some(s) => {
            let ability = Ability::from_value(s).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("{}: unknown ability {:?}", where_str, s))
            })?;
            Ok(Some(ability))
        }
    }
}

fn validate_jewel_deck(jewels: &[Card]) -> PyResult<()> {
    if jewels.len() != EXPECTED_JEWEL_CARDS {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "expected {} jewel cards, got {}",
            EXPECTED_JEWEL_CARDS,
            jewels.len()
        )));
    }

    for (level, expected) in EXPECTED_LEVEL_COUNTS {
        let actual = jewels.iter().filter(|c| c.level == level).count();
        if actual != expected {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "expected {} level-{} jewel cards, got {}",
                expected, level, actual
            )));
        }
    }

    let total_crowns: u32 = jewels.iter().map(|c| c.crowns as u32).sum();
    if total_crowns != EXPECTED_TOTAL_CROWNS {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "expected {} total jewel crowns, got {}",
            EXPECTED_TOTAL_CROWNS, total_crowns
        )));
    }

    let total_points: u32 = jewels.iter().map(|c| c.points as u32).sum();
    if total_points != EXPECTED_TOTAL_POINTS {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "expected {} total jewel prestige points, got {}",
            EXPECTED_TOTAL_POINTS, total_points
        )));
    }

    let multicolor = jewels.iter().filter(|c| c.is_multicolor).count();
    if multicolor != EXPECTED_MULTICOLOR_CARDS {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "expected {} multicolor jewel cards, got {}",
            EXPECTED_MULTICOLOR_CARDS, multicolor
        )));
    }

    Ok(())
}