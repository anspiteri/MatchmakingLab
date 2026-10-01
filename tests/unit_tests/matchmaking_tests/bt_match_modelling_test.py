"""
bt_match_modelling_test.py
~~~~~~~~~~~~~~~~~~~~

This module tests the BradleyTerry matchmaking functions concerned with
calculating the match cost of a pair of players.
"""

import pytest

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
    MatchRequest,
    Region,
)
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    MatchFeatures,
    _bt_probability,
    _competitiveness_score,
    _extract_match_features,
    _latency_cost,
    _match_cost_function,
    _model_match,
    _queue_time_benefit,
    _region_difference,
)
from tests.helpers import make_skill_player

# ---------- Composition Correctness -------------


def test_model_match_composition(mocker):
    player_a = make_skill_player(0, "test_user_a", Region.OCEANIA, BASE_SKILL_RATING)

    player_b = make_skill_player(
        1,
        "test_user_b",
        Region.ASIA,
        BASE_SKILL_RATING + int(BASE_SKILL_RATING / 2),
    )

    request_a = MatchRequest(
        player_a,
        {
            LATENCY_KEY: 50,
            REGION_KEY: Region.OCEANIA,
        },
    )

    request_b = MatchRequest(
        player_b,
        {
            LATENCY_KEY: 100,
            REGION_KEY: Region.ASIA,
        },
    )

    request_a.tick_wait_time = 10
    request_b.tick_wait_time = 20

    bt_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._bt_probability",
        return_value=75,
    )

    competitiveness_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._competitiveness_score",
        return_value=25,
    )

    latency_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._latency_cost",
        return_value=13,
    )

    region_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._region_difference",
        return_value=5,
    )

    queue_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._queue_time_benefit",
        return_value=10,
    )

    cost_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._match_cost_function",
        return_value=33,
    )

    result = _model_match(request_a, request_b)

    bt_mock.assert_called_once_with(100, 150)

    competitiveness_mock.assert_called_once_with(75)

    latency_mock.assert_called_once_with(50, 100)

    region_mock.assert_called_once_with(
        Region.OCEANIA,
        Region.ASIA,
    )

    queue_mock.assert_called_once_with(10, 20)

    cost_mock.assert_called_once_with(
        25,
        13,
        5,
        10,
    )

    assert result.request_A == request_a
    assert result.request_B == request_b
    assert result.match_cost == 33


@pytest.mark.parametrize(
    "competitiveness, latency_cost, region_difference, queue_time_benefit, expected",
    [
        # base case
        (25, 13, 0, 10, 28),
        # no queue-time benefit
        (25, 13, 0, 0, 38),
        # region difference
        (25, 13, 50, 0, 88),
        # all components contribute
        (100, 20, 50, 15, 155),
    ],
)
def test_match_cost_function(
    competitiveness,
    latency_cost,
    region_difference,
    queue_time_benefit,
    expected,
):
    assert (
        _match_cost_function(
            competitiveness,
            latency_cost,
            region_difference,
            queue_time_benefit,
        )
        == expected
    )


# ---------- Extraction / Validation Correctness -------------


@pytest.mark.parametrize(
    "skill_rating_a, skill_rating_b, latency_a, latency_b, "
    "region_a, region_b, queue_time_a, queue_time_b",
    [
        (1000, 1000, 20, 20, Region.OCEANIA, Region.OCEANIA, 0, 0),
        (1000, 1200, 20, 20, Region.OCEANIA, Region.OCEANIA, 0, 0),
        (1000, 1000, 20, 100, Region.OCEANIA, Region.OCEANIA, 0, 0),
        (1000, 1000, 20, 20, Region.OCEANIA, Region.NA, 0, 0),
    ],
)
def test_model_match(
    skill_rating_a,
    skill_rating_b,
    latency_a,
    latency_b,
    region_a,
    region_b,
    queue_time_a,
    queue_time_b,
):
    player_a = make_skill_player(0, "test_user_a", region_a, skill_rating_a)

    player_b = make_skill_player(1, "test_user_b", region_b, skill_rating_b)

    request_a = MatchRequest(
        player_a,
        {
            LATENCY_KEY: latency_a,
            REGION_KEY: region_a,
        },
    )

    request_b = MatchRequest(
        player_b,
        {
            LATENCY_KEY: latency_b,
            REGION_KEY: region_b,
        },
    )

    request_a.tick_wait_time = queue_time_a
    request_b.tick_wait_time = queue_time_b

    result = _model_match(request_a, request_b)

    assert result.request_A == request_a
    assert result.request_B == request_b
    assert isinstance(result.match_cost, int)


@pytest.mark.parametrize(
    "skill_rating, latency, region, queue_time, expected",
    [
        # base case
        (
            BASE_SKILL_RATING,
            50,
            Region.OCEANIA,
            10,
            MatchFeatures(
                skill_rating=BASE_SKILL_RATING,
                latency=50,
                region=Region.OCEANIA,
                queue_time=10,
            ),
        ),
        # latency defaults to zero
        (
            BASE_SKILL_RATING,
            None,
            Region.OCEANIA,
            10,
            MatchFeatures(
                skill_rating=BASE_SKILL_RATING,
                latency=0,
                region=Region.OCEANIA,
                queue_time=10,
            ),
        ),
        # a rating the update rule has already moved off the base
        (
            123.456,
            50,
            Region.OCEANIA,
            10,
            MatchFeatures(
                skill_rating=123.456,
                latency=50,
                region=Region.OCEANIA,
                queue_time=10,
            ),
        ),
    ],
)
def test_extract_match_features(
    skill_rating,
    latency,
    region,
    queue_time,
    expected,
):
    player = make_skill_player(0, "test_user", region, skill_rating)

    request_features = {
        LATENCY_KEY: latency,
        REGION_KEY: region,
    }

    request = MatchRequest(player, request_features)
    request.tick_wait_time = queue_time

    assert _extract_match_features(request) == expected


@pytest.mark.parametrize(
    "skill_rating",
    [None, -1, 0, 1.0e-9, "100"],
)
def test_extract_match_features_invalid_skill(skill_rating):
    # 1.0 is no longer invalid: ratings are floats, since a relative step small
    # enough to be well behaved rounds away against an integer rating.
    player = make_skill_player(0, "test_user", Region.OCEANIA, skill_rating)

    request = MatchRequest(
        player,
        {
            LATENCY_KEY: 10,
            REGION_KEY: Region.OCEANIA,
        },
    )

    with pytest.raises(ValueError):
        _extract_match_features(request)


def test_extract_match_features_rejects_a_bool_rating():
    """bool is an int subclass, so True would otherwise pass as a rating of 1."""
    player = make_skill_player(0, "test_user", Region.OCEANIA, True)

    request = MatchRequest(player, {LATENCY_KEY: 10, REGION_KEY: Region.OCEANIA})

    with pytest.raises(ValueError):
        _extract_match_features(request)


@pytest.mark.parametrize(
    "latency",
    [-1, -100, 1.5, -99.1],
)
def test_extract_match_features_invalid_latency(latency):
    player = make_skill_player(0, "test_user", Region.OCEANIA, BASE_SKILL_RATING)

    request = MatchRequest(
        player,
        {
            LATENCY_KEY: latency,
            REGION_KEY: Region.OCEANIA,
        },
    )

    with pytest.raises(ValueError):
        _extract_match_features(request)


@pytest.mark.parametrize(
    "region",
    [None, Region.UNDEFINED],
)
def test_extract_match_features_invalid_region(region):
    # A valid skill is used deliberately: an invalid one would trip the earlier
    # skill check and mask the region validation this test is meant to cover.
    player = make_skill_player(0, "test_user", Region.OCEANIA, BASE_SKILL_RATING)

    request = MatchRequest(
        player,
        {
            LATENCY_KEY: 0,
            REGION_KEY: region,
        },
    )

    with pytest.raises(ValueError, match="Region is missing"):
        _extract_match_features(request)


# ---------- Calculation Correctness -------------


def test_probability():
    equal_skill_case = _bt_probability(BASE_SKILL_RATING, BASE_SKILL_RATING)
    assert isinstance(equal_skill_case, int)
    assert equal_skill_case >= 0
    assert equal_skill_case <= 100
    assert equal_skill_case == 50

    first_bias_case = _bt_probability(BASE_SKILL_RATING * 2, BASE_SKILL_RATING)
    assert isinstance(first_bias_case, int)
    assert first_bias_case >= 0
    assert first_bias_case <= 100
    assert first_bias_case == 67

    second_bias_case = _bt_probability(BASE_SKILL_RATING, BASE_SKILL_RATING * 2)
    assert isinstance(second_bias_case, int)
    assert second_bias_case >= 0
    assert second_bias_case <= 100
    assert second_bias_case == 33

    # edge case: both have equal zero skill
    equal_zero_case = _bt_probability(0, 0)
    assert isinstance(equal_zero_case, int)
    assert equal_zero_case >= 0
    assert equal_zero_case <= 100
    assert equal_zero_case == 50


def test_competitiveness_score():
    base_case = _competitiveness_score(50)
    assert isinstance(base_case, int)
    assert base_case >= 0
    assert base_case <= 100


def test_latency_cost():
    base_case = _latency_cost(35, 35)
    assert isinstance(base_case, int)
    assert base_case >= 0


def test_region_difference():
    base_case = _region_difference(Region.OCEANIA, Region.OCEANIA)
    assert isinstance(base_case, int)
    assert base_case >= 0


def test_queue_time_benefit():
    base_case = _queue_time_benefit(0, 0)
    assert isinstance(base_case, int)
    assert base_case >= 0
