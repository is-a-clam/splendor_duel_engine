"""Tests for card abilities and multicolor accounting (Task 6)."""

from dataclasses import replace

import pytest

from splendor_duel_engine.engine.actions import (
    BuyCard,
    ChooseMatchingToken,
    ChooseMulticolor,
    ChooseStealToken,
    DoneWithPrivileges,
    DoneWithReplenish,
    PayTokens,
    apply,
    decide,
)
from splendor_duel_engine.engine.cards import Ability, load_cards
from splendor_duel_engine.engine.colors import Color, Tokens
from splendor_duel_engine.engine.phase import Phase
from splendor_duel_engine.engine.state import GameState, ReservedCard, new_game


def _setup_buy_state(base_st: GameState, player: int = 0) -> tuple[GameState, object]:
    """Helper: set up a state where player can buy a card, returns state after BuyCard, before PayTokens."""
    # Give player lots of gold and a colored bonus
    st = replace(
        base_st,
        current_player=player,
        phase=Phase.MANDATORY,
        players=(
            replace(
                base_st.players[player],
                bonus=Tokens(white=1),
                tokens=Tokens(gold=20),
            ),
            base_st.players[1 - player],
        ),
    )
    return st, player


def _complete_buy(st: GameState, card) -> GameState:
    """Execute BuyCard then PayTokens for the given card."""
    dp = decide(st)
    buy_actions = [
        a for a in dp.legal_actions if isinstance(a, BuyCard) and a.card.id == card.id
    ]
    assert len(buy_actions) == 1
    st = apply(st, buy_actions[0])
    assert st.phase is Phase.CHOOSE_PAYMENT
    dp2 = decide(st)
    pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
    assert len(pay_actions) > 0
    st = apply(st, pay_actions[0])
    return st


class TestExtraTurn:
    def test_extra_turn_same_player_plays_again(self):
        """EXTRA_TURN ability: after purchase, same player gets another turn (USE_PRIVILEGES)."""
        base_st = new_game(0)
        # Find a card with extra_turn ability - L1-01
        base_st.pyramid[0][0]  # Check this has extra_turn
        # L1-01 has extra_turn but let's find it properly
        jewels, _ = load_cards()
        extra_turn_card = next(
            c for c in jewels if c.ability == Ability.EXTRA_TURN and c.level == 1
        )
        # Put it in reserved for easy access
        reserved = ReservedCard(card=extra_turn_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )
        # Remove from pyramid
        new_pyramid = [list(r) for r in base_st.pyramid]
        # Find and remove the card
        for r_idx, row in enumerate(new_pyramid):
            for c_idx, c in enumerate(row):
                if c and c.id == extra_turn_card.id:
                    new_pyramid[r_idx][c_idx] = None
        st = replace(st, pyramid=tuple(tuple(r) for r in new_pyramid))

        st = _complete_buy(st, extra_turn_card)

        # After purchase with EXTRA_TURN, should be in USE_PRIVILEGES for SAME player
        assert st.phase is Phase.USE_PRIVILEGES
        assert st.current_player == 0
        assert st.extra_turn is True

        # Complete the extra turn cycle: USE_PRIVILEGES -> REPLENISH -> MANDATORY
        st = apply(st, DoneWithPrivileges())
        assert st.phase is Phase.REPLENISH
        assert st.current_player == 0
        st = apply(st, DoneWithReplenish())
        assert st.phase is Phase.MANDATORY
        assert st.current_player == 0  # Still same player due to extra_turn
        assert st.extra_turn is False  # Flag cleared after use

    def test_extra_turn_flag_cleared_after_extra_turn_used(self):
        """The extra_turn flag is set on purchase, then cleared after the extra turn completes."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        extra_turn_card = next(
            c for c in jewels if c.ability == Ability.EXTRA_TURN and c.level == 1
        )
        reserved = ReservedCard(card=extra_turn_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )
        new_pyramid = [list(r) for r in base_st.pyramid]
        for r_idx, row in enumerate(new_pyramid):
            for c_idx, c in enumerate(row):
                if c and c.id == extra_turn_card.id:
                    new_pyramid[r_idx][c_idx] = None
        st = replace(st, pyramid=tuple(tuple(r) for r in new_pyramid))

        st = _complete_buy(st, extra_turn_card)
        assert st.extra_turn is True

        # Go through the extra turn
        st = apply(st, DoneWithPrivileges())
        st = apply(st, DoneWithReplenish())
        assert st.phase is Phase.MANDATORY
        assert st.extra_turn is False


class TestTakeMatchingToken:
    def test_take_matching_token_chooses_from_board(self):
        """TAKE_MATCHING_TOKEN: enters TAKE_MATCHING_TOKEN phase, player chooses which token to take."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # Find a card with take_matching_token ability - L1-02 (bonus=black)
        take_match_card = next(
            c
            for c in jewels
            if c.ability == Ability.TAKE_MATCHING_TOKEN and c.bonus == Color.BLACK
        )
        reserved = ReservedCard(card=take_match_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            board=tuple([None] * 25),
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )
        # Place black tokens on board at indices 0 and 5
        board = list(st.board)
        board[0] = Color.BLACK
        board[5] = Color.BLACK
        st = replace(st, board=tuple(board))

        st = _complete_buy(st, take_match_card)

        # Should enter TAKE_MATCHING_TOKEN phase
        assert st.phase is Phase.TAKE_MATCHING_TOKEN
        assert st.pending_ability == Ability.TAKE_MATCHING_TOKEN

        # Legal actions should be ChooseMatchingToken for each black token
        dp = decide(st)
        choose_actions = [a for a in dp.legal_actions if isinstance(a, ChooseMatchingToken)]
        assert len(choose_actions) == 2
        choose_indices = {a.index for a in choose_actions}
        assert choose_indices == {0, 5}

        # Choose index 0
        choose_action = next(a for a in choose_actions if a.index == 0)
        st = apply(st, choose_action)

        # Token at index 0 should be taken
        assert st.board[0] is None
        # Token at index 5 should remain
        assert st.board[5] == Color.BLACK
        # Player should have gained 1 black token
        assert st.players[0].tokens.black == 1
        # Should return to USE_PRIVILEGES for same player
        assert st.phase is Phase.USE_PRIVILEGES

    def test_take_matching_token_ignored_when_absent(self):
        """TAKE_MATCHING_TOKEN: ignored (no error) if no token of that color on board."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        take_match_card = next(
            c
            for c in jewels
            if c.ability == Ability.TAKE_MATCHING_TOKEN and c.bonus == Color.BLACK
        )
        reserved = ReservedCard(card=take_match_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            board=tuple([None] * 25),
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )
        # No black tokens on board
        board = list(st.board)
        board[0] = Color.RED  # Different color
        st = replace(st, board=tuple(board))

        st = _complete_buy(st, take_match_card)

        # Should not error; board unchanged for that color
        assert st.board[0] == Color.RED
        assert st.players[0].tokens.black == 0


class TestPrivilegeAbility:
    def test_privilege_ability_grants_privilege(self):
        """PRIVILEGE ability: grants 1 privilege to buyer via _grant_privilege."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # Find a card with privilege ability - L2-12 (bonus=black)
        priv_card = next(
            c
            for c in jewels
            if c.ability == Ability.PRIVILEGE and c.bonus == Color.BLACK
        )
        reserved = ReservedCard(card=priv_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                    privileges=0,
                ),
                replace(base_st.players[1], privileges=0),
            ),
            privileges_supply=3,  # Full supply
        )

        st = _complete_buy(st, priv_card)

        # Buyer should have gained 1 privilege from supply
        assert st.players[0].privileges == 1
        assert st.privileges_supply == 2


class TestStealToken:
    def test_steal_takes_chosen_non_gold_opponent_token_and_cannot_steal_gold(self):
        """STEAL_TOKEN: enters STEAL_TOKEN phase, player chooses non-gold token from opponent; gold immune."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        steal_card = next(
            c
            for c in jewels
            if c.ability == Ability.STEAL_TOKEN and c.bonus == Color.BLACK
        )
        reserved = ReservedCard(card=steal_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                replace(
                    base_st.players[1],
                    tokens=Tokens(
                        white=2, blue=1, gold=3
                    ),  # Opponent has tokens including gold
                ),
            ),
        )

        st = _complete_buy(st, steal_card)

        # Should enter STEAL_TOKEN phase for the buyer (player 0)
        assert st.phase is Phase.STEAL_TOKEN
        assert st.current_player == 0
        assert st.pending_ability == Ability.STEAL_TOKEN

        # Legal actions should be ChooseStealToken for each non-gold color opponent has
        dp = decide(st)
        steal_actions = [a for a in dp.legal_actions if isinstance(a, ChooseStealToken)]
        # Opponent has white and blue (non-gold), so 2 choices
        assert len(steal_actions) == 2
        steal_colors = {a.color for a in steal_actions}
        assert steal_colors == {Color.WHITE, Color.BLUE}
        # Gold should NOT be an option
        assert Color.GOLD not in steal_colors

        # Choose white
        white_steal = next(a for a in steal_actions if a.color == Color.WHITE)
        st = apply(st, white_steal)

        # Opponent loses 1 white, buyer gains 1 white
        assert st.players[1].tokens.white == 1
        assert st.players[0].tokens.white == 1
        # Gold should be reduced by payment amount (card costs 4 white + 3 green = 7, paid with gold)
        # We don't assert exact gold amount since payment enumeration may vary,
        # but gold should be less than 20
        assert st.players[0].tokens.gold < 20

        # Should return to USE_PRIVILEGES for same player
        assert st.phase is Phase.USE_PRIVILEGES
        assert st.current_player == 0
        assert st.pending_ability is None

    def test_steal_ignored_when_opponent_has_no_tokens(self):
        """STEAL_TOKEN: if opponent has no non-gold tokens, ability is ignored (no phase)."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        steal_card = next(
            c
            for c in jewels
            if c.ability == Ability.STEAL_TOKEN and c.bonus == Color.BLACK
        )
        reserved = ReservedCard(card=steal_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                replace(base_st.players[1], tokens=Tokens()),  # Opponent has NO tokens
            ),
        )

        st = _complete_buy(st, steal_card)

        # Should NOT enter STEAL_TOKEN phase; should go straight to USE_PRIVILEGES
        assert st.phase is Phase.USE_PRIVILEGES
        assert st.current_player == 0
        assert st.pending_ability is None


class TestMulticolor:
    def test_multicolor_choose_color_adds_bonus_and_counts_for_that_color(self):
        """MULTICOLOR_COLOR: player chooses color; bonus_count added to that color; prestige counts toward that color."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # Find a multicolor card with bonus_count=1 - L1-18
        multi_card = next(
            c for c in jewels if c.is_multicolor and c.bonus_count == 1 and c.level == 1
        )
        reserved = ReservedCard(card=multi_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),  # Need colored bonus to buy multicolor
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )

        # Buy the card
        dp = decide(st)
        buy_actions = [
            a
            for a in dp.legal_actions
            if isinstance(a, BuyCard) and a.card.id == multi_card.id
        ]
        assert len(buy_actions) == 1
        st = apply(st, buy_actions[0])
        assert st.phase is Phase.CHOOSE_PAYMENT
        dp2 = decide(st)
        pay_actions = [a for a in dp2.legal_actions if isinstance(a, PayTokens)]
        st = apply(st, pay_actions[0])

        # Should enter MULTICOLOR_COLOR phase
        assert st.phase is Phase.MULTICOLOR_COLOR
        assert st.current_player == 0
        assert st.pending_ability is None  # Multicolor is not an Ability enum
        # The pending_buy should store the card for multicolor resolution
        assert st.pending_buy is not None

        # Legal actions: ChooseMulticolor for each color where bonus.count > 0
        dp3 = decide(st)
        color_actions = [
            a for a in dp3.legal_actions if isinstance(a, ChooseMulticolor)
        ]
        # Player has white bonus, so white should be available
        assert len(color_actions) >= 1
        white_action = next(a for a in color_actions if a.color == Color.WHITE)
        st = apply(st, white_action)

        # After choice: chosen_color set on PurchasedCard
        purchased = st.players[0].purchased[-1]
        assert purchased.chosen_color == Color.WHITE
        # Bonus should be added: white bonus += bonus_count (1)
        assert st.players[0].bonus.white == 2  # Started with 1, gained 1
        # Prestige should count toward white for 10-point win check
        # (Task 8 will read this, but we verify chosen_color is set)

        # Should return to USE_PRIVILEGES
        assert st.phase is Phase.USE_PRIVILEGES
        assert st.current_player == 0

    def test_multicolor_copies_only_bonus_not_ability(self):
        """Multicolor copies the bonus, never an ability: multicolor-only card fires no extra ability."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # Find a multicolor card with NO ability - L1-18
        multi_card = next(
            c for c in jewels if c.is_multicolor and c.ability is None and c.level == 1
        )
        reserved = ReservedCard(card=multi_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )

        st = _complete_buy(st, multi_card)

        # Should go through MULTICOLOR_COLOR phase
        assert st.phase is Phase.MULTICOLOR_COLOR
        dp = decide(st)
        color_actions = [a for a in dp.legal_actions if isinstance(a, ChooseMulticolor)]
        white_action = next(a for a in color_actions if a.color == Color.WHITE)
        st = apply(st, white_action)

        # After multicolor resolution, no other ability should fire
        # Should be back to USE_PRIVILEGES
        assert st.phase is Phase.USE_PRIVILEGES
        # No extra_turn, no privilege granted, no steal, no take_matching
        assert st.extra_turn is False
        assert st.pending_ability is None

    def test_multicolor_with_extra_turn_still_plays_again(self):
        """L3-01 (multicolor + extra_turn) still grants extra turn (Ruling R3)."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # L3-01 is multicolor AND has extra_turn
        multi_extra_card = next(c for c in jewels if c.id == "L3-01")
        assert multi_extra_card.is_multicolor
        assert multi_extra_card.ability == Ability.EXTRA_TURN
        reserved = ReservedCard(card=multi_extra_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )

        # Buy -> PayTokens -> MULTICOLOR_COLOR -> ChooseMulticolor -> extra_turn flag set -> USE_PRIVILEGES
        st = _complete_buy(st, multi_extra_card)
        assert st.phase is Phase.MULTICOLOR_COLOR

        dp = decide(st)
        color_actions = [a for a in dp.legal_actions if isinstance(a, ChooseMulticolor)]
        white_action = next(a for a in color_actions if a.color == Color.WHITE)
        st = apply(st, white_action)

        # After multicolor choice, EXTRA_TURN should fire
        assert st.phase is Phase.USE_PRIVILEGES
        assert st.current_player == 0
        assert st.extra_turn is True


class TestAbilityResolutionOrder:
    def test_bought_card_ability_resolves_before_next_player_turns(self):
        """Abilities resolve in fixed order before turn passes to next player."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # Find a card with multiple abilities? Cards have at most one printed ability.
        # But multicolor + ability combination tests the order.
        # Use L3-01 (multicolor + extra_turn)
        multi_extra_card = next(c for c in jewels if c.id == "L3-01")
        reserved = ReservedCard(card=multi_extra_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                base_st.players[1],
            ),
        )

        # Complete purchase
        st = _complete_buy(st, multi_extra_card)

        # Should enter MULTICOLOR_COLOR first (multicolor resolution)
        assert st.phase is Phase.MULTICOLOR_COLOR

        # Choose color
        dp = decide(st)
        color_actions = [a for a in dp.legal_actions if isinstance(a, ChooseMulticolor)]
        st = apply(st, color_actions[0])

        # Then EXTRA_TURN should fire (extra_turn flag set)
        assert st.phase is Phase.USE_PRIVILEGES
        assert st.extra_turn is True
        assert st.current_player == 0

    def test_multicolor_then_steal_token_order(self):
        """MULTICOLOR_COLOR resolves before STEAL_TOKEN; multicolor card without STEAL_TOKEN skips steal phase."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # Find a multicolor card (e.g., L1-24) - these don't have STEAL_TOKEN
        multicolor_card = next(
            c
            for c in jewels
            if c.is_multicolor and c.ability != Ability.STEAL_TOKEN
        )
        reserved = ReservedCard(card=multicolor_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),  # Has colored bonus for multicolor choice
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                replace(base_st.players[1], tokens=Tokens(white=1)),  # Opponent has stealable token
            ),
        )

        # Buy the multicolor card
        st = _complete_buy(st, multicolor_card)

        # Should enter MULTICOLOR_COLOR phase (not STEAL_TOKEN)
        assert st.phase is Phase.MULTICOLOR_COLOR
        assert st.pending_ability is None  # No pending ability during multicolor choice

        # Choose a color
        dp = decide(st)
        choose_color = next(a for a in dp.legal_actions if isinstance(a, ChooseMulticolor))
        st = apply(st, choose_color)

        # After multicolor resolution, should continue to next abilities
        # Since this card has no STEAL_TOKEN, should NOT enter STEAL_TOKEN phase
        # and should proceed through remaining abilities to USE_PRIVILEGES
        assert st.phase is Phase.USE_PRIVILEGES
        assert st.pending_buy is None

    def test_steal_token_ability_check_gated(self):
        """STEAL_TOKEN phase only entered when card has the ability, not just multicolor."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        # Find a multicolor card WITHOUT STEAL_TOKEN
        multicolor_no_steal = next(
            c
            for c in jewels
            if c.is_multicolor and c.ability != Ability.STEAL_TOKEN
        )
        reserved = ReservedCard(card=multicolor_no_steal, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                replace(base_st.players[1], tokens=Tokens(white=1)),  # Opponent has stealable token
            ),
        )

        # Buy the multicolor card (no STEAL_TOKEN ability)
        st = _complete_buy(st, multicolor_no_steal)

        # Choose multicolor
        st = apply(st, next(a for a in decide(st).legal_actions if isinstance(a, ChooseMulticolor)))

        # Should NOT enter STEAL_TOKEN phase (card lacks the ability)
        assert st.phase is Phase.USE_PRIVILEGES


class TestPendingAbilityField:
    def test_pending_ability_stores_steal_token_during_choice(self):
        """pending_ability field stores STEAL_TOKEN during the choice phase."""
        base_st = new_game(0)
        jewels, _ = load_cards()
        steal_card = next(
            c
            for c in jewels
            if c.ability == Ability.STEAL_TOKEN and c.bonus == Color.BLACK
        )
        reserved = ReservedCard(card=steal_card, from_deck=False)
        st = replace(
            base_st,
            current_player=0,
            phase=Phase.MANDATORY,
            players=(
                replace(
                    base_st.players[0],
                    bonus=Tokens(white=1),
                    tokens=Tokens(gold=20),
                    reserved=(reserved,),
                ),
                replace(base_st.players[1], tokens=Tokens(white=1)),
            ),
        )

        st = _complete_buy(st, steal_card)

        assert st.phase is Phase.STEAL_TOKEN
        assert st.pending_ability == Ability.STEAL_TOKEN

        # After choosing, pending_ability cleared
        dp = decide(st)
        steal_action = next(
            a for a in dp.legal_actions if isinstance(a, ChooseStealToken)
        )
        st = apply(st, steal_action)
        assert st.pending_ability is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
