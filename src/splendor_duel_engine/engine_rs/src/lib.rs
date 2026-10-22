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

/// The version of the extension module.
#[pyfunction]
fn __version__() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(__version__, m)?)?;
    m.add_class::<py::PyRandom>()?;
    Ok(())
}