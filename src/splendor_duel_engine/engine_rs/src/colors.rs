//! Color enum and Tokens struct.

use serde::{Deserialize, Serialize};
use std::fmt;

/// A token and bonus color; values match the keys in `cards.json`.
#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Color {
    WHITE,
    BLUE,
    GREEN,
    RED,
    BLACK,
    PEARL,
    GOLD,
}

impl Color {
    /// Return the lowercase string value matching `cards.json`.
    pub fn value(&self) -> &'static str {
        match self {
            Color::WHITE => "white",
            Color::BLUE => "blue",
            Color::GREEN => "green",
            Color::RED => "red",
            Color::BLACK => "black",
            Color::PEARL => "pearl",
            Color::GOLD => "gold",
        }
    }

    /// Parse a color from its lowercase string value.
    pub fn from_value(s: &str) -> Option<Color> {
        match s {
            "white" => Some(Color::WHITE),
            "blue" => Some(Color::BLUE),
            "green" => Some(Color::GREEN),
            "red" => Some(Color::RED),
            "black" => Some(Color::BLACK),
            "pearl" => Some(Color::PEARL),
            "gold" => Some(Color::GOLD),
            _ => None,
        }
    }
}

impl fmt::Display for Color {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.value())
    }
}

/// The five gem colors. Pearls and gold are tokens but never card bonuses.
pub const GEM_COLORS: [Color; 5] = [
    Color::WHITE,
    Color::BLUE,
    Color::GREEN,
    Color::RED,
    Color::BLACK,
];

/// An immutable, hashable count of tokens, one field per color.
#[derive(Clone, Copy, Default, PartialEq, Eq, Hash, Serialize)]
pub struct Tokens {
    pub white: u8,
    pub blue: u8,
    pub green: u8,
    pub red: u8,
    pub black: u8,
    pub pearl: u8,
    pub gold: u8,
}

impl Tokens {
    /// Create a new Tokens with all counts zero.
    pub const fn new() -> Self {
        Tokens {
            white: 0,
            blue: 0,
            green: 0,
            red: 0,
            black: 0,
            pearl: 0,
            gold: 0,
        }
    }

    /// Return how many tokens of `color` are held.
    pub fn count(&self, color: Color) -> u8 {
        match color {
            Color::WHITE => self.white,
            Color::BLUE => self.blue,
            Color::GREEN => self.green,
            Color::RED => self.red,
            Color::BLACK => self.black,
            Color::PEARL => self.pearl,
            Color::GOLD => self.gold,
        }
    }

    /// Return the total number of tokens held across all colors.
    pub fn total(&self) -> u8 {
        self.white
            + self.blue
            + self.green
            + self.red
            + self.black
            + self.pearl
            + self.gold
    }

    /// Plain addition of two Tokens.
    pub fn add(&self, other: Tokens) -> Tokens {
        Tokens {
            white: self.white + other.white,
            blue: self.blue + other.blue,
            green: self.green + other.green,
            red: self.red + other.red,
            black: self.black + other.black,
            pearl: self.pearl + other.pearl,
            gold: self.gold + other.gold,
        }
    }

    /// Plain subtraction of two Tokens. Does NOT saturate - can underflow.
    /// Matches Python's `Tokens.__sub__` behavior.
    pub fn sub(&self, other: Tokens) -> Tokens {
        Tokens {
            white: self.white.wrapping_sub(other.white),
            blue: self.blue.wrapping_sub(other.blue),
            green: self.green.wrapping_sub(other.green),
            red: self.red.wrapping_sub(other.red),
            black: self.black.wrapping_sub(other.black),
            pearl: self.pearl.wrapping_sub(other.pearl),
            gold: self.gold.wrapping_sub(other.gold),
        }
    }
}

impl fmt::Debug for Tokens {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Tokens")
            .field("white", &self.white)
            .field("blue", &self.blue)
            .field("green", &self.green)
            .field("red", &self.red)
            .field("black", &self.black)
            .field("pearl", &self.pearl)
            .field("gold", &self.gold)
            .finish()
    }
}

impl fmt::Display for Tokens {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Tokens(w={}, b={}, g={}, r={}, bl={}, p={}, g={})",
            self.white, self.blue, self.green, self.red, self.black, self.pearl, self.gold
        )
    }
}

impl std::ops::Add for Tokens {
    type Output = Tokens;
    fn add(self, other: Tokens) -> Tokens {
        self.add(other)
    }
}

impl std::ops::Sub for Tokens {
    type Output = Tokens;
    fn sub(self, other: Tokens) -> Tokens {
        self.sub(other)
    }
}

/// Serde deserialization for Tokens from the JSON cost object.
impl<'de> Deserialize<'de> for Tokens {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        #[derive(Deserialize)]
        struct TokenFields {
            white: Option<u8>,
            blue: Option<u8>,
            green: Option<u8>,
            red: Option<u8>,
            black: Option<u8>,
            pearl: Option<u8>,
            #[serde(default)]
            gold: Option<u8>,
        }
        let fields = TokenFields::deserialize(deserializer)?;
        Ok(Tokens {
            white: fields.white.unwrap_or(0),
            blue: fields.blue.unwrap_or(0),
            green: fields.green.unwrap_or(0),
            red: fields.red.unwrap_or(0),
            black: fields.black.unwrap_or(0),
            pearl: fields.pearl.unwrap_or(0),
            gold: fields.gold.unwrap_or(0),
        })
    }
}