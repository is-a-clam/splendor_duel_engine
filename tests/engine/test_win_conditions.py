"""Tests for the end-of-turn win check and the three victory conditions (Task 8).

Spec: docs/specs/splendor-duel-rules.md §"End of turn and victory". Victory is
checked only at the end of the active player's turn, after abilities, royal
picks and discard, and ends the game immediately:
  1. >= 20 prestige, or
  2. >= 10 crowns, or
  3. >= 10 prestige on cards of one colour (multicolor cards count as their
     chosen colour; colorless no-bonus cards and royals do not count).
"""

from dataclasses import replace

from splendor_duel_engine.engine import helpers
from splendor_duel_engine.engine.actions import (
    BuyCard,
    ChooseMulticolor,
    DiscardTokens,
    PayTokens,
    apply,
    decide,
)
from splendor_duel_engine.engine.cards import Ability, load_cards
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import (
    GameState,
    PlayerState,
    PurchasedCard,
    ReservedCard,
)


def board_state(**kwargs) -> GameState:
    """Build a state from a fixed seed with overrides (suite-wide pattern)."""
    return replace(GameState.new_game(0), **kwargs)


def _player(**kwargs) -> PlayerState:
    """An otherwise-empty player with overrides."""
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


def _purchased(card_id: str, chosen_color: Color | None = None) -> PurchasedCard:
    jewels, _ = load_cards()
    card = next(c for c in jewels if c.id == card_id)
    return PurchasedCard(card=card, chosen_color=chosen_color)


def test_win_at_20_prestige_checked_only_at_end_of_own_turn():
    """A purchase that reaches 20 points does not win until the turn ends."""
    jewels, _ = load_cards()
    # L1-21 is a 1-point black card with no ability; buying it takes 19 -> 20.
    card = next(c for c in jewels if c.id == "L1-21")
    reserved = ReservedCard(card=card, from_deck=False)

    p0 = _player(
        tokens=Tokens(gold=12, white=4),  # > 10 even after paying, so discard
        prestige=19,
        reserved=(reserved,),
    )
    st = board_state(current_player=0, phase=Phase.MANDATORY, players=(p0, _player()))

    # Buy and pay; the purchase happens mid-turn.
    dp = decide(st)
    buy = next(
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    )
    st = apply(st, buy)
    pay = next(a for a in decide(st).legal_actions if isinstance(a, PayTokens))
    st = apply(st, pay)

    # Prestige is already 20, but the turn is not over: no winner yet, and the
    # player must discard first (they hold > 10 tokens).
    assert st.players[0].prestige == 20
    assert st.winner is None
    assert st.phase is Phase.DISCARD
    assert st.current_player == 0

    # Discard the excess, which ends the turn and triggers the win check.
    discard_dp = decide(st)
    assert len(discard_dp.legal_actions) > 0
    assert all(isinstance(a, DiscardTokens) for a in discard_dp.legal_actions)
    st = apply(st, discard_dp.legal_actions[0])

    assert st.winner == 0
    assert st.phase is Phase.GAME_OVER


def test_win_at_10_crowns():
    """10 crowns wins even with few prestige points."""
    st = board_state(
        current_player=0,
        players=(_player(crowns=10, prestige=1), _player()),
    )
    assert helpers.is_winner(st.players[0]) is True


def test_win_at_10_points_in_one_color():
    """10 prestige among one colour wins; a multicolor card counts as its chosen colour."""
    # Six red points on red cards + four red points on a multicolor card whose
    # chosen colour is red => exactly 10 red.
    st = board_state(
        current_player=0,
        players=(
            _player(
                purchased=(
                    _purchased("L3-10", None),  # 4 red
                    _purchased("L3-05", None),  # 3 red
                    _purchased("L2-16", None),  # 2 red  (total 9 red so far)
                    _purchased("L3-01", Color.RED),  # 3 pts, multicolor -> red
                )
            ),
            _player(),
        ),
    )
    # 4 + 3 + 2 + 3 = 12 red points; well over 10.
    assert helpers.is_winner(st.players[0]) is True
    assert st.players[0].prestige < 20  # not a 20-point win


def test_multicolor_counts_only_for_its_chosen_color():
    """A multicolor card contributes to exactly one colour: its chosen colour."""
    # 9 red on red cards + a 3-point multicolor chosen RED would win, but the
    # same card chosen BLUE must not.
    pieces = (
        _purchased("L3-10", None),  # 4 red
        _purchased("L3-05", None),  # 3 red
        _purchased("L2-16", None),  # 2 red  => 9 red
        _purchased("L3-01", Color.RED),  # multicolor -> red => 12
    )
    red_chosen = board_state(
        current_player=0, players=(_player(purchased=pieces), _player())
    )
    assert helpers.is_winner(red_chosen.players[0]) is True

    blue_chosen_pieces = pieces[:-1] + (_purchased("L3-01", Color.BLUE),)
    blue_chosen = board_state(
        current_player=0, players=(_player(purchased=blue_chosen_pieces), _player())
    )
    # 9 red and 3 blue: neither reaches 10.
    assert helpers.is_winner(blue_chosen.players[0]) is False


def test_royal_and_colorless_cards_do_not_count_for_color_win_but_do_for_20():
    """Colorless no-bonus cards and royals add to the 20-point total only."""
    # 9 black points on black cards + a colorless 6-point card: color total is
    # 9 (no colour victory), but prestige 15 is still under 20.
    st = board_state(
        current_player=0,
        players=(
            _player(
                purchased=(
                    _purchased("L3-07", None),  # 4 black
                    _purchased("L3-02", None),  # 3 black
                    _purchased("L2-12", None),  # 2 black => 9 black
                    _purchased("L3-12", None),  # 6 pts, colorless => no colour
                )
            ),
            _player(),
        ),
    )
    assert (
        helpers.is_winner(st.players[0]) is False
    )  # 9 black, not 10; 15 prestige, not 20

    # Add a royal (3 points, colorless): prestige 18, still no colour win.
    with_royal = replace(
        st,
        players=(
            replace(st.players[0], prestige=st.players[0].prestige + 3),
            st.players[1],
        ),
    )
    assert helpers.is_winner(with_royal.players[0]) is False

    # Pushing prestige to 20 with colorless/royal points *does* win.
    to_20 = replace(
        st,
        players=(
            replace(st.players[0], prestige=20),
            st.players[1],
        ),
    )
    assert helpers.is_winner(to_20.players[0]) is True


def test_game_ends_immediately_no_opponent_final_turn():
    """Reaching a victory condition ends the game: no final turn for the opponent."""
    jewels, _ = load_cards()
    card = next(c for c in jewels if c.id == "L1-21")  # 1 point, no ability
    reserved = ReservedCard(card=card, from_deck=False)
    p0 = _player(
        tokens=Tokens(gold=5),  # exactly the cost; nothing left => no discard
        prestige=19,
        reserved=(reserved,),
    )
    st = board_state(current_player=0, phase=Phase.MANDATORY, players=(p0, _player()))

    dp = decide(st)
    buy = next(a for a in dp.legal_actions if isinstance(a, BuyCard))
    st = apply(st, buy)
    pay = next(a for a in decide(st).legal_actions if isinstance(a, PayTokens))
    st = apply(st, pay)

    # Game over immediately, and the opponent never gets the turn: the active
    # player is still the winner, not the opponent.
    assert st.phase is Phase.GAME_OVER
    assert st.winner == 0
    assert st.current_player == 0
    # decide refuses once the game is over.
    try:
        decide(st)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("decide should raise after the game is over")


def test_extra_turn_does_not_defer_win_check():
    """A winning turn that also earns an extra turn ends the game immediately."""
    jewels, _ = load_cards()
    # L3-01 is a multicolor 3-point card with the EXTRA_TURN ability.
    card = next(c for c in jewels if c.id == "L3-01")
    assert card.ability == Ability.EXTRA_TURN
    reserved = ReservedCard(card=card, from_deck=False)

    # Exactly 18 red points; L3-01 (chosen red) takes red to 21 and total > 20.
    p0 = _player(
        bonus=Tokens(white=1),  # coloured bonus so the multicolor card is buyable
        tokens=Tokens(gold=10),
        prestige=18,
        reserved=(reserved,),
    )
    st = board_state(current_player=0, phase=Phase.MANDATORY, players=(p0, _player()))

    dp = decide(st)
    buy = next(a for a in dp.legal_actions if isinstance(a, BuyCard))
    st = apply(st, buy)
    # Pay.
    pay = next(a for a in decide(st).legal_actions if isinstance(a, PayTokens))
    st = apply(st, pay)

    # Multicolor colour choice, then the EXTRA_TURN ability resolves.
    assert st.phase is Phase.MULTICOLOR_COLOR
    choose = next(
        a for a in decide(st).legal_actions if isinstance(a, ChooseMulticolor)
    )
    st = apply(st, choose)

    # The ability set an extra turn, but the win check still fires now.
    assert st.phase is Phase.GAME_OVER
    assert st.winner == 0
    assert st.extra_turn is False


def test_no_endgame_bonus_scoring():
    """Leftover pearls, gold and privileges add nothing at game end."""
    rich = _player(
        prestige=20,
        tokens=Tokens(pearl=2, gold=3, white=4),
        privileges=3,
    )
    st = board_state(current_player=0, players=(rich, _player()))
    assert helpers.is_winner(st.players[0]) is True
    # The winning player's score is exactly their prestige, not the token count.
    assert st.players[0].prestige == 20
