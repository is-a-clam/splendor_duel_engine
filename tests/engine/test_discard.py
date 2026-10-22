"""Tests for the discard phase (Task 8).

Spec: docs/specs/splendor-duel-rules.md §"End of turn and victory". The
end-of-turn sequence ends with "discard down to 10 tokens (all token types
count; excess goes to the bag)". There is no purse: a player may hold more than
10 tokens *during* their turn; the check happens only when the turn ends.
"""

from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import (
    BuyCard,
    ChooseMatchingToken,
    DiscardTokens,
    PayTokens,
    TakeTokens,
    apply,
    decide,
)
from splendor_duel_engine.engine.cards import Ability, load_cards
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import (
    GameState,
    PlayerState,
    ReservedCard,
    new_game,
)


def board_state(**kwargs) -> GameState:
    return replace(new_game(0), **kwargs)


def _player(**kwargs) -> PlayerState:
    defaults: dict[str, object] = {
        "tokens": Tokens(),
        "bonus": Tokens(),
        "prestige": 0,
        "crowns": 0,
        "reserved": (),
        "purchased": (),
        "privileges": 0,
    }
    defaults.update(kwargs)
    return PlayerState(**defaults)  # type: ignore[arg-type]


def _total(state: GameState) -> int:
    """Total tokens across board + bag + both hands (must stay 25)."""
    on_board = sum(1 for c in state.board if c is not None)
    return on_board + state.bag.total() + sum(p.tokens.total() for p in state.players)


def test_discard_required_when_over_ten_after_ability_grant():
    """A token-granting ability can push a player past 10, forcing a discard."""
    jewels, _ = load_cards()
    # L1-02: take_matching_token ability, bonus black, no multicolor.
    card = next(c for c in jewels if c.id == "L1-02")
    assert card.ability == Ability.TAKE_MATCHING_TOKEN
    assert card.bonus == Color.BLACK

    reserved = ReservedCard(card=card, from_deck=False)
    # Bonus fully covers L1-02's green=2/red=2 cost, so no tokens are spent.
    # Holding 11 tokens plus one from the ability => 12, forcing a discard.
    p0 = _player(
        bonus=Tokens(green=2, red=2),
        tokens=Tokens(white=10, black=1),  # total 11
        reserved=(reserved,),
    )
    st = board_state(current_player=0, phase=Phase.MANDATORY, players=(p0, _player()))
    board = list(st.board)
    board[0] = Color.BLACK  # a black token for the matching-token ability
    st = replace(st, board=tuple(board))

    dp = decide(st)
    buy = next(
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    )
    st = apply(st, buy)
    pay = next(a for a in decide(st).legal_actions if isinstance(a, PayTokens))
    st = apply(st, pay)

    assert st.phase is Phase.TAKE_MATCHING_TOKEN
    choose = next(
        a for a in decide(st).legal_actions if isinstance(a, ChooseMatchingToken)
    )
    st = apply(st, choose)

    # 10 held (minus payment) + 1 from the ability could exceed 10, so the turn
    # ends in DISCARD rather than handing over.
    assert st.players[0].tokens.total() > 10
    assert st.phase is Phase.DISCARD
    assert st.current_player == 0


def test_discard_subset_sum_equals_excess_and_tokens_reach_bag():
    """Every offered discard sums to the excess and moves those tokens to the bag."""
    hand = Tokens(white=4, blue=4, green=3)  # total 11 => excess 1
    st = board_state(
        current_player=0,
        phase=Phase.DISCARD,
        bag=Tokens(),
        players=(_player(tokens=hand), _player()),
    )

    dp = decide(st)
    assert len(dp.legal_actions) > 0
    # Every option removes exactly the excess (1 token) and is unique.
    seen = set()
    for action in dp.legal_actions:
        assert isinstance(action, DiscardTokens)
        assert action.tokens.total() == 1
        key = (
            action.tokens.white,
            action.tokens.blue,
            action.tokens.green,
            action.tokens.red,
            action.tokens.black,
            action.tokens.pearl,
            action.tokens.gold,
        )
        assert key not in seen
        seen.add(key)
    # Three distinct single-colour discards: white, blue or green.
    assert len(dp.legal_actions) == 3

    total_before = _total(st)
    before_bag = st.bag.total()

    # Discard one white.
    choice = next(
        a
        for a in dp.legal_actions
        if isinstance(a, DiscardTokens) and a.tokens.white == 1
    )
    st = apply(st, choice)

    assert st.players[0].tokens == Tokens(white=3, blue=4, green=3)
    assert st.players[0].tokens.total() == 10
    assert st.bag.total() == before_bag + 1
    assert st.bag.white == 1
    # Token conservation is preserved.
    assert _total(st) == total_before
    # Discarding ends the turn: the seat passes to the opponent.
    assert st.phase is Phase.USE_PRIVILEGES
    assert st.current_player == 1


def test_discard_can_use_gold_and_pearls_and_offers_multicolour_subsets():
    """Discard subsets may include gold and pearls, not only the five gems."""
    hand = Tokens(white=9, gold=2, pearl=1)  # total 12 => excess 2
    st = board_state(
        current_player=0,
        phase=Phase.DISCARD,
        bag=Tokens(),
        players=(_player(tokens=hand), _player()),
    )
    dp = decide(st)
    options = {a.tokens for a in dp.legal_actions if isinstance(a, DiscardTokens)}
    assert len(options) > 0
    assert all(o.total() == 2 for o in options)
    # Gold-only and gold+pearl are both representable.
    assert Tokens(gold=2) in options or Tokens(gold=1, pearl=1) in options

    # Discard a mixed subset (1 white + 1 gold).
    mixed = DiscardTokens(tokens=Tokens(white=1, gold=1))
    assert mixed in dp.legal_actions
    st = apply(st, mixed)
    assert st.players[0].tokens == Tokens(white=8, gold=1, pearl=1)
    assert st.bag.white == 1 and st.bag.gold == 1


def test_under_ten_no_discard_phase():
    """A turn ending at or below 10 advances the seat without a discard phase."""
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        players=(_player(tokens=Tokens(white=2)), _player()),
    )
    board = list(st.board)
    board[0] = Color.RED
    board[1] = Color.RED  # a straight line of length 2
    st = replace(st, board=tuple(board))

    line = next(a.line for a in decide(st).legal_actions if isinstance(a, TakeTokens))
    st = apply(st, TakeTokens(line=line))

    # 2 + 2 = 4 tokens, well under 10: no discard, seat passed.
    assert st.players[0].tokens.total() <= 10
    assert st.phase is Phase.USE_PRIVILEGES
    assert st.current_player == 1


def test_mid_turn_gain_over_ten_is_fine_until_end_of_turn():
    """Holding > 10 mid-turn is legal; the check only happens at turn end."""
    st = board_state(
        current_player=0,
        phase=Phase.MANDATORY,
        bag=Tokens(),
        players=(_player(tokens=Tokens(white=9)), _player()),
    )
    board = list(st.board)
    board[0] = Color.RED
    board[1] = Color.RED
    board[2] = Color.RED  # a straight line of length 3
    st = replace(st, board=tuple(board))

    line = next(
        a.line
        for a in decide(st).legal_actions
        if isinstance(a, TakeTokens) and len(a.line) == 3
    )
    assert len(line) == 3
    st = apply(st, TakeTokens(line=line))

    # The player now holds 12 tokens. Taking them was legal; the excess simply
    # means the turn ends in DISCARD.
    assert st.players[0].tokens.total() == 12
    assert st.phase is Phase.DISCARD
    # 3 same-colour tokens is a penalty, so the opponent gained a privilege.
    assert st.current_player == 0  # still resolving this turn (discard)

    # Resolving the discard downs to exactly 10 and passes the turn.
    dp = decide(st)
    assert all(
        isinstance(a, DiscardTokens) and a.tokens.total() == 2 for a in dp.legal_actions
    )
    st = apply(st, dp.legal_actions[0])
    assert st.players[0].tokens.total() == 10
    assert st.current_player == 1


def test_apply_rejects_illegal_discard():
    """A discard that is the wrong size or exceeds what is held is rejected."""
    hand = Tokens(white=4, blue=4, green=3)  # excess 1
    st = board_state(
        current_player=0,
        phase=Phase.DISCARD,
        players=(_player(tokens=hand), _player()),
    )
    # Wrong total.
    with pytest.raises(ValueError):
        apply(st, DiscardTokens(tokens=Tokens(white=2)))
    # More than held.
    with pytest.raises(ValueError):
        apply(st, DiscardTokens(tokens=Tokens(gold=1)))


def test_discard_then_extra_turn_keeps_the_seat():
    """After discarding, an earned extra turn keeps the same player on turn."""
    hand = Tokens(white=4, blue=4, green=3)  # excess 1
    st = board_state(
        current_player=0,
        phase=Phase.DISCARD,
        players=(_player(tokens=hand), _player()),
        extra_turn=True,  # an ability/royal earned an extra turn this turn
    )
    st = apply(st, decide(st).legal_actions[0])
    assert st.players[0].tokens.total() == 10
    assert st.current_player == 0
    assert st.extra_turn is True
    assert st.phase is Phase.USE_PRIVILEGES
