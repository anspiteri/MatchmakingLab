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
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    SKILL_RATING_KEY,
    BradleyTerry,
)
from matchmakinglab.matchmakers.factory import (
    BradleyTerryFactory,
    MatchmakerFactory,
)
from matchmakinglab.platform.platform import Platform
from tests.helpers import make_skill_player

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
        database[req["user"]] = make_skill_player(0, req["user"], Region.OCEANIA)

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
    gen: BradleyTerryGenerator,
    count: int,
    region: Region = Region.OCEANIA,
    status: PlayerStatus = PlayerStatus.IDLE,
) -> dict:
    database: dict = {}
    for i, req in enumerate(gen.generate_requests(count, {})):
        database[req["user"]] = make_skill_player(i, req["user"], region, status=status)
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
        "player_0000": make_skill_player(0, "player_0000", Region.ASIA),
        "player_0001": make_skill_player(1, "player_0001", Region.EU),
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
        "player_0000": make_skill_player(
            0, "player_0000", Region.OCEANIA, status=PlayerStatus.PLAYING
        ),
        "player_0001": make_skill_player(
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


def test_generate_requests_stops_early_when_pool_runs_out_mid_fallback():
    """Falling back to new signups stops early once the pool is exhausted.

    A six-player pool with four slots already consumed draws the existing-player
    branch on the third pick, by which point the pool is full. The fallback loop
    cannot top the batch up, so it returns the signups it managed to create
    rather than the number originally requested.
    """
    gen = BradleyTerryGenerator(player_count=6, seed=3)
    database = _seed_database(gen, 4, status=PlayerStatus.PLAYING)
    assert gen._index == 4

    requests = gen.generate_requests(3, database)

    # Only the two remaining pool slots could be filled, and no existing
    # player was idle enough to be pulled back.
    assert [req["user"] for req in requests] == ["player_0004", "player_0005"]
    assert all(req["is_new"] for req in requests)
    assert gen._index == len(gen._pool)


# ---------- is_new flag ----------


def test_new_player_requests_are_flagged_new_and_omit_skill_rating():
    """A signup carries no skill rating — it is assigned when the player is created."""
    gen = BradleyTerryGenerator(player_count=5, seed=1)

    requests = gen.generate_requests(5, {})

    assert requests
    assert all(req["is_new"] is True for req in requests)
    assert all(SKILL_RATING_KEY not in req["req_features"] for req in requests)


def test_existing_player_requests_are_flagged_not_new():
    gen = BradleyTerryGenerator(player_count=2, seed=1)
    database = {
        "player_0000": make_skill_player(0, "player_0000", Region.ASIA),
        "player_0001": make_skill_player(1, "player_0001", Region.EU),
    }
    gen.generate_requests(2, {})  # exhaust the pool -> CASE TWO

    requests = gen.generate_requests(2, database)

    assert requests
    assert all(req["is_new"] is False for req in requests)


def test_is_new_flag_agrees_with_database_membership_in_a_mixed_batch():
    gen = BradleyTerryGenerator(player_count=10, seed=42)
    database = _seed_database(gen, 4)

    requests = gen.generate_requests(10, database)

    for req in requests:
        assert req["is_new"] is (req["user"] not in database)


def test_existing_player_request_carries_the_players_current_skill_rating():
    """A returning player's request reports their live rating, not the base one."""
    gen = BradleyTerryGenerator(player_count=2, seed=1)
    database = {
        "player_0000": make_skill_player(
            0, "player_0000", Region.ASIA, skill_rating=137
        ),
        "player_0001": make_skill_player(1, "player_0001", Region.EU, skill_rating=64),
    }
    gen.generate_requests(2, {})

    requests = gen.generate_requests(4, database)

    assert requests
    for req in requests:
        expected = database[req["user"]].player_features[SKILL_RATING_KEY]
        assert req["req_features"][SKILL_RATING_KEY] == expected
        assert expected != BASE_SKILL_RATING


def test_existing_player_request_tracks_skill_rating_updates():
    """Ratings updated between requests are reflected in the next pullback."""
    player = make_skill_player(0, "player_0000", Region.ASIA, BASE_SKILL_RATING)
    database = {"player_0000": player}
    gen = BradleyTerryGenerator(player_count=1, seed=1)
    gen.generate_requests(1, {})

    request = _gen_existing_player_request(
        1, ["player_0000"], random.Random(0), database
    )
    assert request is not None
    assert request["req_features"][SKILL_RATING_KEY] == BASE_SKILL_RATING

    player.player_features[SKILL_RATING_KEY] = 142

    request = _gen_existing_player_request(
        1, ["player_0000"], random.Random(0), database
    )
    assert request is not None
    assert request["req_features"][SKILL_RATING_KEY] == 142


# ---------- _gen_existing_player_request ----------


def test_gen_existing_player_request_uses_default_region():
    rng = random.Random(1)
    database = {"player_0000": make_skill_player(0, "player_0000", Region.ASIA)}

    request = _gen_existing_player_request(1, ["player_0000"], rng, database)

    assert request is not None
    assert request["user"] == "player_0000"
    assert request["req_features"][REGION_KEY] == Region.ASIA


def test_gen_existing_player_request_returns_none_when_no_idle_player():
    rng = random.Random(1)
    database = {
        "player_0000": make_skill_player(
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
