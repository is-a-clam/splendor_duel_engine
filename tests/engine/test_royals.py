"""Tests for royal card acquisition and abilities (Task 7)."""

from dataclasses import replace

from splendor_duel_engine.engine.actions import (
    BuyCard,
    ChooseMulticolor,
    ChooseRoyal,
    PayTokens,
    apply,
    decide,
)
from splendor_duel_engine.engine.cards import Ability, RoyalCard, load_cards
from splendor_duel_engine.engine.colors import Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, ReservedCard


def board_state(**kwargs) -> GameState:
    st = GameState.new_game(0)
    return replace(st, **kwargs)


def test_third_crown_grants_royal_choice():
    """Acquiring 3rd crown triggers CHOOSE_ROYAL phase."""
    base_st = GameState.new_game(0)
    jewels, _royals = load_cards()
    card = None
    for c in jewels:
        if c.id == "L2-19":  # gives 1 crown
            card = c
            break
    assert card is not None

    p0 = replace(
        base_st.players[0],
        bonus=Tokens(white=2, blue=2, red=2, black=2, pearl=1),
        tokens=Tokens(white=2, blue=2, red=2, black=2, pearl=1, gold=5),
        crowns=2,
        reserved=(ReservedCard(card=card, from_deck=False),),
    )
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        players=(p0, base_st.players[1]),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    assert st2.phase is Phase.CHOOSE_PAYMENT
    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    assert len(pay_actions) > 0
    st3 = apply(st2, pay_actions[0])
    assert st3.phase == Phase.CHOOSE_ROYAL
    assert len(decide(st3).legal_actions) == len(st3.royals_available)


def test_sixth_crown_grants_second_royal():
    base_st = GameState.new_game(0)
    jewels, _royals = load_cards()
    card = None
    for c in jewels:
        if c.id == "L2-19":
            card = c
            break
    assert card is not None
    p0 = replace(
        base_st.players[0],
        bonus=Tokens(white=2, blue=2, red=2, black=2, pearl=1),
        tokens=Tokens(white=2, blue=2, red=2, black=2, pearl=1, gold=5),
        crowns=5,
        reserved=(ReservedCard(card=card, from_deck=False),),
    )
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        players=(p0, base_st.players[1]),
    )
    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    st2 = apply(st, buy_actions[0])
    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    st3 = apply(st2, pay_actions[0])
    assert st3.phase == Phase.CHOOSE_ROYAL


def test_max_two_royals_per_player():
    """The rule: at most 2 royals per player, triggered at the 3rd and 6th crown.

    Spec §Royal cards: a player takes a royal when crossing 3 crowns and again
    when crossing 6; there is no trigger at 9. This drives a single player
    through all three crossings and asserts the real representation: the royal
    is removed from ``royals_available`` and its prestige lands on the player.

    The player's royal count is not stored on ``PlayerState``, so it is inferred
    from the ``royals_available`` shrink plus the extra prestige granted.
    """
    base_st = GameState.new_game(0)
    jewels, _royals = load_cards()
    crown_card = next(c for c in jewels if c.id == "L2-19")  # grants 1 crown
    assert crown_card.crowns == 1

    # Two distinguishable royals, both ability-free so the post-pick phase is a
    # plain turn end (no STEAL_TOKEN / extra-turn branch to reason about).
    royal_a = RoyalCard(id="R-test-a", points=2, ability=None)
    royal_b = RoyalCard(id="R-test-b", points=3, ability=None)
    # Left over to prove the 9-crown crossing does *not* consume one.
    royal_c = RoyalCard(id="R-test-c", points=4, ability=None)

    def buy_crown_card(st: GameState) -> GameState:
        """From MANDATORY, buy the reserved crown card and pay for it."""
        dp = decide(st)
        buy = [
            a
            for a in dp.legal_actions
            if isinstance(a, BuyCard) and a.card.id == crown_card.id
        ]
        assert len(buy) == 1
        st2 = apply(st, buy[0])
        pay = [a for a in decide(st2).legal_actions if isinstance(a, PayTokens)]
        assert pay
        return apply(st2, pay[0])

    def choose_first_royal(st: GameState) -> GameState:
        choices = decide(st).legal_actions
        assert choices, "expected at least one royal to choose"
        return apply(st, choices[0])

    # --- Crossing the 3rd crown grants the first royal ---
    p0 = replace(
        base_st.players[0],
        bonus=Tokens(white=2, blue=2, red=2, black=2, pearl=1),
        tokens=Tokens(white=2, blue=2, red=2, black=2, pearl=1, gold=5),
        crowns=2,
        reserved=(ReservedCard(card=crown_card, from_deck=False),),
    )
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        royals_available=(royal_a, royal_b, royal_c),
        players=(p0, base_st.players[1]),
    )

    st = buy_crown_card(st)
    assert st.phase is Phase.CHOOSE_ROYAL
    assert st.players[0].crowns == 3
    available_before = len(st.royals_available)
    prestige_before = st.players[0].prestige
    action_chosen = decide(st).legal_actions[0]
    assert isinstance(action_chosen, ChooseRoyal)
    royal_chosen = next(
        r for r in st.royals_available if r.id == action_chosen.royal_id
    )
    st = choose_first_royal(st)
    assert len(st.royals_available) == available_before - 1
    assert st.players[0].prestige == prestige_before + royal_chosen.points

    # --- Crossing the 6th crown grants the second royal ---
    p0 = replace(
        st.players[0],
        tokens=Tokens(white=2, blue=2, red=2, black=2, pearl=1, gold=5),
        crowns=5,
        reserved=(ReservedCard(card=crown_card, from_deck=False),),
    )
    st = replace(
        st,
        current_player=0,
        phase=Phase.MANDATORY,
        players=(p0, st.players[1]),
    )

    st = buy_crown_card(st)
    assert st.phase is Phase.CHOOSE_ROYAL
    assert st.players[0].crowns == 6
    available_before = len(st.royals_available)
    prestige_before = st.players[0].prestige
    action_chosen = decide(st).legal_actions[0]
    assert isinstance(action_chosen, ChooseRoyal)
    royal_chosen = next(
        r for r in st.royals_available if r.id == action_chosen.royal_id
    )
    st = choose_first_royal(st)
    assert len(st.royals_available) == available_before - 1
    assert st.players[0].prestige == prestige_before + royal_chosen.points

    # --- Crossing from 8 to 9 crowns must NOT trigger a third royal ---
    p0 = replace(
        st.players[0],
        tokens=Tokens(white=2, blue=2, red=2, black=2, pearl=1, gold=5),
        crowns=8,
        reserved=(ReservedCard(card=crown_card, from_deck=False),),
    )
    st = replace(
        st,
        current_player=0,
        phase=Phase.MANDATORY,
        players=(p0, st.players[1]),
    )

    available_before = len(st.royals_available)
    st = buy_crown_card(st)
    assert st.players[0].crowns == 9
    assert st.phase is not Phase.CHOOSE_ROYAL
    assert len(st.royals_available) == available_before  # unchanged


def test_royal_ability_resolves():
    base_st = GameState.new_game(0)
    # Put player in CHOOSE_ROYAL state with a royal that has steal ability
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.CHOOSE_ROYAL,
        royals_available=(RoyalCard(id="R-2", points=2, ability=Ability.STEAL_TOKEN),),
        players=(
            replace(base_st.players[0], tokens=Tokens()),
            replace(base_st.players[1], tokens=Tokens(red=1)),
        ),
    )
    dp = decide(st)
    assert len(dp.legal_actions) == 1
    st2 = apply(st, dp.legal_actions[0])
    # Should go to STEAL_TOKEN phase
    assert st2.phase == Phase.STEAL_TOKEN


def test_royal_gives_prestige_but_neither_crown_nor_bonus():
    base_st = GameState.new_game(0)
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.CHOOSE_ROYAL,
        royals_available=(RoyalCard(id="R-3", points=3, ability=None),),
        players=(
            replace(base_st.players[0], prestige=5, crowns=3, bonus=Tokens()),
            base_st.players[1],
        ),
    )
    dp = decide(st)
    st2 = apply(st, dp.legal_actions[0])
    p0 = st2.players[0]
    assert p0.prestige == 8  # 5+3
    assert p0.crowns == 3  # unchanged
    assert p0.bonus.total() == 0  # unchanged


def test_no_royal_available_skips_choice():
    base_st = GameState.new_game(0)
    jewels, _royals = load_cards()
    card = None
    for c in jewels:
        if c.id == "L2-19":
            card = c
            break
    assert card is not None
    p0 = replace(
        base_st.players[0],
        bonus=Tokens(white=2, blue=2, red=2, black=2, pearl=1),
        tokens=Tokens(white=2, blue=2, red=2, black=2, pearl=1, gold=5),
        crowns=2,
        reserved=(ReservedCard(card=card, from_deck=False),),
    )
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        royals_available=(),
        players=(p0, base_st.players[1]),
    )
    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    st2 = apply(st, buy_actions[0])
    dp2 = decide(st2)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    st3 = apply(st2, pay_actions[0])
    # No royals available, should skip to ability resolution or turn end
    assert st3.phase != Phase.CHOOSE_ROYAL


def test_multicolor_purchase_crossing_crown_threshold_grants_royal():
    """Buying a multicolor card that crosses a crown threshold still offers a royal.

    The color choice comes first (MULTICOLOR_COLOR), but the royal pick must not
    be dropped: after the color resolves the engine enters CHOOSE_ROYAL, and
    choosing a royal grants its prestige.
    """
    base_st = GameState.new_game(0)
    jewels, _royals = load_cards()
    card = None
    for c in jewels:
        if c.id == "L2-00":  # multicolor, gives 2 crowns
            card = c
            break
    assert card is not None and card.is_multicolor and card.crowns > 0

    # Player has 2 crowns, so this purchase reaches 4 (crosses the 3rd-crown
    # threshold). A colored bonus is required to buy a multicolor card.
    p0 = replace(
        base_st.players[0],
        bonus=Tokens(white=1),
        tokens=Tokens(green=6, pearl=1, gold=5),
        crowns=2,
        prestige=10,
        reserved=(ReservedCard(card=card, from_deck=False),),
    )
    st = replace(
        base_st,
        current_player=0,
        phase=Phase.MANDATORY,
        players=(p0, base_st.players[1]),
    )

    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st2 = apply(st, buy_actions[0])
    assert st2.phase is Phase.CHOOSE_PAYMENT

    pay_actions = [a for a in decide(st2).legal_actions if isinstance(a, PayTokens)]
    st3 = apply(st2, pay_actions[0])

    # The color must be chosen before the royal, and the trigger is retained.
    assert st3.phase is Phase.MULTICOLOR_COLOR
    assert st3.pending_royal is True
    assert st3.players[0].crowns == 2 + card.crowns

    color_actions = [
        a for a in decide(st3).legal_actions if isinstance(a, ChooseMulticolor)
    ]
    assert color_actions
    st4 = apply(st3, color_actions[0])

    assert st4.phase is Phase.CHOOSE_ROYAL
    assert st4.pending_royal is False
    assert len(decide(st4).legal_actions) == len(st4.royals_available)

    royal_actions = decide(st4).legal_actions
    chosen_action = royal_actions[0]
    assert isinstance(chosen_action, ChooseRoyal)
    royal = next(r for r in st4.royals_available if r.id == chosen_action.royal_id)
    prestige_before = st4.players[0].prestige
    st5 = apply(st4, royal_actions[0])
    assert st5.players[0].prestige == prestige_before + royal.points
