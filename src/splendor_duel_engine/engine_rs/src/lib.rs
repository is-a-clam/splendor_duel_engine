//! Splendor Duel engine, ported to Rust.
//!
//! The rule logic lives in the pure-Rust modules; `py` wraps it in
//! `#[pyclass]`es for the Python boundary.

use pyo3::prelude::*;

pub mod actions;
pub mod board;
pub mod cards;
pub mod colors;
pub mod helpers;
pub mod observation;
pub mod phase;
pub mod py;
pub mod rng;
pub mod state;

use crate::cards::load_cards as rs_load_cards;
use crate::helpers::{COLOR_WIN_POINTS, CROWNS_WIN, MAX_RESERVED, PRESTIGE_WIN, TOKEN_LIMIT};
use crate::py::{
    can_afford_card, can_reserve, color_points, cost_deficits, decide, discard_subsets, is_winner,
    legal_payments, new_game, observation as py_observation, take_penalty, visible_cards,
    PyAbility, PyBuyCard, PyCard, PyChooseGold, PyChooseMatchingToken, PyChooseMulticolor,
    PyChooseRoyal, PyChooseStealToken, PyColor, PyDecisionPoint, PyDiscardTokens,
    PyDoneWithPrivileges, PyDoneWithReplenish, PyGameState, PyObservation, PyPayTokens, PyPhase,
    PyPlayerState, PyPlayerView, PyPurchasedCard, PyRandom, PyReplenish, PyReserveCard,
    PyReservedCard, PyRoyalCard, PyTakeTokens, PyTokens, PyUsePrivilege,
};

/// The version of the extension module.
#[pyfunction]
fn __version__() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Load and validate the card data.
/// Returns a tuple of (jewel_cards, royal_cards) in file order.
#[pyfunction]
fn load_cards() -> PyResult<(Vec<PyCard>, Vec<PyRoyalCard>)> {
    let (jewels, royals) = rs_load_cards()?;
    Ok((
        jewels.into_iter().map(PyCard::from).collect(),
        royals.into_iter().map(PyRoyalCard::from).collect(),
    ))
}

/// The five gem colors as a tuple of Color.
#[pyfunction]
fn gem_colors() -> PyResult<(PyColor, PyColor, PyColor, PyColor, PyColor)> {
    Ok((
        PyColor::WHITE,
        PyColor::BLUE,
        PyColor::GREEN,
        PyColor::RED,
        PyColor::BLACK,
    ))
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(__version__, m)?)?;
    m.add_function(wrap_pyfunction!(load_cards, m)?)?;
    m.add_function(wrap_pyfunction!(gem_colors, m)?)?;
    m.add_function(wrap_pyfunction!(new_game, m)?)?;
    m.add_function(wrap_pyfunction!(py_observation, m)?)?;
    m.add_function(wrap_pyfunction!(decide, m)?)?;

    // Classes
    m.add_class::<PyRandom>()?;
    m.add_class::<PyColor>()?;
    m.add_class::<PyTokens>()?;
    m.add_class::<PyAbility>()?;
    m.add_class::<PyPhase>()?;
    m.add_class::<PyCard>()?;
    m.add_class::<PyRoyalCard>()?;
    m.add_class::<PyBuyCard>()?;
    m.add_class::<PyReserveCard>()?;
    m.add_class::<PyPurchasedCard>()?;
    m.add_class::<PyReservedCard>()?;
    m.add_class::<PyPlayerState>()?;
    m.add_class::<PyPlayerView>()?;
    m.add_class::<PyObservation>()?;
    m.add_class::<PyGameState>()?;
    m.add_class::<PyUsePrivilege>()?;
    m.add_class::<PyDoneWithPrivileges>()?;
    m.add_class::<PyReplenish>()?;
    m.add_class::<PyDoneWithReplenish>()?;
    m.add_class::<PyTakeTokens>()?;
    m.add_class::<PyPayTokens>()?;
    m.add_class::<PyChooseGold>()?;
    m.add_class::<PyChooseMulticolor>()?;
    m.add_class::<PyChooseStealToken>()?;
    m.add_class::<PyChooseMatchingToken>()?;
    m.add_class::<PyChooseRoyal>()?;
    m.add_class::<PyDiscardTokens>()?;
    m.add_class::<PyDecisionPoint>()?;

    // Constants
    m.add(
        "GEM_COLORS",
        (
            PyColor::WHITE,
            PyColor::BLUE,
            PyColor::GREEN,
            PyColor::RED,
            PyColor::BLACK,
        ),
    )?;

    // Rule helpers submodule (`_core.helpers`).
    let helpers_mod = PyModule::new(m.py(), "helpers")?;
    helpers_mod.add("TOKEN_LIMIT", TOKEN_LIMIT)?;
    helpers_mod.add("MAX_RESERVED", MAX_RESERVED)?;
    helpers_mod.add("PRESTIGE_WIN", PRESTIGE_WIN)?;
    helpers_mod.add("CROWNS_WIN", CROWNS_WIN)?;
    helpers_mod.add("COLOR_WIN_POINTS", COLOR_WIN_POINTS)?;
    helpers_mod.add_function(wrap_pyfunction!(cost_deficits, &helpers_mod)?)?;
    helpers_mod.add_function(wrap_pyfunction!(can_afford_card, &helpers_mod)?)?;
    helpers_mod.add_function(wrap_pyfunction!(legal_payments, &helpers_mod)?)?;
    helpers_mod.add_function(wrap_pyfunction!(take_penalty, &helpers_mod)?)?;
    helpers_mod.add_function(wrap_pyfunction!(color_points, &helpers_mod)?)?;
    helpers_mod.add_function(wrap_pyfunction!(discard_subsets, &helpers_mod)?)?;
    helpers_mod.add_function(wrap_pyfunction!(can_reserve, &helpers_mod)?)?;
    helpers_mod.add_function(wrap_pyfunction!(visible_cards, &helpers_mod)?)?;
    m.add_submodule(&helpers_mod)?;
    m.py()
        .import("sys")?
        .getattr("modules")?
        .set_item("splendor_duel_engine._core.helpers", &helpers_mod)?;

    // Win check lives at the top level (`_core.is_winner`).
    m.add_function(wrap_pyfunction!(is_winner, m)?)?;

    Ok(())
}
