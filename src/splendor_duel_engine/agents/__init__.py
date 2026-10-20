"""Agents that play Splendor Duel via the observation and action APIs."""

from __future__ import annotations

from splendor_duel_engine.agents.base import Agent, play_game
from splendor_duel_engine.agents.greedy_agent import GreedyAgent
from splendor_duel_engine.agents.random_agent import RandomAgent

__all__ = ["Agent", "GreedyAgent", "RandomAgent", "play_game"]
