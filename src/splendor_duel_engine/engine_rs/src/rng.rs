//! CPython-compatible randomness.
//!
//! The generator itself is the `mt19937` crate; this module adds CPython's
//! *seeding* rule and CPython's `getrandbits`/`_randbelow`/`randrange`/
//! `shuffle` semantics on top of it.

use mt19937::MT19937;
use rand_core::Rng;

/// The CPython-compatible generator.
#[derive(Debug)]
pub struct Random {
    inner: MT19937,
}

impl Clone for Random {
    /// `MT19937` inherits no `Clone`, so copy its state and cursor by hand.
    fn clone(&self) -> Self {
        let mut inner = MT19937::default();
        inner.set_state(self.inner.get_state());
        inner.set_index(self.inner.get_index());
        Self { inner }
    }
}

impl Random {
    /// Seed exactly like `random.Random(seed)`.
    ///
    /// CPython takes the **absolute** value of the seed, converts it to
    /// minimal little-endian bytes, zero-pads to a multiple of 4 bytes, splits
    /// that into 32-bit little-endian words, and hands the words to
    /// `init_by_array`. The seed is *not* truncated to 32 bits.
    pub fn from_seed(seed: i64) -> Self {
        let words = seed_to_words(seed);
        Self {
            inner: MT19937::new_with_slice_seed(&words),
        }
    }

    /// The next 32-bit word, as CPython's `genrand_uint32`.
    pub fn next_u32(&mut self) -> u32 {
        self.inner.next_u32()
    }

    /// `getrandbits(k)` for `1 <= k <= 32`.
    pub fn getrandbits(&mut self, k: u32) -> u32 {
        assert!((1..=32).contains(&k), "k must be in 1..=32");
        self.next_u32() >> (32 - k)
    }

    /// CPython's `_randbelow(n)`.
    pub fn randbelow(&mut self, n: u32) -> u32 {
        // n == 0 is handled by the Python wrapper to raise ValueError
        // This function assumes n > 0
        let k = n.ilog2() + 1; // n.bit_length()
        loop {
            let r = self.getrandbits(k);
            if r < n {
                return r;
            }
        }
    }

    /// CPython's `randrange(n)` for `n >= 1`.
    pub fn randrange(&mut self, n: u32) -> u32 {
        self.randbelow(n)
    }

    /// CPython's `random.shuffle`: Fisher-Yates from the end.
    pub fn shuffle<T>(&mut self, items: &mut [T]) {
        for i in (1..items.len()).rev() {
            let j = self.randbelow((i + 1) as u32) as usize;
            items.swap(i, j);
        }
    }
}

/// Convert a seed integer to words exactly as CPython does.
fn seed_to_words(seed: i64) -> Vec<u32> {
    let magnitude = (seed as i128).unsigned_abs();

    // Convert to minimal little-endian bytes
    let mut bytes = Vec::new();
    let mut n = magnitude;
    if n == 0 {
        bytes.push(0);
    } else {
        while n > 0 {
            bytes.push((n & 0xFF) as u8);
            n >>= 8;
        }
    }

    // Zero-pad to multiple of 4
    while bytes.len() % 4 != 0 {
        bytes.push(0);
    }

    // Split into u32 words
    bytes
        .chunks_exact(4)
        .map(|c| u32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_seed_zero() {
        let mut rng = Random::from_seed(0);
        assert_eq!(rng.next_u32(), 3626764237);
    }

    #[test]
    fn test_seed_one() {
        let mut rng = Random::from_seed(1);
        assert_eq!(rng.next_u32(), 577090037);
    }

    #[test]
    fn test_seed_42() {
        let mut rng = Random::from_seed(42);
        assert_eq!(rng.next_u32(), 2746317213);
    }

    #[test]
    fn test_negative_seed_matches_absolute() {
        let mut rng1 = Random::from_seed(-42);
        let mut rng2 = Random::from_seed(42);
        assert_eq!(rng1.next_u32(), rng2.next_u32());
    }

    #[test]
    fn test_large_seeds() {
        let mut rng = Random::from_seed(2i64.pow(32));
        assert_eq!(rng.next_u32(), 485306839);

        let mut rng = Random::from_seed(2i64.pow(32) + 1);
        assert_eq!(rng.next_u32(), 991850117);

        let mut rng = Random::from_seed(i64::MAX);
        assert_eq!(rng.next_u32(), 1359979423);

        let mut rng = Random::from_seed(987654321012345678);
        assert_eq!(rng.next_u32(), 586827094);
    }
}