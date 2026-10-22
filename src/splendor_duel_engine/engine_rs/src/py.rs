//! PyO3 wrapper types.

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

    fn randrange(&mut self, n: u32) -> u32 {
        self.inner.randrange(n)
    }

    fn shuffle(&mut self, items: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = items.cast::<PyList>()?;
        let len: usize = list.len();
        // Extract items as PyObject
        let mut objs: Vec<Bound<'_, PyAny>> = Vec::with_capacity(len);
        for i in 0..len {
            objs.push(list.get_item(i)?);
        }
        // Shuffle using Rust RNG
        self.inner.shuffle(&mut objs);
        // Write back
        for (i, obj) in objs.into_iter().enumerate() {
            list.set_item(i, obj)?;
        }
        Ok(())
    }

    fn copy(&self) -> PyRandom {
        self.clone()
    }
}