"""Game phases as defined by the spec."""

from __future__ import annotations

import enum


class Phase(enum.Enum):
    USE_PRIVILEGES = "use_privileges"
    REPLENISH = "replenish"
    MANDATORY = "mandatory"
    CHOOSE_PAYMENT = "choose_payment"
    MULTICOLOR_COLOR = "multicolor_color"
    STEAL_TOKEN = "steal_token"
    CHOOSE_ROYAL = "choose_royal"
    DISCARD = "discard"
    GAME_OVER = "game_over"
