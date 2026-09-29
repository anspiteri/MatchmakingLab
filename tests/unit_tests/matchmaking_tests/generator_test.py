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
    PlayerStatus,
    Region,
)
from matchmakinglab.matchmakers import BTCandidateGenerationMethod
from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry.generator import (
    MAX_TRIES,
    BradleyTerryGenerator,
    _gen_existing_player_request,
    _gen_n_existing_requests,
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

    requests = gen.generate_requests(3, {})
    database = {
        req["user"]: make_skill_player(i, req["user"], Region.OCEANIA)
        for i, req in enumerate(requests)
    }

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
    # Asking for 4 only yields 2: the batch is capped by the number of distinct
    # idle players available, since a player may hold only one request.
    requests = gen.generate_requests(4, database)

    assert len(requests) == len(database)
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
    """With no idle player to pull back, the whole batch becomes new signups.

    Seed 0 draws the existing-player branch on the first pick, so this also
    covers the fallback loop that tops the batch up with fresh signups once the
    pool lookup has come up empty.
    """
    gen = BradleyTerryGenerator(player_count=10, seed=0)
    database = _seed_database(gen, 4)
    for player in database.values():
        player.status = PlayerStatus.PLAYING

    requests = gen.generate_requests(5, database)

    assert len(requests) == 5
    assert all(req["user"] not in database for req in requests)
    assert all(req["is_new"] for req in requests)
    # The batch is topped up from the next available pool slots.
    assert [req["user"] for req in requests] == [f"player_{i:04d}" for i in range(4, 9)]


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
    assert request["is_new"] is False


def test_gen_existing_player_request_returns_none_when_no_idle_player():
    rng = random.Random(1)
    database = {
        "player_0000": make_skill_player(
            0, "player_0000", Region.OCEANIA, status=PlayerStatus.PLAYING
        )
    }

    assert _gen_existing_player_request(1, ["player_0000"], rng, database) is None


def test_gen_existing_player_request_returns_none_for_unknown_username():
    rng = random.Random(1)
    database = {}

    assert _gen_existing_player_request(1, ["player_0000"], rng, database) is None


def test_gen_existing_player_request_gives_up_after_max_tries(mocker):
    rng = random.Random(1)
    database = {
        "player_0000": make_skill_player(
            0, "player_0000", Region.OCEANIA, status=PlayerStatus.QUEUING
        )
    }
    pick = mocker.patch.object(rng, "randint", return_value=0)

    assert _gen_existing_player_request(1, ["player_0000"], rng, database) is None
    assert pick.call_count == MAX_TRIES


# ---------- Distinct users per batch (self-match regression) ----------


@pytest.mark.parametrize("seed", range(10))
def test_gen_existing_player_request_skips_excluded_users(seed):
    pool = ["player_0000", "player_0001"]
    database = {
        name: make_skill_player(i, name, Region.OCEANIA) for i, name in enumerate(pool)
    }

    request = _gen_existing_player_request(
        len(pool),
        pool,
        random.Random(seed),
        database,
        exclude={"player_0000"},
    )

    assert request is not None
    assert request["user"] == "player_0001"


def test_gen_existing_player_request_retries_past_an_excluded_user(mocker):
    """An excluded draw is a miss, not a reason to give up immediately."""
    pool = ["player_0000", "player_0001"]
    database = {
        name: make_skill_player(i, name, Region.OCEANIA) for i, name in enumerate(pool)
    }
    rng = random.Random(0)
    # randint serves both the pool draw (randint(0, index - 1)) and the latency
    # draw (randint(5, 120)); they are told apart by the low bound.
    pool_picks = iter([0, 1])

    def pick(lo, hi):
        return next(pool_picks) if lo == 0 else 50

    pick_mock = mocker.patch.object(rng, "randint", side_effect=pick)

    request = _gen_existing_player_request(
        len(pool), pool, rng, database, exclude={"player_0000"}
    )

    assert request is not None
    assert request["user"] == "player_0001"
    assert pick_mock.call_count > 1  # it actually retried


def test_gen_existing_player_request_returns_none_when_all_users_excluded(mocker):
    rng = random.Random(1)
    database = {"player_0000": make_skill_player(0, "player_0000", Region.OCEANIA)}
    mocker.patch.object(rng, "randint", return_value=0)

    request = _gen_existing_player_request(
        1, ["player_0000"], rng, database, exclude={"player_0000"}
    )

    assert request is None


def test_gen_n_existing_requests_never_repeats_a_user():
    pool = [f"player_{i:04d}" for i in range(8)]
    database = {
        name: make_skill_player(i, name, Region.OCEANIA) for i, name in enumerate(pool)
    }

    requests = _gen_n_existing_requests(6, len(pool), pool, random.Random(3), database)

    users = [req["user"] for req in requests]
    assert len(users) == 6
    assert len(set(users)) == 6


def test_gen_n_existing_requests_stops_when_distinct_pool_exhausted():
    """Asking for more than exist returns what is available, not duplicates."""
    pool = ["player_0000", "player_0001"]
    database = {
        name: make_skill_player(i, name, Region.OCEANIA) for i, name in enumerate(pool)
    }

    requests = _gen_n_existing_requests(5, len(pool), pool, random.Random(1), database)

    users = [req["user"] for req in requests]
    assert sorted(users) == sorted(pool)


def test_gen_n_existing_requests_honours_preexisting_exclusions():
    pool = ["player_0000", "player_0001", "player_0002"]
    database = {
        name: make_skill_player(i, name, Region.OCEANIA) for i, name in enumerate(pool)
    }

    requests = _gen_n_existing_requests(
        2, len(pool), pool, random.Random(5), database, exclude={"player_0000"}
    )

    users = [req["user"] for req in requests]
    assert "player_0000" not in users
    assert len(users) == 2
    assert len(set(users)) == 2


@pytest.mark.parametrize("seed", range(12))
def test_generate_requests_never_names_a_player_twice(seed):
    """Every batch, in every mode, yields distinct users."""
    generator = BradleyTerryGenerator(player_count=8, seed=seed)
    database = {
        req["user"]: make_skill_player(
            i, req["user"], Region.OCEANIA, status=PlayerStatus.IDLE
        )
        for i, req in enumerate(generator.generate_requests(4, {}))
    }

    # Mixed mode, then existing-only mode, then a re-seeded mixed mode.
    for requests in (
        generator.generate_requests(6, database),
        generator.generate_requests(6, database),
    ):
        users = [req["user"] for req in requests]
        assert len(users) == len(set(users)), f"duplicate user in batch for seed {seed}"


def test_generate_requests_mixed_mode_skips_names_already_used():
    """A new signup and a pulled-back player cannot collide within one batch."""
    generator = BradleyTerryGenerator(player_count=4, seed=2)
    database = {
        req["user"]: make_skill_player(
            i, req["user"], Region.OCEANIA, status=PlayerStatus.IDLE
        )
        for i, req in enumerate(generator.generate_requests(2, {}))
    }

    for _ in range(20):
        users = [req["user"] for req in generator.generate_requests(4, database)]
        assert len(users) == len(set(users))


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


def test_factory_treats_empty_config_as_defaults():
    platform = BradleyTerryFactory({}).create_platform()

    strategy = platform.strategy
    assert isinstance(strategy, BradleyTerry)
    assert strategy._candidate_generation_method == BTCandidateGenerationMethod.NAIVE
    assert strategy._optimisation_method.name == "GREEDY"
