"""
bt_match_modelling_test.py
~~~~~~~~~~~~~~~~~~~~

This module tests a group of functions from the BradleyTerry matchmaking
strategy. These functions are concerned with calculating the total match
cost of a pair of players.
"""

import pytest

import matchmakinglab.matchmakers.bradley_terry.strategy as bt
from matchmakinglab.models import Region

BASE_RATING = bt.BASE_SKILL_RATING


def model_match_test():
    pass


@pytest.mark.parametrize(
    "competitiveness, latency_cost, region_difference, queue_time_benefit, expected",
    [
        # base case
        (25, 13, 0, 10, "25+13+0-10"),
    ],
)
def test_match_cost_function(
    competitiveness, latency_cost, region_difference, queue_time_benefit, expected
):
    assert bt._match_cost_function(
        competitiveness, latency_cost, region_difference, queue_time_benefit
    ) == eval(expected)


def test_bt_probability():
    equal_skill_case = bt._bt_probability(BASE_RATING, BASE_RATING)
    assert isinstance(equal_skill_case, int)
    assert equal_skill_case >= 0
    assert equal_skill_case <= 100
    assert equal_skill_case == 50

    first_bias_case = bt._bt_probability(BASE_RATING * 2, BASE_RATING)
    assert isinstance(first_bias_case, int)
    assert first_bias_case >= 0
    assert first_bias_case <= 100
    assert first_bias_case == 67

    second_bias_case = bt._bt_probability(BASE_RATING, BASE_RATING * 2)
    assert isinstance(second_bias_case, int)
    assert second_bias_case >= 0
    assert second_bias_case <= 100
    assert second_bias_case == 33

    # edge case: both have equal zero skill
    equal_zero_case = bt._bt_probability(0, 0)
    assert isinstance(equal_zero_case, int)
    assert equal_zero_case >= 0
    assert equal_zero_case <= 100
    assert equal_zero_case == 50


def test_competitiveness_score():
    base_case = bt._competitiveness_score(50)
    assert isinstance(base_case, int)
    assert base_case >= 0
    assert base_case <= 100


def test_latency_cost():
    base_case = bt._latency_cost(35, 35)
    assert isinstance(base_case, int)
    assert base_case >= 0


def test_region_difference():
    base_case = bt._region_difference(Region.OCEANIA, Region.OCEANIA)
    assert isinstance(base_case, int)
    assert base_case >= 0


def test_queue_time_benefit():
    base_case = bt._queue_time_benefit(0, 0)
    assert isinstance(base_case, int)
    assert base_case >= 0
