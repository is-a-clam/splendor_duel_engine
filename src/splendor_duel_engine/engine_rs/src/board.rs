//! Board layout and SPIRAL ordering.

/// Row-major board indices in spiral order, centre first.
/// Matches Python's `engine/board.py` exactly.
pub const SPIRAL: [usize; 25] = [
    12, 7, 8, 13, 18, 17, 16, 11, 6, 1, 2, 3, 4, 9, 14, 19, 24, 23, 22, 21, 20, 15, 10, 5, 0,
];

/// Pyramid layout: (row_length, deck_index) for each row in order (level 3, 2, 1).
/// decks is stored as [level3, level2, level1] so deck_index matches row index.
pub const PYRAMID_LAYOUT: [(usize, usize); 3] = [(3, 0), (4, 1), (5, 2)];