import pytest

from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.play.human import HumanAgent


def _scripted_input(answers: list[str]):
    it = iter(answers)
    return lambda _prompt="": next(it)


def test_human_agent_full_game_with_scripted_input():
    # Scripted human always answers "0" (first legal action); game must run
    # to completion (enough answers: worst case many turns; pad generously).
    answers = ["0"] * 2000
    human = HumanAgent(input_fn=_scripted_input(answers), print_fn=lambda *a, **k: None)
    final = play_game(human, RandomAgent(seed=7), seed=3)
    assert final.winner in (0, 1)


def test_human_agent_reprompts_on_invalid_input():
    outputs = []
    # "abc" invalid, "99" out of range, then "0" valid
    human = HumanAgent(
        input_fn=_scripted_input(["abc", "99", "0"]),
        print_fn=lambda *a, **k: outputs.append(" ".join(str(x) for x in a)),
    )
    from splendor_duel_engine.engine.actions import decide
    from splendor_duel_engine.engine.observation import observation
    from splendor_duel_engine.engine.state import GameState

    state = GameState.new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = human.choose_action(obs, dp.legal_actions)
    assert action == dp.legal_actions[0]
    assert any("invalid" in o.lower() for o in outputs)  # re-prompt happened


def test_human_agent_renders_observation_not_hidden_info():
    rendered = []
    human = HumanAgent(
        input_fn=_scripted_input(["0"]),
        print_fn=lambda *a, **k: rendered.append(" ".join(str(x) for x in a)),
    )
    from splendor_duel_engine.engine.actions import decide
    from splendor_duel_engine.engine.observation import observation
    from splendor_duel_engine.engine.state import GameState

    state = GameState.new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    human.choose_action(obs, dp.legal_actions)
    text = "\n".join(rendered)
    # Sanity: board and hand shown.
    assert len(text) > 0
    # Hidden-info discipline: no deck contents leak (only counts). Every card
    # identity that appears in the render must come from a public source
    # (pyramid, royals, the player's own reserved/purchased cards, or the
    # opponent's public reserved/purchased cards) — never from a deck.
    public_ids: set[str] = set()
    public_ids |= {c.id for row in obs.pyramid for c in row if c is not None}
    public_ids |= {r.id for r in obs.royals_available}
    public_ids |= {c.id for c in obs.you.reserved_public}
    public_ids |= {c.id for c in obs.your_reserved_deck}
    public_ids |= {pc.card.id for pc in obs.you.purchased}
    public_ids |= {c.id for c in obs.opponent.reserved_public}
    public_ids |= {pc.card.id for pc in obs.opponent.purchased}
    all_card_ids: set[str] = set(public_ids)
    for deck in state.decks:
        for card in deck:
            all_card_ids.add(card.id)
    # Opponent's hidden (deck-reserved) cards are not in the Observation, but
    # state is only used here to enumerate every possible card identity; the
    # render must not surface any of the hidden ones.
    rendered_ids = {tok for tok in text.split() if tok in all_card_ids}
    assert rendered_ids <= public_ids
    # Explicit deck-top check (redundant with the comparison above, but cheap).
    for deck in state.decks:
        for card in deck:
            assert card.id not in text


def test_human_agent_input_terminated():
    outputs = []

    def _raising(_prompt=""):
        raise StopIteration

    human = HumanAgent(
        input_fn=_raising,
        print_fn=lambda *a, **k: outputs.append(" ".join(str(x) for x in a)),
    )
    from splendor_duel_engine.engine.actions import decide
    from splendor_duel_engine.engine.observation import observation
    from splendor_duel_engine.engine.state import GameState

    state = GameState.new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    with pytest.raises(SystemExit):
        human.choose_action(obs, dp.legal_actions)
    assert any("terminated" in o.lower() for o in outputs)


def test_human_agent_eof_terminated():
    outputs = []

    def _raising(_prompt=""):
        raise EOFError

    human = HumanAgent(
        input_fn=_raising,
        print_fn=lambda *a, **k: outputs.append(" ".join(str(x) for x in a)),
    )
    from splendor_duel_engine.engine.actions import decide
    from splendor_duel_engine.engine.observation import observation
    from splendor_duel_engine.engine.state import GameState

    state = GameState.new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    with pytest.raises(SystemExit):
        human.choose_action(obs, dp.legal_actions)
    assert any("terminated" in o.lower() for o in outputs)
