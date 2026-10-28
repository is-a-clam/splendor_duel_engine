"""Tests for the greedy heuristic baseline agent (Task 3)."""

from dataclasses import replace

from splendor_duel_engine.agents.base import Agent, play_game
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.engine.actions import (
    BuyCard,
    ChooseMulticolor,
    ChooseRoyal,
    DiscardTokens,
    DoneWithReplenish,
    PayTokens,
    Replenish,
    ReserveCard,
    TakeTokens,
    UsePrivilege,
    apply,
    decide,
)
from splendor_duel_engine.engine.cards import Ability, Card, load_cards
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.observation import Observation, get_observation
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, ReservedCard

EMPTY_PYRAMID = ((None,) * 3, (None,) * 4, (None,) * 5)


def board_state(**kwargs) -> GameState:
    st = GameState.new_game(0)
    return replace(st, **kwargs)


def synthetic_card(
    card_id: str,
    *,
    points: int = 0,
    crowns: int = 0,
    bonus: Color | None = None,
    cost: Tokens | None = None,
    ability: Ability | None = None,
) -> Card:
    return Card(
        id=card_id,
        level=1,
        points=points,
        crowns=crowns,
        bonus=bonus,
        bonus_count=1 if bonus is not None else 0,
        ability=ability,
        is_multicolor=False,
        cost=Tokens() if cost is None else cost,
    )


def _observation_with_visible_card(card: Card, tokens: Tokens) -> Observation:
    """An observation whose only visible card is ``card`` for the active player."""
    st = GameState.new_game(0)
    st = replace(
        st,
        current_player=0,
        phase=Phase.MANDATORY,
        players=(
            replace(st.players[0], tokens=tokens, bonus=Tokens()),
            st.players[1],
        ),
        pyramid=((card, None, None), (None,) * 4, (None,) * 5),
    )
    return get_observation(st, 0)


def test_greedy_agent_chooses_legal_action():
    agent = GreedyAgent()
    assert isinstance(agent, Agent)
    state = GameState.new_game(0)
    obs = get_observation(state, state.current_player)
    dp = decide(state)
    action = agent.choose_action(obs, dp.legal_actions)
    assert action in dp.legal_actions


def test_greedy_agent_deterministic():
    agent1 = GreedyAgent()
    agent2 = GreedyAgent()
    state = GameState.new_game(42)
    # Play a few turns and verify same choices
    for _ in range(5):
        if state.winner is not None:
            break
        player = state.current_player
        obs = get_observation(state, player)
        dp = decide(state)
        a1 = agent1.choose_action(obs, dp.legal_actions)
        a2 = agent2.choose_action(obs, dp.legal_actions)
        assert a1 == a2, f"Diverged at phase {dp.phase}: {a1} vs {a2}"
        state = apply(state, a1)  # apply from engine.actions


def test_greedy_agent_full_game_terminates():
    final = play_game(GreedyAgent(), GreedyAgent(), seed=0)
    assert final.winner in (0, 1)


def test_greedy_always_declines_a_voluntary_replenish():
    # Table rule: the agent never replenishes voluntarily. It returns
    # DoneWithReplenish whenever the engine offers it, and takes Replenish()
    # only when the engine offers nothing else (the forced replenish).
    agent = GreedyAgent()
    base = board_state(current_player=0, phase=Phase.REPLENISH, bag=Tokens(white=6))

    dp = decide(base)
    assert any(isinstance(a, Replenish) for a in dp.legal_actions)
    assert any(isinstance(a, DoneWithReplenish) for a in dp.legal_actions)
    action = agent.choose_action(get_observation(base, 0), dp.legal_actions)
    assert isinstance(action, DoneWithReplenish)

    # Blocked mandatory phase *and* a bag worth more than five tokens: the
    # exact position where the old "blocked AND bag > 5" rule took a voluntary
    # replenish. The table rule declines here and waits for the forced step.
    empty_handed = replace(
        base,
        board=(None,) * 25,
        players=(replace(base.players[0], tokens=Tokens()), base.players[1]),
    )
    # Precondition: MANDATORY really is blocked -- no take line, no gold on the
    # board to reserve, and nothing in the pyramid affordable with an empty hand.
    mandatory = decide(replace(empty_handed, phase=Phase.MANDATORY))
    assert [type(a) for a in mandatory.legal_actions] == [Replenish]
    dp = decide(empty_handed)
    assert any(isinstance(a, Replenish) for a in dp.legal_actions)
    assert any(isinstance(a, DoneWithReplenish) for a in dp.legal_actions)
    action = agent.choose_action(get_observation(empty_handed, 0), dp.legal_actions)
    assert isinstance(action, DoneWithReplenish)

    # Forced: MANDATORY would have no legal action, so the engine offers
    # Replenish() alone and the agent must take it.
    blocked = replace(base, phase=Phase.MANDATORY, board=(None,) * 25)
    dp = decide(blocked)
    assert [type(a) for a in dp.legal_actions] == [Replenish]
    action = agent.choose_action(get_observation(blocked, 0), dp.legal_actions)
    assert isinstance(action, Replenish)


def test_needed_colors_repeat_once_per_missing_token():
    # The needed-color list is a multiset with one entry per missing token,
    # not one entry per color: the discard scoring counts that multiset, so
    # collapsing it would change the discard tie-break.
    agent = GreedyAgent()
    card = Card(
        id="T1",
        level=1,
        points=3,
        crowns=0,
        bonus=Color.WHITE,
        bonus_count=1,
        ability=None,
        is_multicolor=False,
        cost=Tokens(white=3),
    )
    obs = _observation_with_visible_card(card, Tokens(white=1, gold=2))
    needed = agent._colors_needed_for_best_purchase(obs)
    assert needed.count(Color.WHITE) == 2
    assert needed.count(Color.BLUE) == 0


def test_greedy_buys_the_first_maximum_value_visible_card():
    # Pins the *engine's* legal-action order: `_choose_mandatory` takes the
    # first maximum among the BuyCard actions `decide()` offers, so an earlier
    # equal-value card wins. Order of `helpers.visible_cards` is a different
    # contract, pinned in
    # test_needed_colors_follow_the_visible_cards_contract_order below.
    agent = GreedyAgent()
    first = Card(
        id="A",
        level=1,
        points=3,
        crowns=0,
        bonus=Color.WHITE,
        bonus_count=1,
        ability=None,
        is_multicolor=False,
        cost=Tokens(),
    )
    second = Card(
        id="B",
        level=1,
        points=3,
        crowns=0,
        bonus=Color.BLUE,
        bonus_count=1,
        ability=None,
        is_multicolor=False,
        cost=Tokens(),
    )
    base = board_state(current_player=0, phase=Phase.MANDATORY)
    st = replace(
        base,
        players=(
            replace(base.players[0], tokens=Tokens(gold=20), bonus=Tokens()),
            base.players[1],
        ),
        pyramid=((first, second, None), (None,) * 4, (None,) * 5),
    )
    dp = decide(st)
    action = agent.choose_action(get_observation(st, 0), dp.legal_actions)
    assert isinstance(action, BuyCard)
    assert action.card.id == "A"


def test_needed_colors_follow_the_visible_cards_contract_order():
    # The order-sensitive consumer of `visible_cards` is the needed-color
    # lookup: it picks the best affordable card with max(), which returns the
    # first maximum, and that card's deficits become the multiset that drives
    # the take-action scoring. Two equally valuable cards with different costs
    # therefore flip the multiset when the helper's order changes.
    agent = GreedyAgent()
    white_card = Card(
        id="W3",
        level=1,
        points=3,
        crowns=0,
        bonus=Color.WHITE,
        bonus_count=1,
        ability=None,
        is_multicolor=False,
        cost=Tokens(white=3),
    )
    blue_card = Card(
        id="B3",
        level=1,
        points=3,
        crowns=0,
        bonus=Color.BLUE,
        bonus_count=1,
        ability=None,
        is_multicolor=False,
        cost=Tokens(blue=3),
    )
    base = board_state(current_player=0, phase=Phase.MANDATORY)
    # Both cards are affordable (two white / three blue, covered by five gold)
    # and equal in value (points*2 + crowns), so the first in helper order wins.
    hand = Tokens(white=1, gold=5)

    def needed(row: tuple[Card | None, ...]) -> list[Color]:
        st = replace(
            base,
            players=(
                replace(base.players[0], tokens=hand, bonus=Tokens()),
                base.players[1],
            ),
            pyramid=(row, (None,) * 4, (None,) * 5),
        )
        return agent._colors_needed_for_best_purchase(get_observation(st, 0))

    assert needed((white_card, blue_card, None)) == [Color.WHITE, Color.WHITE]
    assert needed((blue_card, white_card, None)) == [Color.BLUE] * 3


def test_greedy_prefers_buying_high_value_affordable_card():
    # With plenty of gold every non-multicolor pyramid card is affordable;
    # the agent must buy the one with the highest points*2 + crowns.
    base = board_state(current_player=0, phase=Phase.MANDATORY)
    st = replace(
        base,
        players=(replace(base.players[0], tokens=Tokens(gold=20)), base.players[1]),
    )
    obs = get_observation(st, 0)
    best = max(
        (
            card
            for row in obs.pyramid
            for card in row
            if card is not None and not card.is_multicolor
        ),
        key=lambda card: card.points * 2 + card.crowns,
    )
    dp = decide(st)
    action = GreedyAgent().choose_action(obs, dp.legal_actions)
    assert isinstance(action, BuyCard)
    assert action.card.id == best.id


def test_greedy_reserves_only_when_gold_needed_and_slots_available():
    agent = GreedyAgent()
    jewels, _ = load_cards()
    six_pointer = next(c for c in jewels if c.points == 6)  # L3-12
    base = board_state(current_player=0, phase=Phase.MANDATORY)

    # (a) No gold on board -> the engine offers no ReserveCard; take tokens
    board_a: list[Color | None] = [None] * 25
    board_a[0] = Color.RED
    st_a = replace(base, board=tuple(board_a))
    dp_a = decide(st_a)
    assert not any(isinstance(a, ReserveCard) for a in dp_a.legal_actions)
    action = agent.choose_action(get_observation(st_a, 0), dp_a.legal_actions)
    assert isinstance(action, TakeTokens)

    # (b) Gold on board but 3 cards reserved -> still no ReserveCard offered
    three_reserved = tuple(ReservedCard(card=c, from_deck=False) for c in jewels[:3])
    board_b: list[Color | None] = [None] * 25
    board_b[0] = Color.RED
    board_b[5] = Color.GOLD
    st_b = replace(
        base,
        board=tuple(board_b),
        players=(replace(base.players[0], reserved=three_reserved), base.players[1]),
    )
    dp_b = decide(st_b)
    assert not any(isinstance(a, ReserveCard) for a in dp_b.legal_actions)
    action = agent.choose_action(get_observation(st_b, 0), dp_b.legal_actions)
    assert isinstance(action, TakeTokens)

    # (c) Gold on board, free slot, visible 6-point card -> reserve that card
    board_c: list[Color | None] = [None] * 25
    board_c[3] = Color.GOLD
    st_c = replace(
        base,
        board=tuple(board_c),
        pyramid=((six_pointer, None, None), (None,) * 4, (None,) * 5),
    )
    dp_c = decide(st_c)
    action = agent.choose_action(get_observation(st_c, 0), dp_c.legal_actions)
    assert action == ReserveCard(source="pyramid", index=0)


def test_greedy_avoids_penalty_unless_high_value_purchase_enabled():
    # L3-12 costs white=8 and is worth 6 points. A line of 3 white tokens
    # triggers the penalty (opponent gains a privilege) but is the only way
    # to make that card affordable in one take.
    jewels, _ = load_cards()
    six_pointer = next(c for c in jewels if c.points == 6)
    agent = GreedyAgent()
    base = board_state(current_player=0, phase=Phase.MANDATORY, pyramid=EMPTY_PYRAMID)

    def make_state(hand: Tokens) -> GameState:
        board: list[Color | None] = [None] * 25
        board[0] = Color.WHITE
        board[1] = Color.WHITE
        board[2] = Color.WHITE  # penalty line of 3
        board[10] = Color.BLUE  # safe single token
        return replace(
            base,
            board=tuple(board),
            pyramid=((six_pointer, None, None), (None,) * 4, (None,) * 5),
            players=(replace(base.players[0], tokens=hand), base.players[1]),
        )

    # white=5: only the 3-line reaches white=8 -> take the penalty line
    enabling = make_state(Tokens(white=5))
    dp = decide(enabling)
    action = agent.choose_action(get_observation(enabling, 0), dp.legal_actions)
    assert action == TakeTokens((0, 1, 2))

    # white=3: no take makes the card affordable -> avoid the penalty line
    # (among penalty-free options the table's scoring picks the 2-white line)
    safe = make_state(Tokens(white=3))
    dp = decide(safe)
    action = agent.choose_action(get_observation(safe, 0), dp.legal_actions)
    assert isinstance(action, TakeTokens)
    assert action != TakeTokens((0, 1, 2))


def test_greedy_multicolor_chooses_most_bonus_color():
    # Agent has bonus: 3 white, 1 blue; multicolor card -> should choose white
    base = board_state(current_player=0)
    st = replace(
        base,
        players=(
            replace(base.players[0], bonus=Tokens(white=3, blue=1)),
            base.players[1],
        ),
    )
    obs = get_observation(st, 0)
    legal = (ChooseMulticolor(Color.BLUE), ChooseMulticolor(Color.WHITE))
    assert GreedyAgent().choose_action(obs, legal) == ChooseMulticolor(Color.WHITE)


def test_greedy_discard_prefers_excess_colors_not_needed():
    # Hand has 12 tokens, must discard 2; 4 red (not needed), 3 blue (needed
    # by the only affordable card) -> discard reds first.
    blue_card = synthetic_card("test-blue", cost=Tokens(blue=4))
    base = board_state(
        current_player=0,
        phase=Phase.DISCARD,
        pyramid=EMPTY_PYRAMID,
    )
    st = replace(
        base,
        players=(
            replace(
                base.players[0],
                tokens=Tokens(red=4, blue=3, green=2, white=2, gold=1),
                reserved=(ReservedCard(card=blue_card, from_deck=False),),
            ),
            base.players[1],
        ),
    )
    obs = get_observation(st, 0)
    dp = decide(st)
    action = GreedyAgent().choose_action(obs, dp.legal_actions)
    assert action == DiscardTokens(tokens=Tokens(red=2))


def test_greedy_use_privileges_takes_needed_color_for_best_affordable_card():
    # Reserved card costs red=4; with red=3 + gold=1 it is affordable and the
    # only missing color is red -> the privilege must take a red token.
    red_card = synthetic_card("test-red", cost=Tokens(red=4))
    base = board_state(
        current_player=0, phase=Phase.USE_PRIVILEGES, pyramid=EMPTY_PYRAMID
    )
    board: list[Color | None] = [None] * 25
    board[0] = Color.WHITE
    board[5] = Color.BLUE
    board[7] = Color.RED
    st = replace(
        base,
        board=tuple(board),
        players=(
            replace(
                base.players[0],
                tokens=Tokens(red=3, gold=1),
                privileges=1,
                reserved=(ReservedCard(card=red_card, from_deck=False),),
            ),
            base.players[1],
        ),
    )
    dp = decide(st)
    action = GreedyAgent().choose_action(get_observation(st, 0), dp.legal_actions)
    assert action == UsePrivilege(index=7)


def test_greedy_use_privileges_takes_contested_color_when_nothing_affordable():
    # Nothing affordable -> take the least abundant non-gold color on board.
    base = board_state(
        current_player=0, phase=Phase.USE_PRIVILEGES, pyramid=EMPTY_PYRAMID
    )
    board: list[Color | None] = [None] * 25
    board[0] = Color.WHITE
    board[1] = Color.WHITE
    board[2] = Color.WHITE  # white x3
    board[5] = Color.BLUE
    board[6] = Color.BLUE  # blue x2
    board[10] = Color.RED  # red x1 -> contested
    st = replace(
        base,
        board=tuple(board),
        players=(replace(base.players[0], privileges=1), base.players[1]),
    )
    dp = decide(st)
    action = GreedyAgent().choose_action(get_observation(st, 0), dp.legal_actions)
    assert action == UsePrivilege(index=10)


def test_greedy_royal_prefers_extra_turn_ability():
    base = board_state(current_player=0)
    obs = get_observation(base, 0)
    extra = next(r for r in obs.royals_available if r.ability == Ability.EXTRA_TURN)
    no_ability = next(r for r in obs.royals_available if r.ability is None)
    legal = (ChooseRoyal(royal_id=no_ability.id), ChooseRoyal(royal_id=extra.id))
    assert GreedyAgent().choose_action(obs, legal) == ChooseRoyal(royal_id=extra.id)


def test_greedy_payment_prefers_fewest_gold_then_fewest_tokens():
    base = board_state(current_player=0)
    obs = get_observation(base, 0)
    legal = (
        PayTokens(payment=Tokens(gold=4)),
        PayTokens(payment=Tokens(white=2, gold=2)),
        PayTokens(payment=Tokens(white=4)),
    )
    assert GreedyAgent().choose_action(obs, legal) == PayTokens(payment=Tokens(white=4))
