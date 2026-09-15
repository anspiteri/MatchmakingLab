"""
generator_test.py
~~~~~~~~~~~~~~~~~

Tests the BradleyTerry request generator and the factory that wires it
together with the strategy platform.
"""

from matchmakinglab.core.models import LATENCY_KEY, REGION_KEY
from matchmakinglab.matchmakers import BTCandidateGenerationMethod
from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry.generator import BradleyTerryGenerator
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry
from matchmakinglab.matchmakers.factory import (
    BradleyTerryFactory,
    MatchmakerFactory,
)
from matchmakinglab.platform.platform import Platform

# ---------- BradleyTerryGenerator ----------


def test_generate_requests_returns_expected_count():
    gen = BradleyTerryGenerator(player_count=50)

    requests = gen.generate_requests(10)

    assert len(requests) == 10


def test_generated_requests_have_features():
    gen = BradleyTerryGenerator(player_count=50, seed=1)

    req = gen.generate_requests(1)[0]

    assert "user" in req
    assert LATENCY_KEY in req["req_features"]
    assert REGION_KEY in req["req_features"]
    assert 5 <= req["req_features"][LATENCY_KEY] <= 120


def test_generate_requests_emits_distinct_usernames_within_pool():
    gen = BradleyTerryGenerator(player_count=100)

    usernames = [req["user"] for req in gen.generate_requests(100)]

    assert len(set(usernames)) == 100


def test_generate_requests_rotates_after_pool_exhausted():
    gen = BradleyTerryGenerator(player_count=3)

    usernames = [req["user"] for req in gen.generate_requests(5)]

    assert usernames[0] == usernames[3]  # pool wraps around
    assert len(set(usernames)) == 3


def test_generate_requests_is_seeded_reproducibly():
    first = BradleyTerryGenerator(player_count=500, seed=42)
    second = BradleyTerryGenerator(player_count=500, seed=42)

    assert first.generate_requests(10) == second.generate_requests(10)


def test_generate_requests_differs_across_seeds():
    first = BradleyTerryGenerator(player_count=500, seed=42)
    second = BradleyTerryGenerator(player_count=500, seed=7)

    assert first.generate_requests(50) != second.generate_requests(50)


# ---------- BradleyTerryFactory ----------


def test_factory_implements_matchmaker_factory_interface():
    assert isinstance(BradleyTerryFactory(), MatchmakerFactory)


def test_factory_defaults():
    factory = BradleyTerryFactory()

    assert isinstance(factory.create_platform(), Platform)
    assert isinstance(factory.create_platform().strategy, BradleyTerry)
    assert isinstance(factory.create_generator(), RequestGenerator)
    assert isinstance(factory.create_generator(), BradleyTerryGenerator)


def test_factory_passes_config_to_strategy():
    factory = BradleyTerryFactory(
        {"candidate_generation_method": BTCandidateGenerationMethod.NAIVE}
    )

    platform = factory.create_platform()

    assert platform.strategy._candidate_generation_method == (
        BTCandidateGenerationMethod.NAIVE
    )