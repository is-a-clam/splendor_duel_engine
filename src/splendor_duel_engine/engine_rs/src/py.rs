//! PyO3 wrapper types.

use crate::cards::{Ability, Card, RoyalCard};
use crate::colors::{Color, Tokens};
use crate::phase::Phase;
use crate::rng;
use pyo3::prelude::*;
use pyo3::types::PyList;

#[pyclass(name = "Random", module = "splendor_duel_engine._core")]
#[derive(Clone)]
pub struct PyRandom {
    pub inner: rng::Random,
}

#[pymethods]
impl PyRandom {
    #[new]
    fn new(seed: i64) -> Self {
        Self {
            inner: rng::Random::from_seed(seed),
        }
    }

    fn getrandbits(&mut self, k: u32) -> u32 {
        assert!(k >= 1 && k <= 32, "k must be in 1..=32");
        self.inner.getrandbits(k)
    }

    fn randbelow(&mut self, n: u32) -> PyResult<u32> {
        if n == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "empty range for randrange()",
            ));
        }
        Ok(self.inner.randbelow(n))
    }

    fn randrange(&mut self, n: u32) -> PyResult<u32> {
        if n == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "empty range for randrange()",
            ));
        }
        Ok(self.inner.randrange(n))
    }

    fn shuffle(&mut self, items: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = items.cast::<PyList>()?;
        let len: usize = list.len();
        let mut objs: Vec<Bound<'_, PyAny>> = Vec::with_capacity(len);
        for i in 0..len {
            objs.push(list.get_item(i)?);
        }
        self.inner.shuffle(&mut objs);
        for (i, obj) in objs.into_iter().enumerate() {
            list.set_item(i, obj)?;
        }
        Ok(())
    }

    fn copy(&self) -> PyRandom {
        self.clone()
    }
}

/// Color enum - fieldless enum for PyO3 to expose variants as class attributes.
#[allow(non_camel_case_types)]
#[pyclass(eq, frozen, name = "Color", module = "splendor_duel_engine._core")]
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub enum PyColor {
    WHITE,
    BLUE,
    GREEN,
    RED,
    BLACK,
    PEARL,
    GOLD,
}

impl PyColor {
    pub fn inner(&self) -> Color {
        match self {
            PyColor::WHITE => Color::WHITE,
            PyColor::BLUE => Color::BLUE,
            PyColor::GREEN => Color::GREEN,
            PyColor::RED => Color::RED,
            PyColor::BLACK => Color::BLACK,
            PyColor::PEARL => Color::PEARL,
            PyColor::GOLD => Color::GOLD,
        }
    }

    pub fn from_inner(color: Color) -> PyColor {
        match color {
            Color::WHITE => PyColor::WHITE,
            Color::BLUE => PyColor::BLUE,
            Color::GREEN => PyColor::GREEN,
            Color::RED => PyColor::RED,
            Color::BLACK => PyColor::BLACK,
            Color::PEARL => PyColor::PEARL,
            Color::GOLD => PyColor::GOLD,
        }
    }
}

#[pymethods]
impl PyColor {
    #[getter]
    fn value(&self) -> &'static str {
        self.inner().value()
    }

    #[staticmethod]
    fn from_value(s: &str) -> PyResult<PyColor> {
        Color::from_value(s)
            .map(PyColor::from_inner)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("invalid color: {}", s)))
    }

    fn __repr__(&self) -> String {
        format!("Color.{}", match self {
            PyColor::WHITE => "WHITE",
            PyColor::BLUE => "BLUE",
            PyColor::GREEN => "GREEN",
            PyColor::RED => "RED",
            PyColor::BLACK => "BLACK",
            PyColor::PEARL => "PEARL",
            PyColor::GOLD => "GOLD",
        })
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }
}

/// Tokens struct wrapper.
#[pyclass(frozen, eq, name = "Tokens", module = "splendor_duel_engine._core", get_all)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct PyTokens {
    pub white: u8,
    pub blue: u8,
    pub green: u8,
    pub red: u8,
    pub black: u8,
    pub pearl: u8,
    pub gold: u8,
}

impl From<Tokens> for PyTokens {
    fn from(t: Tokens) -> Self {
        PyTokens {
            white: t.white,
            blue: t.blue,
            green: t.green,
            red: t.red,
            black: t.black,
            pearl: t.pearl,
            gold: t.gold,
        }
    }
}

impl From<PyTokens> for Tokens {
    fn from(t: PyTokens) -> Self {
        Tokens {
            white: t.white,
            blue: t.blue,
            green: t.green,
            red: t.red,
            black: t.black,
            pearl: t.pearl,
            gold: t.gold,
        }
    }
}

#[pymethods]
impl PyTokens {
    #[new]
    #[pyo3(signature = (white=0, blue=0, green=0, red=0, black=0, pearl=0, gold=0))]
    fn new(
        white: u8,
        blue: u8,
        green: u8,
        red: u8,
        black: u8,
        pearl: u8,
        gold: u8,
    ) -> Self {
        PyTokens {
            white,
            blue,
            green,
            red,
            black,
            pearl,
            gold,
        }
    }

    fn count(&self, color: &PyColor) -> u8 {
        match color.inner() {
            Color::WHITE => self.white,
            Color::BLUE => self.blue,
            Color::GREEN => self.green,
            Color::RED => self.red,
            Color::BLACK => self.black,
            Color::PEARL => self.pearl,
            Color::GOLD => self.gold,
        }
    }

    fn total(&self) -> u8 {
        self.white + self.blue + self.green + self.red + self.black + self.pearl + self.gold
    }

    fn __add__(&self, other: &PyTokens) -> PyTokens {
        PyTokens {
            white: self.white.wrapping_add(other.white),
            blue: self.blue.wrapping_add(other.blue),
            green: self.green.wrapping_add(other.green),
            red: self.red.wrapping_add(other.red),
            black: self.black.wrapping_add(other.black),
            pearl: self.pearl.wrapping_add(other.pearl),
            gold: self.gold.wrapping_add(other.gold),
        }
    }

    fn __sub__(&self, other: &PyTokens) -> PyTokens {
        PyTokens {
            white: self.white.wrapping_sub(other.white),
            blue: self.blue.wrapping_sub(other.blue),
            green: self.green.wrapping_sub(other.green),
            red: self.red.wrapping_sub(other.red),
            black: self.black.wrapping_sub(other.black),
            pearl: self.pearl.wrapping_sub(other.pearl),
            gold: self.gold.wrapping_sub(other.gold),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "Tokens(white={}, blue={}, green={}, red={}, black={}, pearl={}, gold={})",
            self.white, self.blue, self.green, self.red, self.black, self.pearl, self.gold
        )
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }

    fn __hash__(&self) -> isize {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        (
            self.white,
            self.blue,
            self.green,
            self.red,
            self.black,
            self.pearl,
            self.gold,
        )
            .hash(&mut hasher);
        hasher.finish() as isize
    }
}

/// Ability enum - fieldless enum for PyO3 to expose variants as class attributes.
#[allow(non_camel_case_types)]
#[pyclass(eq, frozen, name = "Ability", module = "splendor_duel_engine._core")]
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub enum PyAbility {
    EXTRA_TURN,
    TAKE_MATCHING_TOKEN,
    STEAL_TOKEN,
    PRIVILEGE,
}

impl PyAbility {
    pub fn inner(&self) -> Ability {
        match self {
            PyAbility::EXTRA_TURN => Ability::EXTRA_TURN,
            PyAbility::TAKE_MATCHING_TOKEN => Ability::TAKE_MATCHING_TOKEN,
            PyAbility::STEAL_TOKEN => Ability::STEAL_TOKEN,
            PyAbility::PRIVILEGE => Ability::PRIVILEGE,
        }
    }

    pub fn from_inner(ability: Ability) -> PyAbility {
        match ability {
            Ability::EXTRA_TURN => PyAbility::EXTRA_TURN,
            Ability::TAKE_MATCHING_TOKEN => PyAbility::TAKE_MATCHING_TOKEN,
            Ability::STEAL_TOKEN => PyAbility::STEAL_TOKEN,
            Ability::PRIVILEGE => PyAbility::PRIVILEGE,
        }
    }
}

#[pymethods]
impl PyAbility {
    #[getter]
    fn value(&self) -> &'static str {
        self.inner().value()
    }

    #[staticmethod]
    fn from_value(s: &str) -> PyResult<PyAbility> {
        Ability::from_value(s)
            .map(PyAbility::from_inner)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("invalid ability: {}", s)))
    }

    fn __repr__(&self) -> String {
        format!("Ability.{}", match self {
            PyAbility::EXTRA_TURN => "EXTRA_TURN",
            PyAbility::TAKE_MATCHING_TOKEN => "TAKE_MATCHING_TOKEN",
            PyAbility::STEAL_TOKEN => "STEAL_TOKEN",
            PyAbility::PRIVILEGE => "PRIVILEGE",
        })
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }
}

/// Phase enum - fieldless enum for PyO3 to expose variants as class attributes.
#[allow(non_camel_case_types)]
#[pyclass(eq, frozen, name = "Phase", module = "splendor_duel_engine._core")]
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub enum PyPhase {
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

impl PyPhase {
    pub fn inner(&self) -> Phase {
        match self {
            PyPhase::USE_PRIVILEGES => Phase::USE_PRIVILEGES,
            PyPhase::REPLENISH => Phase::REPLENISH,
            PyPhase::MANDATORY => Phase::MANDATORY,
            PyPhase::CHOOSE_PAYMENT => Phase::CHOOSE_PAYMENT,
            PyPhase::CHOOSE_GOLD => Phase::CHOOSE_GOLD,
            PyPhase::MULTICOLOR_COLOR => Phase::MULTICOLOR_COLOR,
            PyPhase::STEAL_TOKEN => Phase::STEAL_TOKEN,
            PyPhase::TAKE_MATCHING_TOKEN => Phase::TAKE_MATCHING_TOKEN,
            PyPhase::CHOOSE_ROYAL => Phase::CHOOSE_ROYAL,
            PyPhase::DISCARD => Phase::DISCARD,
            PyPhase::GAME_OVER => Phase::GAME_OVER,
        }
    }

    pub fn from_inner(phase: Phase) -> PyPhase {
        match phase {
            Phase::USE_PRIVILEGES => PyPhase::USE_PRIVILEGES,
            Phase::REPLENISH => PyPhase::REPLENISH,
            Phase::MANDATORY => PyPhase::MANDATORY,
            Phase::CHOOSE_PAYMENT => PyPhase::CHOOSE_PAYMENT,
            Phase::CHOOSE_GOLD => PyPhase::CHOOSE_GOLD,
            Phase::MULTICOLOR_COLOR => PyPhase::MULTICOLOR_COLOR,
            Phase::STEAL_TOKEN => PyPhase::STEAL_TOKEN,
            Phase::TAKE_MATCHING_TOKEN => PyPhase::TAKE_MATCHING_TOKEN,
            Phase::CHOOSE_ROYAL => PyPhase::CHOOSE_ROYAL,
            Phase::DISCARD => PyPhase::DISCARD,
            Phase::GAME_OVER => PyPhase::GAME_OVER,
        }
    }
}

#[pymethods]
impl PyPhase {
    #[getter]
    fn value(&self) -> &'static str {
        self.inner().value()
    }

    #[staticmethod]
    fn from_value(s: &str) -> PyResult<PyPhase> {
        Phase::from_value(s)
            .map(PyPhase::from_inner)
            .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(format!("invalid phase: {}", s)))
    }

    fn __repr__(&self) -> String {
        format!("Phase.{}", match self {
            PyPhase::USE_PRIVILEGES => "USE_PRIVILEGES",
            PyPhase::REPLENISH => "REPLENISH",
            PyPhase::MANDATORY => "MANDATORY",
            PyPhase::CHOOSE_PAYMENT => "CHOOSE_PAYMENT",
            PyPhase::CHOOSE_GOLD => "CHOOSE_GOLD",
            PyPhase::MULTICOLOR_COLOR => "MULTICOLOR_COLOR",
            PyPhase::STEAL_TOKEN => "STEAL_TOKEN",
            PyPhase::TAKE_MATCHING_TOKEN => "TAKE_MATCHING_TOKEN",
            PyPhase::CHOOSE_ROYAL => "CHOOSE_ROYAL",
            PyPhase::DISCARD => "DISCARD",
            PyPhase::GAME_OVER => "GAME_OVER",
        })
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }
}

/// Card wrapper.
#[pyclass(frozen, eq, name = "Card", module = "splendor_duel_engine._core", get_all)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyCard {
    pub id: String,
    pub level: u8,
    pub points: u8,
    pub crowns: u8,
    pub bonus: Option<PyColor>,
    pub bonus_count: u8,
    pub ability: Option<PyAbility>,
    pub is_multicolor: bool,
    pub cost: PyTokens,
}

impl From<Card> for PyCard {
    fn from(c: Card) -> Self {
        PyCard {
            id: c.id,
            level: c.level,
            points: c.points,
            crowns: c.crowns,
            bonus: c.bonus.map(PyColor::from_inner),
            bonus_count: c.bonus_count,
            ability: c.ability.map(PyAbility::from_inner),
            is_multicolor: c.is_multicolor,
            cost: c.cost.into(),
        }
    }
}

#[pymethods]
impl PyCard {
    #[new]
    #[pyo3(signature = (id, level, points, crowns, bonus, bonus_count, ability, is_multicolor, cost))]
    fn new(
        id: String,
        level: u8,
        points: u8,
        crowns: u8,
        bonus: Option<&PyColor>,
        bonus_count: u8,
        ability: Option<&PyAbility>,
        is_multicolor: bool,
        cost: &PyTokens,
    ) -> Self {
        PyCard {
            id,
            level,
            points,
            crowns,
            bonus: bonus.cloned(),
            bonus_count,
            ability: ability.cloned(),
            is_multicolor,
            cost: cost.clone(),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "Card(id={:?}, level={}, points={}, crowns={}, bonus={:?}, bonus_count={}, ability={:?}, is_multicolor={}, cost={:?})",
            self.id, self.level, self.points, self.crowns,
            self.bonus.as_ref().map(|c| c.inner().value()),
            self.bonus_count,
            self.ability.as_ref().map(|a| a.inner().value()),
            self.is_multicolor,
            self.cost
        )
    }
}

/// RoyalCard wrapper.
#[pyclass(frozen, eq, name = "RoyalCard", module = "splendor_duel_engine._core", get_all)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyRoyalCard {
    pub id: String,
    pub points: u8,
    pub ability: Option<PyAbility>,
}

impl From<RoyalCard> for PyRoyalCard {
    fn from(r: RoyalCard) -> Self {
        PyRoyalCard {
            id: r.id,
            points: r.points,
            ability: r.ability.map(PyAbility::from_inner),
        }
    }
}

#[pymethods]
impl PyRoyalCard {
    #[new]
    #[pyo3(signature = (id, points, ability))]
    fn new(id: String, points: u8, ability: Option<&PyAbility>) -> Self {
        PyRoyalCard {
            id,
            points,
            ability: ability.cloned(),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "RoyalCard(id={:?}, points={}, ability={:?})",
            self.id, self.points, self.ability.as_ref().map(|a| a.inner().value())
        )
    }
}