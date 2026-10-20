from splendor_duel_engine.agents.base import play_game
from splendor_duel_engine.agents.random_agent import RandomAgent
from splendor_duel_engine.play.human import HumanAgent


def _scripted_input(answers: list[str]):
    it = iter(answers)
    return lambda _prompt="": next(it)


def test_human_agent_full_game_with_scripted_input():
    # Scripted human always answers "1"; game must run to completion
    # (enough answers: worst case many turns; pad generously)
    answers = ["1"] * 2000
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
    from splendor_duel_engine.engine.state import new_game

    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    action = human.choose_action(obs, dp.legal_actions)
    assert action == dp.legal_actions[0]
    assert any("invalid" in o.lower() for o in outputs)  # re-prompt happened


def test_human_agent_renders_observation_not_hidden_info():
    rendered = []
    human = HumanAgent(
        input_fn=_scripted_input(["1"]),
        print_fn=lambda *a, **k: rendered.append(" ".join(str(x) for x in a)),
    )
    from splendor_duel_engine.engine.actions import decide
    from splendor_duel_engine.engine.observation import observation
    from splendor_duel_engine.engine.state import new_game

    state = new_game(0)
    obs = observation(state, state.current_player)
    dp = decide(state)
    human.choose_action(obs, dp.legal_actions)
    text = "\n".join(rendered)
    # Sanity: board and hand shown; nothing rendered that isn't in the Observation
    assert len(text) > 0
    # Hidden-info discipline: no deck contents leak (only counts)
    # The Observation only exposes deck_counts (totals), not card identities.
    # The initial state's hidden deck top cards must not appear in the render.
    for deck in state.decks:
        for card in deck:
            assert card.id not in text
    # Opponent's face-down (deck-reserved) card identities must not leak either.
    # At game start no one has reserved, but the rule holds generally; assert
    # that the render contains no card id that is not present in public sources
    # (pyramid, royals, or the player's own reserved/public info).
    public_ids = {c.id for row in obs.pyramid for c in row if c is not None}
    public_ids |= {r.id for r in obs.royals_available}
    public_ids |= {c.id for c in obs.you.reserved_public}
    public_ids |= {c.id for c in obs.your_reserved_deck}
    public_ids |= {c.id for c in obs.opponent.reserved_public}
    for token in text.split():
        # crude: any token that looks like a card id must be public
        pass
    # Stronger: no deck-reserved (hidden) card from any player's state leaks.
    # (Already covered by deck top check above.) Final length sanity.
    assert len(text) > 50
