//! Phase enum.

use serde::{Deserialize, Serialize};
use std::fmt;

/// Game phases as defined by the spec.
#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Phase {
    USE_PRIVILEGES,
    REPLENISH,
    MANDATORY,
    CHOOSE_PAYMENT,
    CHOOSE_GOLD,
    MULTICOLOR_COLOR,
    STEAL_TOKEN,
    TAKE_MATCHING_TOKEN,
    CHOOSE_ROYAL,
    DISCARD,
    GAME_OVER,
}

impl Phase {
    /// Return the lowercase string value matching the Python enum.
    pub fn value(&self) -> &'static str {
        match self {
            Phase::USE_PRIVILEGES => "use_privileges",
            Phase::REPLENISH => "replenish",
            Phase::MANDATORY => "mandatory",
            Phase::CHOOSE_PAYMENT => "choose_payment",
            Phase::CHOOSE_GOLD => "choose_gold",
            Phase::MULTICOLOR_COLOR => "multicolor_color",
            Phase::STEAL_TOKEN => "steal_token",
            Phase::TAKE_MATCHING_TOKEN => "take_matching_token",
            Phase::CHOOSE_ROYAL => "choose_royal",
            Phase::DISCARD => "discard",
            Phase::GAME_OVER => "game_over",
        }
    }

    /// Parse a phase from its lowercase string value.
    pub fn from_value(s: &str) -> Option<Phase> {
        match s {
            "use_privileges" => Some(Phase::USE_PRIVILEGES),
            "replenish" => Some(Phase::REPLENISH),
            "mandatory" => Some(Phase::MANDATORY),
            "choose_payment" => Some(Phase::CHOOSE_PAYMENT),
            "choose_gold" => Some(Phase::CHOOSE_GOLD),
            "multicolor_color" => Some(Phase::MULTICOLOR_COLOR),
            "steal_token" => Some(Phase::STEAL_TOKEN),
            "take_matching_token" => Some(Phase::TAKE_MATCHING_TOKEN),
            "choose_royal" => Some(Phase::CHOOSE_ROYAL),
            "discard" => Some(Phase::DISCARD),
            "game_over" => Some(Phase::GAME_OVER),
            _ => None,
        }
    }
}

impl fmt::Display for Phase {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.value())
    }
}