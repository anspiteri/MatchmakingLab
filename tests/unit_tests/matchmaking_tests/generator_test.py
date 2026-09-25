"""
generator_test.py
~~~~~~~~~~~~~~~~~

Tests the BradleyTerry request generator and the factory that wires it
together with the strategy platform.
"""

import random

import pytest

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
    Player,
    PlayerStatus,
    Region,
)
from matchmakinglab.matchmakers import BTCandidateGenerationMethod
from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry.generator import (
    BradleyTerryGenerator,
    _gen_existing_player_request,
)
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry
from matchmakinglab.matchmakers.factory import (
    BradleyTerryFactory,
    MatchmakerFactory,
)
from matchmakinglab.platform.platform import Platform

# ---------- BradleyTerryGenerator ----------


def test_generate_requests_returns_expected_count():
    gen = BradleyTerryGenerator(player_count=50)

    requests = gen.generate_requests(10, {})

    assert len(requests) == 10


def test_generated_requests_have_features():
    gen = BradleyTerryGenerator(player_count=50, seed=1)

    req = gen.generate_requests(1, {})[0]

    assert "user" in req
    assert LATENCY_KEY in req["req_features"]
    assert REGION_KEY in req["req_features"]
    assert 5 <= req["req_features"][LATENCY_KEY] <= 120


def test_generate_requests_emits_distinct_usernames_within_pool():
    gen = BradleyTerryGenerator(player_count=100)

    usernames = [req["user"] for req in gen.generate_requests(100, {})]

    assert len(set(usernames)) == 100


def test_generate_requests_rejects_batch_larger_than_pool():
    gen = BradleyTerryGenerator(player_count=3)

    with pytest.raises(ValueError, match="greater than max allowed players"):
        gen.generate_requests(5, {})


def test_generate_requests_reuses_pool_players_once_exhausted():
    gen = BradleyTerryGenerator(player_count=3)

    database: dict[str, Player] = {}
    for req in gen.generate_requests(3, database):
        database[req["user"]] = Player(0, req["user"], Region.OCEANIA)

    requests = gen.generate_requests(5, database)

    assert requests
    assert all(req["user"] in database for req in requests)
    assert len({req["user"] for req in requests}) <= 3


def test_generate_requests_is_seeded_reproducibly():
    first = BradleyTerryGenerator(player_count=500, seed=42)
    second = BradleyTerryGenerator(player_count=500, seed=42)

    assert first.generate_requests(10, {}) == second.generate_requests(10, {})


def test_generate_requests_differs_across_seeds():
    first = BradleyTerryGenerator(player_count=500, seed=42)
    second = BradleyTerryGenerator(player_count=500, seed=7)

    assert first.generate_requests(50, {}) != second.generate_requests(50, {})


# ---------- Mixed / existing-player generation ----------


def _seed_database(
    gen: BradleyTerryGenerator, count: int, region: Region = Region.OCEANIA
) -> dict[str, Player]:
    database: dict[str, Player] = {}
    for req in gen.generate_requests(count, {}):
        database[req["user"]] = Player(len(database), req["user"], region)
    return database


def test_generate_requests_mixes_new_and_existing_with_partial_database():
    # Four new signups fill the database while six pool slots remain, so a
    # larger batch must mix new players and existing pullbacks.
    gen = BradleyTerryGenerator(player_count=10, seed=42)
    database = _seed_database(gen, 4)

    requests = gen.generate_requests(10, database)

    assert len(requests) == 10
    users = {req["user"] for req in requests}
    existing = set(database)
    assert users & existing  # pulled back existing players
    assert users - existing  # still signed up new players
    assert users - existing == {f"player_{i:04d}" for i in range(4, 10)}


def test_generate_requests_with_partial_database_is_seeded_reproducibly():
    def run(seed):
        gen = BradleyTerryGenerator(player_count=10, seed=seed)
        database = _seed_database(gen, 4)
        return gen.generate_requests(10, database)

    assert run(42) == run(42)
    assert run(42) != run(7)


def test_existing_requests_use_player_default_region():
    gen = BradleyTerryGenerator(player_count=2, seed=1)
    database = {
        "player_0000": Player(0, "player_0000", Region.ASIA),
        "player_0001": Player(1, "player_0001", Region.EU),
    }
    gen.generate_requests(2, {})  # exhaust the new-player pool -> CASE TWO
    requests = gen.generate_requests(4, database)

    assert len(requests) == 4
    for req in requests:
        assert req["user"] in database
        assert req["req_features"][REGION_KEY] == database[req["user"]].default_region


def test_generate_requests_full_database_with_no_idle_players_returns_empty():
    gen = BradleyTerryGenerator(player_count=2, seed=1)
    database = {
        "player_0000": Player(
            0, "player_0000", Region.OCEANIA, status=PlayerStatus.PLAYING
        ),
        "player_0001": Player(
            1, "player_0001", Region.OCEANIA, status=PlayerStatus.PLAYING
        ),
    }
    gen.generate_requests(2, {})

    assert gen.generate_requests(3, database) == []


def test_generate_requests_signs_up_new_players_when_existing_pool_is_busy():
    gen = BradleyTerryGenerator(player_count=10, seed=42)
    database = _seed_database(gen, 4)
    for player in database.values():
        player.status = PlayerStatus.PLAYING

    requests = gen.generate_requests(5, database)

    assert len(requests) == 5
    assert all(req["user"] not in database for req in requests)


# ---------- _gen_existing_player_request ----------


def test_gen_existing_player_request_uses_default_region():
    rng = random.Random(1)
    database = {"player_0000": Player(0, "player_0000", Region.ASIA)}

    request = _gen_existing_player_request(1, ["player_0000"], rng, database)

    assert request is not None
    assert request["user"] == "player_0000"
    assert request["req_features"][REGION_KEY] == Region.ASIA


def test_gen_existing_player_request_returns_none_when_no_idle_player():
    rng = random.Random(1)
    database = {
        "player_0000": Player(
            0, "player_0000", Region.OCEANIA, status=PlayerStatus.PLAYING
        )
    }

    assert _gen_existing_player_request(1, ["player_0000"], rng, database) is None


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

    strategy = platform.strategy
    assert isinstance(strategy, BradleyTerry)
    assert strategy._candidate_generation_method == BTCandidateGenerationMethod.NAIVE