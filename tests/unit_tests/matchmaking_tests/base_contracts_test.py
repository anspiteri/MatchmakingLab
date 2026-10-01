"""
base_contracts_test.py
~~~~~~~~~~~~~~~~~~~~~~

Tests the abstract base classes that define the pluggable matchmaker
contracts. The abstract methods are declared but their bodies are bare, so
these lock in both the "must be overridden" requirement and the behaviour of
the inherited default bodies.
"""

import pytest

from matchmakinglab.core.models import FinishedMatch, MatchRequest
from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.base_strategy import MatchmakingStrategy
from matchmakinglab.matchmakers.factory import MatchmakerFactory
from tests.helpers import make_player

# ---------- RequestGenerator ----------


def test_request_generator_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        RequestGenerator()


def test_request_generator_subclass_must_override():
    class Incomplete(RequestGenerator):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_request_generator_default_body_returns_none():
    class Delegating(RequestGenerator):
        def generate_requests(self, number, player_database):
            return super().generate_requests(number, player_database)

    assert Delegating().generate_requests(5, {}) is None


# ---------- MatchmakingStrategy ----------


def test_matchmaking_strategy_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        MatchmakingStrategy()


def test_matchmaking_strategy_subclass_must_override_all_methods():
    class Incomplete(MatchmakingStrategy):
        pass

    with pytest.raises(TypeError):
        Incomplete()

    class OnlySetup(MatchmakingStrategy):
        def setup_player_features(self):
            return {}

    with pytest.raises(TypeError):
        OnlySetup()


def test_matchmaking_strategy_default_bodies_return_none():
    class Delegating(MatchmakingStrategy):
        def setup_player_features(self):
            return super().setup_player_features()

        def update_player_features(self, finished_match):
            return super().update_player_features(finished_match)

        def run_algorithm(self, queue_snapshot):
            return super().run_algorithm(queue_snapshot)

    strategy = Delegating()

    assert strategy.setup_player_features() is None
    assert strategy.update_player_features(FinishedMatch(0)) is None
    assert strategy.run_algorithm([MatchRequest(make_player())]) is None


# ---------- MatchmakerFactory ----------


def test_matchmaker_factory_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        MatchmakerFactory()


def test_matchmaker_factory_subclass_must_override():
    class Incomplete(MatchmakerFactory):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_matchmaker_factory_default_bodies_return_none():
    class Delegating(MatchmakerFactory):
        def create_platform(self):
            return super().create_platform()

        def create_generator(self, player_count):
            return super().create_generator(player_count)

    factory = Delegating()

    assert factory.create_platform() is None
    assert factory.create_generator(10) is None
