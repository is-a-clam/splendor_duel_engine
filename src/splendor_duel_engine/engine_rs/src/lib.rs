//! Splendor Duel engine, ported to Rust.
//!
//! The rule logic lives in the pure-Rust modules; `py` wraps it in
//! `#[pyclass]`es for the Python boundary.

use pyo3::prelude::*;

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
use crate::colors::GEM_COLORS;
use crate::py::{
    PyAbility, PyCard, PyColor, PyPhase, PyRandom, PyRoyalCard, PyTokens,
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

    // Classes
    m.add_class::<PyRandom>()?;
    m.add_class::<PyColor>()?;
    m.add_class::<PyTokens>()?;
    m.add_class::<PyAbility>()?;
    m.add_class::<PyPhase>()?;
    m.add_class::<PyCard>()?;
    m.add_class::<PyRoyalCard>()?;

    // Constants
    m.add("GEM_COLORS", (PyColor::WHITE, PyColor::BLUE, PyColor::GREEN, PyColor::RED, PyColor::BLACK))?;

    Ok(())
}