"""Parity between the Rust rule helpers and the Python ones."""

from __future__ import annotations

from splendor_duel_engine._core import Color as RustColor
from splendor_duel_engine._core import PlayerState as RustPlayerState
from splendor_duel_engine._core import PurchasedCard as RustPurchasedCard
from splendor_duel_engine._core import Tokens as RustTokens
from splendor_duel_engine._core import helpers as rust_helpers
from splendor_duel_engine._core import load_cards as rust_load_cards

from splendor_duel_engine.engine import helpers as py_helpers
from splendor_duel_engine.engine.cards import load_cards as py_load_cards
from splendor_duel_engine.engine.colors import GEM_COLORS
from splendor_duel_engine.engine.colors import Color as PyColor
from splendor_duel_engine.engine.colors import Tokens as PyTokens
from splendor_duel_engine.engine.state import PlayerState as PyPlayerState
from splendor_duel_engine.engine.state import PurchasedCard as PyPurchasedCard
from tests.engine_rs.parity import tokens_fingerprint

# The same token vectors are built on both sides: the field names match.
TOKEN_CASES = [
    ({}, {}, {}),
    ({"white": 3}, {"white": 1}, {"white": 1}),
    ({"white": 2, "blue": 2}, {}, {}),
    ({"pearl": 2}, {"pearl": 1}, {}),
    ({"white": 1, "gold": 2}, {}, {}),
    ({"black": 2, "red": 1}, {"black": 1}, {"gold": 1}),
]

RUST_CARDS, _ = rust_load_cards()
PY_CARDS, _ = py_load_cards()
RUST_BY_ID = {card.id: card for card in RUST_CARDS}
PY_BY_ID = {card.id: card for card in PY_CARDS}


def _rust_purchased(card_id: str, chosen_color: str | None) -> RustPurchasedCard:
    chosen = getattr(RustColor, chosen_color) if chosen_color is not None else None
    return RustPurchasedCard(RUST_BY_ID[card_id], chosen)


def _py_purchased(card_id: str, chosen_color: str | None) -> PyPurchasedCard:
    chosen = getattr(PyColor, chosen_color) if chosen_color is not None else None
    return PyPurchasedCard(PY_BY_ID[card_id], chosen)


def _rust_player(prestige: int, crowns: int, purchased: list[tuple[str, str | None]]):
    return RustPlayerState(
        tokens=RustTokens(),
        bonus=RustTokens(),
        prestige=prestige,
        crowns=crowns,
        reserved=[],
        purchased=[_rust_purchased(cid, chosen) for cid, chosen in purchased],
        privileges=0,
    )


def _py_player(prestige: int, crowns: int, purchased: list[tuple[str, str | None]]):
    return PyPlayerState(
        tokens=PyTokens(),
        bonus=PyTokens(),
        prestige=prestige,
        crowns=crowns,
        reserved=(),
        purchased=tuple(_py_purchased(cid, chosen) for cid, chosen in purchased),
        privileges=0,
    )


def test_constants_match() -> None:
    for name in (
        "TOKEN_LIMIT",
        "MAX_RESERVED",
        "PRESTIGE_WIN",
        "CROWNS_WIN",
        "COLOR_WIN_POINTS",
    ):
        assert getattr(rust_helpers, name) == getattr(py_helpers, name)


def test_cost_deficits_matches() -> None:
    for cost, bonus, paid in TOKEN_CASES:
        rust = rust_helpers.cost_deficits(
            RustTokens(**cost), RustTokens(**bonus), RustTokens(**paid)
        )
        py = py_helpers.cost_deficits(
            PyTokens(**cost), PyTokens(**bonus), PyTokens(**paid)
        )
        assert {colour.value: n for colour, n in rust.items()} == {
            colour.value: n for colour, n in py.items()
        }
        assert list(rust) == [getattr(RustColor, name) for name in _order(py)]


def _order(py_deficits) -> list[str]:
    """The colour names in the Python helper's insertion order."""
    return [colour.name for colour in py_deficits]


def test_cost_deficits_ignores_gold() -> None:
    rust = rust_helpers.cost_deficits(
        RustTokens(white=1, gold=2), RustTokens(), RustTokens()
    )
    assert {colour.value: n for colour, n in rust.items()} == {"white": 1}


def test_can_afford_card_matches() -> None:
    cases = [
        ("L1-15", {"white": 3}, {}),
        ("L1-15", {"white": 2}, {}),
        ("L1-15", {"white": 2, "gold": 1}, {}),
        ("L1-29", {"red": 4, "pearl": 1}, {}),
        ("L1-29", {"red": 4, "gold": 1}, {}),
        # Multicolor: no gem-colour bonus means unaffordable, however much gold.
        ("L1-18", {"gold": 10}, {}),
        # ... but a single gem bonus in any colour unlocks it.
        ("L1-18", {"white": 3, "pearl": 1}, {"white": 1}),
        ("L1-18", {"gold": 10}, {"white": 1}),
        ("L1-18", {"gold": 10}, {"black": 1}),
        # Pearls and gold are not gem-colour bonuses.
        ("L1-18", {"gold": 10}, {"pearl": 1}),
        ("L1-18", {"gold": 10}, {"gold": 1}),
        # Bonus tokens reduce the coloured requirement.
        ("L2-17", {"white": 3, "blue": 2, "pearl": 1}, {"white": 1}),
        ("L2-17", {"white": 2, "blue": 2, "pearl": 1}, {"white": 1}),
    ]
    for card_id, tokens, bonus in cases:
        rust = rust_helpers.can_afford_card(
            RUST_BY_ID[card_id], RustTokens(**tokens), RustTokens(**bonus)
        )
        py = py_helpers.can_afford_card(
            PY_BY_ID[card_id], PyTokens(**tokens), PyTokens(**bonus)
        )
        assert rust == py, (card_id, tokens, bonus)


def test_legal_payments_matches() -> None:
    cases = [
        ("L1-15", {"white": 3}, {}),
        ("L1-15", {"white": 2}, {}),
        ("L1-18", {"white": 4, "gold": 2}, {}),
        ("L1-18", {"white": 3, "pearl": 1}, {"white": 1}),
        ("L1-01", {"white": 2, "blue": 2, "pearl": 1, "gold": 2}, {}),
        ("L2-17", {"white": 3, "blue": 2, "pearl": 1, "gold": 1}, {"white": 1}),
        ("L3-12", {"white": 8, "gold": 3}, {}),
    ]
    for card_id, tokens, bonus in cases:
        rust = rust_helpers.legal_payments(
            RUST_BY_ID[card_id], RustTokens(**tokens), RustTokens(**bonus)
        )
        py = py_helpers.legal_payments(
            PY_BY_ID[card_id], PyTokens(**tokens), PyTokens(**bonus)
        )
        assert [tokens_fingerprint(t) for t in rust] == [
            tokens_fingerprint(t) for t in py
        ], (card_id, tokens, bonus)


def test_take_penalty_matches() -> None:
    cases = [
        [PyColor.WHITE, PyColor.WHITE, PyColor.WHITE],
        [PyColor.PEARL, PyColor.PEARL],
        [PyColor.WHITE, PyColor.BLUE],
        [PyColor.WHITE, PyColor.WHITE],
        [PyColor.GOLD, PyColor.GOLD, PyColor.GOLD],
        [],
    ]
    for case in cases:
        rust_case = [getattr(RustColor, colour.name) for colour in case]
        assert rust_helpers.take_penalty(rust_case) == py_helpers.take_penalty(case)


def test_color_points_matches() -> None:
    purchased_cases = [
        ("L1-21", None),
        ("L3-02", None),
        ("L3-01", "RED"),
        ("L1-18", "BLACK"),
        ("L1-29", None),
        ("L2-23", None),
        ("L3-07", None),
    ]
    rust = [_rust_purchased(cid, chosen) for cid, chosen in purchased_cases]
    py = [_py_purchased(cid, chosen) for cid, chosen in purchased_cases]
    for colour in GEM_COLORS:
        assert rust_helpers.color_points(
            rust, getattr(RustColor, colour.name)
        ) == py_helpers.color_points(py, colour)


def test_discard_subsets_matches() -> None:
    cases = [
        ({"white": 2, "blue": 1, "pearl": 1, "gold": 1}, 2),
        ({"white": 3}, 2),
        (
            {
                "white": 1,
                "blue": 1,
                "green": 1,
                "red": 1,
                "black": 1,
                "pearl": 1,
                "gold": 1,
            },
            3,
        ),
        ({"gold": 2, "pearl": 1}, 1),
        ({"white": 1}, 1),
        ({"white": 3}, 5),
        ({"black": 2, "red": 2}, 0),
    ]
    for tokens, excess in cases:
        rust = rust_helpers.discard_subsets(RustTokens(**tokens), excess)
        py = py_helpers.discard_subsets(PyTokens(**tokens), excess)
        assert [tokens_fingerprint(t) for t in rust] == [
            tokens_fingerprint(t) for t in py
        ], (tokens, excess)


def test_can_reserve_matches() -> None:
    boards = [
        tuple([PyColor.WHITE] * 25),
        tuple([PyColor.GOLD] + [PyColor.WHITE] * 24),
    ]
    for board in boards:
        rust_board = [getattr(RustColor, colour.name) for colour in board]
        for reserved in (0, 2, 3):
            assert rust_helpers.can_reserve(rust_board, reserved) == (
                py_helpers.can_reserve(board, reserved)
            )


def test_visible_cards_matches() -> None:
    pyramid_cases = [
        [["L1-15", None], ["L1-16", "L1-17", "L1-18"]],
        [[], ["L1-19"]],
    ]
    public_ids = ["L1-20", "L1-21"]
    deck_ids = ["L1-22"]

    for rows in pyramid_cases:
        rust_pyramid = [
            [RUST_BY_ID[cid] if cid is not None else None for cid in row]
            for row in rows
        ]
        py_pyramid = [
            [PY_BY_ID[cid] if cid is not None else None for cid in row] for row in rows
        ]
        rust = rust_helpers.visible_cards(
            rust_pyramid,
            [RUST_BY_ID[cid] for cid in public_ids],
            [RUST_BY_ID[cid] for cid in deck_ids],
        )
        py = py_helpers.visible_cards(
            tuple(tuple(row) for row in py_pyramid),
            tuple(PY_BY_ID[cid] for cid in public_ids),
            tuple(PY_BY_ID[cid] for cid in deck_ids),
        )
        assert [card.id for card in rust] == [card.id for card in py]
        expected = [cid for row in rows for cid in row if cid is not None]
        assert [card.id for card in rust] == expected + public_ids + deck_ids


def test_can_reserve_gold_on_board_is_required() -> None:
    py_board = tuple([PyColor.WHITE] * 25)
    rust_board = [getattr(RustColor, colour.name) for colour in py_board]
    assert rust_helpers.can_reserve(rust_board, 0) == py_helpers.can_reserve(
        py_board, 0
    )
    assert rust_helpers.can_reserve(rust_board, 0) is False


def test_is_winner_matches() -> None:
    cases = [
        (20, 0, []),
        (19, 0, []),
        (0, 10, []),
        (0, 9, []),
        (0, 0, [("L3-01", "RED")] * 4),
        (0, 0, [("L3-01", "RED")] * 3),
        (0, 0, [("L3-07", None)] * 3),
        (5, 0, [("L3-01", "BLACK"), ("L3-08", None)]),
        (0, 0, [(cid, None) for cid in ("L3-07", "L3-08", "L3-09", "L3-10")]),
    ]
    expected = [True, False, True, False, True, False, True, False, False]
    for (prestige, crowns, purchased), want in zip(cases, expected, strict=True):
        rust = rust_helpers.is_winner(_rust_player(prestige, crowns, purchased))
        py = py_helpers.is_winner(_py_player(prestige, crowns, purchased))
        assert rust == py, (prestige, crowns, purchased)
        assert rust is want, (prestige, crowns, purchased)
