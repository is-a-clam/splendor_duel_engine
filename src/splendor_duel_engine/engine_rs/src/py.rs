//! PyO3 wrapper types.

use crate::actions::{apply as actions_apply, decide as actions_decide, Action};
use crate::cards::{Ability, Card, RoyalCard};
use crate::colors::{Color, Tokens};
use crate::helpers as rule_helpers;
use crate::observation::{observation as state_observation, Observation, PlayerView};
use crate::phase::Phase;
use crate::rng;
use crate::state::{
    new_game as state_new_game, BuyCard, GameState, PlayerState, PurchasedCard, ReserveCard,
    ReservedCard,
};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::rc::Rc;

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
#[pyclass(
    eq,
    hash,
    frozen,
    name = "Color",
    module = "splendor_duel_engine._core",
    from_py_object
)]
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

impl From<&PyColor> for Color {
    fn from(c: &PyColor) -> Self {
        c.inner()
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
        format!(
            "Color.{}",
            match self {
                PyColor::WHITE => "WHITE",
                PyColor::BLUE => "BLUE",
                PyColor::GREEN => "GREEN",
                PyColor::RED => "RED",
                PyColor::BLACK => "BLACK",
                PyColor::PEARL => "PEARL",
                PyColor::GOLD => "GOLD",
            }
        )
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }
}

/// Tokens struct wrapper.
#[pyclass(
    frozen,
    eq,
    name = "Tokens",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
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

impl From<&PyTokens> for Tokens {
    fn from(t: &PyTokens) -> Self {
        (*t).into()
    }
}

#[pymethods]
impl PyTokens {
    #[new]
    #[pyo3(signature = (white=0, blue=0, green=0, red=0, black=0, pearl=0, gold=0))]
    fn new(white: u8, blue: u8, green: u8, red: u8, black: u8, pearl: u8, gold: u8) -> Self {
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
            self.white, self.blue, self.green, self.red, self.black, self.pearl, self.gold,
        )
            .hash(&mut hasher);
        hasher.finish() as isize
    }
}

/// Ability enum - fieldless enum for PyO3 to expose variants as class attributes.
#[allow(non_camel_case_types)]
#[pyclass(
    eq,
    frozen,
    name = "Ability",
    module = "splendor_duel_engine._core",
    from_py_object
)]
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

impl From<&PyAbility> for Ability {
    fn from(a: &PyAbility) -> Self {
        a.inner()
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
            .ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("invalid ability: {}", s))
            })
    }

    fn __repr__(&self) -> String {
        format!(
            "Ability.{}",
            match self {
                PyAbility::EXTRA_TURN => "EXTRA_TURN",
                PyAbility::TAKE_MATCHING_TOKEN => "TAKE_MATCHING_TOKEN",
                PyAbility::STEAL_TOKEN => "STEAL_TOKEN",
                PyAbility::PRIVILEGE => "PRIVILEGE",
            }
        )
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }
}

/// Phase enum - fieldless enum for PyO3 to expose variants as class attributes.
#[allow(non_camel_case_types)]
#[pyclass(
    eq,
    frozen,
    name = "Phase",
    module = "splendor_duel_engine._core",
    from_py_object
)]
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

impl From<&PyPhase> for Phase {
    fn from(p: &PyPhase) -> Self {
        p.inner()
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
        format!(
            "Phase.{}",
            match self {
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
            }
        )
    }

    fn __str__(&self) -> String {
        self.__repr__()
    }
}

/// Card wrapper.
#[pyclass(
    frozen,
    eq,
    name = "Card",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
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

impl From<&Card> for PyCard {
    fn from(c: &Card) -> Self {
        c.clone().into()
    }
}

impl From<&PyCard> for Card {
    fn from(c: &PyCard) -> Self {
        Card {
            id: c.id.clone(),
            level: c.level,
            points: c.points,
            crowns: c.crowns,
            bonus: c.bonus.as_ref().map(|b| b.inner()),
            bonus_count: c.bonus_count,
            ability: c.ability.as_ref().map(|a| a.inner()),
            is_multicolor: c.is_multicolor,
            cost: (&c.cost).into(),
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
#[pyclass(
    frozen,
    eq,
    name = "RoyalCard",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
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

impl From<&RoyalCard> for PyRoyalCard {
    fn from(r: &RoyalCard) -> Self {
        r.clone().into()
    }
}

impl From<&PyRoyalCard> for RoyalCard {
    fn from(r: &PyRoyalCard) -> Self {
        RoyalCard {
            id: r.id.clone(),
            points: r.points,
            ability: r.ability.as_ref().map(|a| a.inner()),
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
            self.id,
            self.points,
            self.ability.as_ref().map(|a| a.inner().value())
        )
    }
}

/// BuyCard wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "BuyCard",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyBuyCard {
    pub card: PyCard,
    pub source: String,
}

impl From<BuyCard> for PyBuyCard {
    fn from(b: BuyCard) -> Self {
        PyBuyCard {
            card: b.card.into(),
            source: b.source,
        }
    }
}

impl From<&PyBuyCard> for BuyCard {
    fn from(b: &PyBuyCard) -> Self {
        BuyCard {
            card: (&b.card).into(),
            source: b.source.clone(),
        }
    }
}

#[pymethods]
impl PyBuyCard {
    #[new]
    #[pyo3(signature = (card, source))]
    fn new(card: &PyCard, source: String) -> Self {
        PyBuyCard {
            card: card.clone(),
            source,
        }
    }
}

/// ReserveCard wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "ReserveCard",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyReserveCard {
    pub source: String,
    pub index: usize,
}

impl From<ReserveCard> for PyReserveCard {
    fn from(r: ReserveCard) -> Self {
        PyReserveCard {
            source: r.source,
            index: r.index,
        }
    }
}

impl From<&PyReserveCard> for ReserveCard {
    fn from(r: &PyReserveCard) -> Self {
        ReserveCard {
            source: r.source.clone(),
            index: r.index,
        }
    }
}

#[pymethods]
impl PyReserveCard {
    #[new]
    #[pyo3(signature = (source, index))]
    fn new(source: String, index: usize) -> Self {
        PyReserveCard { source, index }
    }
}

/// PurchasedCard wrapper.
#[pyclass(
    frozen,
    eq,
    name = "PurchasedCard",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyPurchasedCard {
    pub card: PyCard,
    pub chosen_color: Option<PyColor>,
}

impl From<PurchasedCard> for PyPurchasedCard {
    fn from(p: PurchasedCard) -> Self {
        PyPurchasedCard {
            card: p.card.into(),
            chosen_color: p.chosen_color.map(PyColor::from_inner),
        }
    }
}

impl From<&PyPurchasedCard> for PurchasedCard {
    fn from(p: &PyPurchasedCard) -> Self {
        PurchasedCard {
            card: (&p.card).into(),
            chosen_color: p.chosen_color.as_ref().map(|c| c.inner()),
        }
    }
}

#[pymethods]
impl PyPurchasedCard {
    #[new]
    #[pyo3(signature = (card, chosen_color))]
    fn new(card: &PyCard, chosen_color: Option<&PyColor>) -> Self {
        PyPurchasedCard {
            card: card.clone(),
            chosen_color: chosen_color.cloned(),
        }
    }
}

/// ReservedCard wrapper.
#[pyclass(
    frozen,
    eq,
    name = "ReservedCard",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyReservedCard {
    pub card: PyCard,
    pub from_deck: bool,
}

impl From<ReservedCard> for PyReservedCard {
    fn from(r: ReservedCard) -> Self {
        PyReservedCard {
            card: r.card.into(),
            from_deck: r.from_deck,
        }
    }
}

impl From<&PyReservedCard> for ReservedCard {
    fn from(r: &PyReservedCard) -> Self {
        ReservedCard {
            card: (&r.card).into(),
            from_deck: r.from_deck,
        }
    }
}

#[pymethods]
impl PyReservedCard {
    #[new]
    #[pyo3(signature = (card, from_deck))]
    fn new(card: &PyCard, from_deck: bool) -> Self {
        PyReservedCard {
            card: card.clone(),
            from_deck,
        }
    }
}

/// PlayerState wrapper.
#[pyclass(
    frozen,
    eq,
    name = "PlayerState",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyPlayerState {
    pub tokens: PyTokens,
    pub bonus: PyTokens,
    pub prestige: u32,
    pub crowns: u32,
    pub reserved: Vec<PyReservedCard>,
    pub purchased: Vec<PyPurchasedCard>,
    pub privileges: u32,
}

impl From<PlayerState> for PyPlayerState {
    fn from(p: PlayerState) -> Self {
        PyPlayerState {
            tokens: p.tokens.into(),
            bonus: p.bonus.into(),
            prestige: p.prestige,
            crowns: p.crowns,
            reserved: p.reserved.into_iter().map(PyReservedCard::from).collect(),
            purchased: p.purchased.into_iter().map(PyPurchasedCard::from).collect(),
            privileges: p.privileges,
        }
    }
}

impl From<&PyPlayerState> for PlayerState {
    fn from(p: &PyPlayerState) -> Self {
        PlayerState {
            tokens: (&p.tokens).into(),
            bonus: (&p.bonus).into(),
            prestige: p.prestige,
            crowns: p.crowns,
            reserved: p.reserved.iter().map(ReservedCard::from).collect(),
            purchased: p.purchased.iter().map(PurchasedCard::from).collect(),
            privileges: p.privileges,
        }
    }
}

#[pymethods]
impl PyPlayerState {
    #[new]
    #[pyo3(signature = (tokens, bonus, prestige, crowns, reserved, purchased, privileges))]
    fn new(
        tokens: &PyTokens,
        bonus: &PyTokens,
        prestige: u32,
        crowns: u32,
        reserved: Vec<PyReservedCard>,
        purchased: Vec<PyPurchasedCard>,
        privileges: u32,
    ) -> Self {
        PyPlayerState {
            tokens: tokens.clone(),
            bonus: bonus.clone(),
            prestige,
            crowns,
            reserved,
            purchased,
            privileges,
        }
    }
}

/// PlayerView wrapper.
#[pyclass(
    frozen,
    eq,
    name = "PlayerView",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyPlayerView {
    pub tokens: PyTokens,
    pub bonus: PyTokens,
    pub prestige: u32,
    pub crowns: u32,
    pub reserved_public: Vec<PyCard>,
    pub reserved_deck_count: usize,
    pub purchased: Vec<PyPurchasedCard>,
    pub privileges: u32,
}

impl From<PlayerView> for PyPlayerView {
    fn from(v: PlayerView) -> Self {
        PyPlayerView {
            tokens: v.tokens.into(),
            bonus: v.bonus.into(),
            prestige: v.prestige,
            crowns: v.crowns,
            reserved_public: v.reserved_public.into_iter().map(PyCard::from).collect(),
            reserved_deck_count: v.reserved_deck_count,
            purchased: v.purchased.into_iter().map(PyPurchasedCard::from).collect(),
            privileges: v.privileges,
        }
    }
}

#[pymethods]
impl PyPlayerView {
    #[new]
    #[pyo3(signature = (tokens, bonus, prestige, crowns, reserved_public, reserved_deck_count, purchased, privileges))]
    fn new(
        tokens: &PyTokens,
        bonus: &PyTokens,
        prestige: u32,
        crowns: u32,
        reserved_public: Vec<PyCard>,
        reserved_deck_count: usize,
        purchased: Vec<PyPurchasedCard>,
        privileges: u32,
    ) -> Self {
        PyPlayerView {
            tokens: tokens.clone(),
            bonus: bonus.clone(),
            prestige,
            crowns,
            reserved_public,
            reserved_deck_count,
            purchased,
            privileges,
        }
    }
}

/// Observation wrapper.
#[pyclass(
    frozen,
    eq,
    name = "Observation",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyObservation {
    pub you: PyPlayerView,
    pub opponent: PyPlayerView,
    pub board: Vec<Option<PyColor>>,
    pub pyramid: Vec<Vec<Option<PyCard>>>,
    pub royals_available: Vec<PyRoyalCard>,
    pub privileges_supply: u32,
    pub deck_counts: (usize, usize, usize),
    pub bag: PyTokens,
    pub current_player: usize,
    pub winner: Option<usize>,
    pub your_reserved_deck: Vec<PyCard>,
    pub phase: PyPhase,
    pub pending_buy: Option<PyBuyCard>,
    pub pending_reserve: Option<PyReserveCard>,
    pub pending_ability: Option<PyAbility>,
    pub pending_royal: bool,
    pub extra_turn: bool,
}

impl From<Observation> for PyObservation {
    fn from(o: Observation) -> Self {
        PyObservation {
            you: o.you.into(),
            opponent: o.opponent.into(),
            board: o.board.iter().map(|c| c.map(PyColor::from_inner)).collect(),
            pyramid: o
                .pyramid
                .iter()
                .map(|row| row.iter().map(|c| c.as_ref().map(PyCard::from)).collect())
                .collect(),
            royals_available: o
                .royals_available
                .into_iter()
                .map(PyRoyalCard::from)
                .collect(),
            privileges_supply: o.privileges_supply,
            deck_counts: (o.deck_counts[0], o.deck_counts[1], o.deck_counts[2]),
            bag: o.bag.into(),
            current_player: o.current_player,
            winner: o.winner,
            your_reserved_deck: o.your_reserved_deck.into_iter().map(PyCard::from).collect(),
            phase: PyPhase::from_inner(o.phase),
            pending_buy: o.pending_buy.map(PyBuyCard::from),
            pending_reserve: o.pending_reserve.map(PyReserveCard::from),
            pending_ability: o.pending_ability.map(PyAbility::from_inner),
            pending_royal: o.pending_royal,
            extra_turn: o.extra_turn,
        }
    }
}

#[pymethods]
impl PyObservation {
    #[new]
    #[pyo3(signature = (you, opponent, board, pyramid, royals_available, privileges_supply, deck_counts, bag, current_player, winner, your_reserved_deck, phase, pending_buy, pending_reserve, pending_ability, pending_royal, extra_turn))]
    fn new(
        you: &PyPlayerView,
        opponent: &PyPlayerView,
        board: Vec<Option<PyColor>>,
        pyramid: Vec<Vec<Option<PyCard>>>,
        royals_available: Vec<PyRoyalCard>,
        privileges_supply: u32,
        deck_counts: (usize, usize, usize),
        bag: &PyTokens,
        current_player: usize,
        winner: Option<usize>,
        your_reserved_deck: Vec<PyCard>,
        phase: PyPhase,
        pending_buy: Option<&PyBuyCard>,
        pending_reserve: Option<&PyReserveCard>,
        pending_ability: Option<&PyAbility>,
        pending_royal: bool,
        extra_turn: bool,
    ) -> Self {
        PyObservation {
            you: you.clone(),
            opponent: opponent.clone(),
            board,
            pyramid,
            royals_available,
            privileges_supply,
            deck_counts,
            bag: bag.clone(),
            current_player,
            winner,
            your_reserved_deck,
            phase,
            pending_buy: pending_buy.cloned(),
            pending_reserve: pending_reserve.cloned(),
            pending_ability: pending_ability.cloned(),
            pending_royal,
            extra_turn,
        }
    }
}

/// GameState wrapper.
///
/// Takes `seed` in place of Python's `rng`: the determinizer builds a state
/// from sampled hidden information and supplies the seed, and the Rust
/// `GameState` derives its own RNG stream from it.
#[pyclass(unsendable, name = "GameState", module = "splendor_duel_engine._core")]
pub struct PyGameState {
    pub inner: GameState,
}

#[pymethods]
impl PyGameState {
    #[new]
    #[pyo3(signature = (players, board, bag, decks, pyramid, royals_available, privileges_supply, current_player, winner, phase, pending_buy, pending_reserve, seed, extra_turn=false, pending_ability=None, pending_royal=false))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        players: Vec<PyPlayerState>,
        board: Vec<Option<PyColor>>,
        bag: &PyTokens,
        decks: Vec<Vec<PyCard>>,
        pyramid: Vec<Vec<Option<PyCard>>>,
        royals_available: Vec<PyRoyalCard>,
        privileges_supply: u32,
        current_player: usize,
        winner: Option<usize>,
        phase: PyPhase,
        pending_buy: Option<&PyBuyCard>,
        pending_reserve: Option<&PyReserveCard>,
        seed: i64,
        extra_turn: bool,
        pending_ability: Option<&PyAbility>,
        pending_royal: bool,
    ) -> PyResult<Self> {
        let players: [PlayerState; 2] = players
            .iter()
            .map(PlayerState::from)
            .collect::<Vec<_>>()
            .try_into()
            .map_err(|_| pyo3::exceptions::PyValueError::new_err("players must have length 2"))?;

        let board: [Option<Color>; 25] = board
            .into_iter()
            .map(|c| c.map(|c| c.inner()))
            .collect::<Vec<_>>()
            .try_into()
            .map_err(|_| pyo3::exceptions::PyValueError::new_err("board must have length 25"))?;

        let decks: [Vec<Card>; 3] = decks
            .into_iter()
            .map(|deck| deck.iter().map(Card::from).collect())
            .collect::<Vec<_>>()
            .try_into()
            .map_err(|_| pyo3::exceptions::PyValueError::new_err("decks must have length 3"))?;

        let pyramid: [Vec<Option<Card>>; 3] = pyramid
            .into_iter()
            .map(|row| row.iter().map(|c| c.as_ref().map(Card::from)).collect())
            .collect::<Vec<_>>()
            .try_into()
            .map_err(|_| pyo3::exceptions::PyValueError::new_err("pyramid must have length 3"))?;

        Ok(PyGameState {
            inner: GameState {
                players,
                board,
                bag: bag.into(),
                decks,
                pyramid,
                royals_available: royals_available.iter().map(RoyalCard::from).collect(),
                privileges_supply,
                current_player,
                winner,
                phase: phase.inner(),
                pending_buy: pending_buy.map(BuyCard::from),
                pending_reserve: pending_reserve.map(ReserveCard::from),
                extra_turn,
                pending_ability: pending_ability.map(Ability::from),
                pending_royal,
                rng: Rc::new(rng::Random::from_seed(seed)),
            },
        })
    }

    #[getter]
    fn players(&self) -> [PyPlayerState; 2] {
        [
            self.inner.players[0].clone().into(),
            self.inner.players[1].clone().into(),
        ]
    }

    #[getter]
    fn board(&self) -> Vec<Option<PyColor>> {
        self.inner
            .board
            .iter()
            .map(|c| c.map(PyColor::from_inner))
            .collect()
    }

    #[getter]
    fn bag(&self) -> PyTokens {
        self.inner.bag.into()
    }

    #[getter]
    fn decks(&self) -> Vec<Vec<PyCard>> {
        self.inner
            .decks
            .iter()
            .map(|d| d.iter().map(PyCard::from).collect())
            .collect()
    }

    #[getter]
    fn pyramid(&self) -> Vec<Vec<Option<PyCard>>> {
        self.inner
            .pyramid
            .iter()
            .map(|row| row.iter().map(|c| c.as_ref().map(PyCard::from)).collect())
            .collect()
    }

    #[getter]
    fn royals_available(&self) -> Vec<PyRoyalCard> {
        self.inner
            .royals_available
            .iter()
            .map(PyRoyalCard::from)
            .collect()
    }

    #[getter]
    fn privileges_supply(&self) -> u32 {
        self.inner.privileges_supply
    }

    #[getter]
    fn current_player(&self) -> usize {
        self.inner.current_player
    }

    #[getter]
    fn winner(&self) -> Option<usize> {
        self.inner.winner
    }

    #[getter]
    fn phase(&self) -> PyPhase {
        PyPhase::from_inner(self.inner.phase)
    }

    #[getter]
    fn pending_buy(&self) -> Option<PyBuyCard> {
        self.inner.pending_buy.clone().map(PyBuyCard::from)
    }

    #[getter]
    fn pending_reserve(&self) -> Option<PyReserveCard> {
        self.inner.pending_reserve.clone().map(PyReserveCard::from)
    }

    #[getter]
    fn extra_turn(&self) -> bool {
        self.inner.extra_turn
    }

    #[getter]
    fn pending_ability(&self) -> Option<PyAbility> {
        self.inner.pending_ability.map(PyAbility::from_inner)
    }

    #[getter]
    fn pending_royal(&self) -> bool {
        self.inner.pending_royal
    }

    fn __repr__(&self) -> String {
        format!(
            "GameState(current_player={}, phase={:?}, winner={:?})",
            self.inner.current_player,
            self.inner.phase.value(),
            self.inner.winner
        )
    }
}

/// Create a fresh game set up deterministically from `seed`.
#[pyfunction]
pub fn new_game(seed: i64) -> PyGameState {
    PyGameState {
        inner: state_new_game(seed),
    }
}

/// Report missing tokens per colour after bonuses and payment.
///
/// Returns an insertion-ordered `dict[Color, int]`: gem colours in
/// `GEM_COLORS` order, then pearl, and only colours with a positive shortfall.
#[pyfunction]
pub fn cost_deficits<'py>(
    py: Python<'py>,
    cost: &PyTokens,
    bonus: &PyTokens,
    paid: &PyTokens,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new(py);
    for (colour, missing) in
        rule_helpers::cost_deficits((*cost).into(), (*bonus).into(), (*paid).into())
    {
        dict.set_item(PyColor::from_inner(colour), missing)?;
    }
    Ok(dict)
}

/// Return whether the player may buy this card right now.
#[pyfunction]
pub fn can_afford_card(card: &PyCard, tokens: &PyTokens, bonus: &PyTokens) -> bool {
    rule_helpers::can_afford_card(&Card::from(card), (*tokens).into(), (*bonus).into())
}

/// Enumerate legal payments for buying `card`, in the pinned loop order.
#[pyfunction]
pub fn legal_payments(card: &PyCard, tokens: &PyTokens, bonus: &PyTokens) -> Vec<PyTokens> {
    rule_helpers::legal_payments(&Card::from(card), (*tokens).into(), (*bonus).into())
        .into_iter()
        .map(PyTokens::from)
        .collect()
}

/// Return true if taking these colours triggers a penalty.
#[pyfunction]
pub fn take_penalty(colors: Vec<PyColor>) -> bool {
    let colors: Vec<Color> = colors.iter().map(PyColor::inner).collect();
    rule_helpers::take_penalty(&colors)
}

/// Sum card points for purchased cards of effective colour `color`.
#[pyfunction]
pub fn color_points(purchased: Vec<PyPurchasedCard>, color: &PyColor) -> u32 {
    let purchased: Vec<PurchasedCard> = purchased.iter().map(PurchasedCard::from).collect();
    rule_helpers::color_points(&purchased, color.inner())
}

/// Enumerate distinct discard subsets of `tokens` summing to `excess`.
#[pyfunction]
pub fn discard_subsets(tokens: &PyTokens, excess: i64) -> Vec<PyTokens> {
    rule_helpers::discard_subsets((*tokens).into(), excess)
        .into_iter()
        .map(PyTokens::from)
        .collect()
}

/// Return true if the player may reserve a card.
#[pyfunction]
pub fn can_reserve(board: Vec<Option<PyColor>>, reserved_count: i64) -> bool {
    let board: Vec<Option<Color>> = board
        .into_iter()
        .map(|colour| colour.map(|c| c.inner()))
        .collect();
    rule_helpers::can_reserve(&board, reserved_count)
}

/// Return all visible cards in contract order.
#[pyfunction]
pub fn visible_cards(
    pyramid: Vec<Vec<Option<PyCard>>>,
    reserved_public: Vec<PyCard>,
    reserved_deck: Vec<PyCard>,
) -> Vec<PyCard> {
    let pyramid: Vec<Vec<Option<Card>>> = pyramid
        .iter()
        .map(|row| row.iter().map(|c| c.as_ref().map(Card::from)).collect())
        .collect();
    let reserved_public: Vec<Card> = reserved_public.iter().map(Card::from).collect();
    let reserved_deck: Vec<Card> = reserved_deck.iter().map(Card::from).collect();
    rule_helpers::visible_cards(&pyramid, &reserved_public, &reserved_deck)
        .iter()
        .map(PyCard::from)
        .collect()
}

/// Return true if this player meets any win condition.
#[pyfunction]
pub fn is_winner(player: &PyPlayerState) -> bool {
    rule_helpers::is_winner(&PlayerState::from(player))
}

/// Create an observation from a GameState for a specific player.
#[pyfunction]
pub fn observation(state: &PyGameState, player: usize) -> PyResult<PyObservation> {
    if player > 1 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "player must be 0 or 1",
        ));
    }
    Ok(state_observation(&state.inner, player).into())
}

// ===== Action wrappers =====
//
// One `#[pyclass]` per action dataclass in `engine/actions.py`. `PyBuyCard`
// and `PyReserveCard` above double as the `BuyCard` and `ReserveCard` actions.
// Class names and field names must match Python exactly: `tests/rust/parity.py`
// fingerprints actions by `type(action).__name__` and attribute names.

/// UsePrivilege action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "UsePrivilege",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyUsePrivilege {
    pub index: usize,
}

#[pymethods]
impl PyUsePrivilege {
    #[new]
    #[pyo3(signature = (index))]
    fn new(index: usize) -> Self {
        PyUsePrivilege { index }
    }

    fn __repr__(&self) -> String {
        format!("UsePrivilege(index={})", self.index)
    }
}

/// DoneWithPrivileges action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "DoneWithPrivileges",
    module = "splendor_duel_engine._core",
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyDoneWithPrivileges {}

#[pymethods]
impl PyDoneWithPrivileges {
    #[new]
    fn new() -> Self {
        PyDoneWithPrivileges {}
    }

    fn __repr__(&self) -> String {
        "DoneWithPrivileges()".to_string()
    }
}

/// Replenish action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "Replenish",
    module = "splendor_duel_engine._core",
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyReplenish {}

#[pymethods]
impl PyReplenish {
    #[new]
    fn new() -> Self {
        PyReplenish {}
    }

    fn __repr__(&self) -> String {
        "Replenish()".to_string()
    }
}

/// DoneWithReplenish action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "DoneWithReplenish",
    module = "splendor_duel_engine._core",
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyDoneWithReplenish {}

#[pymethods]
impl PyDoneWithReplenish {
    #[new]
    fn new() -> Self {
        PyDoneWithReplenish {}
    }

    fn __repr__(&self) -> String {
        "DoneWithReplenish()".to_string()
    }
}

/// TakeTokens action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "TakeTokens",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyTakeTokens {
    pub line: Vec<usize>,
}

#[pymethods]
impl PyTakeTokens {
    #[new]
    #[pyo3(signature = (line))]
    fn new(line: Vec<usize>) -> Self {
        PyTakeTokens { line }
    }

    fn __repr__(&self) -> String {
        format!("TakeTokens(line={:?})", self.line)
    }
}

/// PayTokens action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "PayTokens",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyPayTokens {
    pub payment: PyTokens,
}

#[pymethods]
impl PyPayTokens {
    #[new]
    #[pyo3(signature = (payment))]
    fn new(payment: &PyTokens) -> Self {
        PyPayTokens { payment: *payment }
    }

    fn __repr__(&self) -> String {
        format!("PayTokens(payment={:?})", self.payment)
    }
}

/// ChooseGold action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "ChooseGold",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyChooseGold {
    pub index: usize,
}

#[pymethods]
impl PyChooseGold {
    #[new]
    #[pyo3(signature = (index))]
    fn new(index: usize) -> Self {
        PyChooseGold { index }
    }

    fn __repr__(&self) -> String {
        format!("ChooseGold(index={})", self.index)
    }
}

/// ChooseMulticolor action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "ChooseMulticolor",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyChooseMulticolor {
    pub color: PyColor,
}

#[pymethods]
impl PyChooseMulticolor {
    #[new]
    #[pyo3(signature = (color))]
    fn new(color: &PyColor) -> Self {
        PyChooseMulticolor { color: *color }
    }

    fn __repr__(&self) -> String {
        format!("ChooseMulticolor(color={})", self.color.__repr__())
    }
}

/// ChooseStealToken action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "ChooseStealToken",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyChooseStealToken {
    pub color: PyColor,
}

#[pymethods]
impl PyChooseStealToken {
    #[new]
    #[pyo3(signature = (color))]
    fn new(color: &PyColor) -> Self {
        PyChooseStealToken { color: *color }
    }

    fn __repr__(&self) -> String {
        format!("ChooseStealToken(color={})", self.color.__repr__())
    }
}

/// ChooseMatchingToken action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "ChooseMatchingToken",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyChooseMatchingToken {
    pub index: usize,
}

#[pymethods]
impl PyChooseMatchingToken {
    #[new]
    #[pyo3(signature = (index))]
    fn new(index: usize) -> Self {
        PyChooseMatchingToken { index }
    }

    fn __repr__(&self) -> String {
        format!("ChooseMatchingToken(index={})", self.index)
    }
}

/// ChooseRoyal action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "ChooseRoyal",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyChooseRoyal {
    pub royal_id: String,
}

#[pymethods]
impl PyChooseRoyal {
    #[new]
    #[pyo3(signature = (royal_id))]
    fn new(royal_id: String) -> Self {
        PyChooseRoyal { royal_id }
    }

    fn __repr__(&self) -> String {
        format!("ChooseRoyal(royal_id={:?})", self.royal_id)
    }
}

/// DiscardTokens action wrapper.
#[pyclass(
    frozen,
    eq,
    hash,
    name = "DiscardTokens",
    module = "splendor_duel_engine._core",
    get_all,
    from_py_object
)]
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct PyDiscardTokens {
    pub tokens: PyTokens,
}

#[pymethods]
impl PyDiscardTokens {
    #[new]
    #[pyo3(signature = (tokens))]
    fn new(tokens: &PyTokens) -> Self {
        PyDiscardTokens { tokens: *tokens }
    }

    fn __repr__(&self) -> String {
        format!("DiscardTokens(tokens={:?})", self.tokens)
    }
}

/// DecisionPoint wrapper: the phase and the ordered legal actions.
#[pyclass(frozen, name = "DecisionPoint", module = "splendor_duel_engine._core")]
pub struct PyDecisionPoint {
    pub phase: PyPhase,
    pub legal_actions: Vec<Py<PyAny>>,
}

#[pymethods]
impl PyDecisionPoint {
    #[getter]
    fn phase(&self) -> PyPhase {
        self.phase
    }

    #[getter]
    fn legal_actions(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        self.legal_actions
            .iter()
            .map(|action| action.clone_ref(py))
            .collect()
    }

    fn __repr__(&self) -> String {
        format!(
            "DecisionPoint(phase={}, legal_actions=<{} actions>)",
            self.phase.__repr__(),
            self.legal_actions.len()
        )
    }
}

/// Convert one Rust action into its Python wrapper instance.
fn action_to_py(py: Python<'_>, action: Action) -> PyResult<Py<PyAny>> {
    Ok(match action {
        Action::UsePrivilege { index } => Py::new(py, PyUsePrivilege { index })?.into_any(),
        Action::DoneWithPrivileges => Py::new(py, PyDoneWithPrivileges {})?.into_any(),
        Action::Replenish => Py::new(py, PyReplenish {})?.into_any(),
        Action::DoneWithReplenish => Py::new(py, PyDoneWithReplenish {})?.into_any(),
        Action::TakeTokens { line } => Py::new(py, PyTakeTokens { line })?.into_any(),
        Action::BuyCard(card) => Py::new(py, PyBuyCard::from(card))?.into_any(),
        Action::PayTokens { payment } => Py::new(
            py,
            PyPayTokens {
                payment: payment.into(),
            },
        )?
        .into_any(),
        Action::ReserveCard(reserve) => Py::new(py, PyReserveCard::from(reserve))?.into_any(),
        Action::ChooseGold { index } => Py::new(py, PyChooseGold { index })?.into_any(),
        Action::ChooseMulticolor { color } => Py::new(
            py,
            PyChooseMulticolor {
                color: PyColor::from_inner(color),
            },
        )?
        .into_any(),
        Action::ChooseStealToken { color } => Py::new(
            py,
            PyChooseStealToken {
                color: PyColor::from_inner(color),
            },
        )?
        .into_any(),
        Action::ChooseMatchingToken { index } => {
            Py::new(py, PyChooseMatchingToken { index })?.into_any()
        }
        Action::ChooseRoyal { royal_id } => Py::new(py, PyChooseRoyal { royal_id })?.into_any(),
        Action::DiscardTokens { tokens } => Py::new(
            py,
            PyDiscardTokens {
                tokens: tokens.into(),
            },
        )?
        .into_any(),
    })
}

/// Convert a Python action object into the Rust `Action`, if it is one of the
/// fourteen action wrapper classes.
fn try_from_action(obj: &Bound<'_, PyAny>) -> Result<Action, ()> {
    if let Ok(action) = obj.extract::<PyUsePrivilege>() {
        return Ok(Action::UsePrivilege {
            index: action.index,
        });
    }
    if obj.extract::<PyDoneWithPrivileges>().is_ok() {
        return Ok(Action::DoneWithPrivileges);
    }
    if obj.extract::<PyReplenish>().is_ok() {
        return Ok(Action::Replenish);
    }
    if obj.extract::<PyDoneWithReplenish>().is_ok() {
        return Ok(Action::DoneWithReplenish);
    }
    if let Ok(action) = obj.extract::<PyTakeTokens>() {
        return Ok(Action::TakeTokens { line: action.line });
    }
    if let Ok(action) = obj.extract::<PyBuyCard>() {
        return Ok(Action::BuyCard(BuyCard::from(&action)));
    }
    if let Ok(action) = obj.extract::<PyPayTokens>() {
        return Ok(Action::PayTokens {
            payment: (&action.payment).into(),
        });
    }
    if let Ok(action) = obj.extract::<PyReserveCard>() {
        return Ok(Action::ReserveCard(ReserveCard::from(&action)));
    }
    if let Ok(action) = obj.extract::<PyChooseGold>() {
        return Ok(Action::ChooseGold {
            index: action.index,
        });
    }
    if let Ok(action) = obj.extract::<PyChooseMulticolor>() {
        return Ok(Action::ChooseMulticolor {
            color: action.color.inner(),
        });
    }
    if let Ok(action) = obj.extract::<PyChooseStealToken>() {
        return Ok(Action::ChooseStealToken {
            color: action.color.inner(),
        });
    }
    if let Ok(action) = obj.extract::<PyChooseMatchingToken>() {
        return Ok(Action::ChooseMatchingToken {
            index: action.index,
        });
    }
    if let Ok(action) = obj.extract::<PyChooseRoyal>() {
        return Ok(Action::ChooseRoyal {
            royal_id: action.royal_id,
        });
    }
    if let Ok(action) = obj.extract::<PyDiscardTokens>() {
        return Ok(Action::DiscardTokens {
            tokens: (&action.tokens).into(),
        });
    }
    Err(())
}

/// Apply an action, returning a new state. Never mutates `state`.
#[pyfunction]
pub fn apply(state: &PyGameState, action: &Bound<'_, PyAny>) -> PyResult<PyGameState> {
    let action = match try_from_action(action) {
        Ok(action) => action,
        Err(()) => {
            // Python's `apply` validates the decision point before it looks at
            // the action object, so a finished game reports "game is over"
            // even for an unrecognised action.
            if let Err(err) = actions_decide(&state.inner) {
                return Err(pyo3::exceptions::PyValueError::new_err(err));
            }
            return Err(pyo3::exceptions::PyValueError::new_err("illegal action"));
        }
    };
    let inner =
        actions_apply(&state.inner, action).map_err(pyo3::exceptions::PyValueError::new_err)?;
    Ok(PyGameState { inner })
}

/// Return the legal actions for the state's current phase.
#[pyfunction]
pub fn decide(py: Python<'_>, state: &PyGameState) -> PyResult<PyDecisionPoint> {
    let decision = actions_decide(&state.inner).map_err(pyo3::exceptions::PyValueError::new_err)?;
    let legal_actions = decision
        .legal_actions
        .into_iter()
        .map(|action| action_to_py(py, action))
        .collect::<PyResult<Vec<_>>>()?;
    Ok(PyDecisionPoint {
        phase: PyPhase::from_inner(decision.phase),
        legal_actions,
    })
}
