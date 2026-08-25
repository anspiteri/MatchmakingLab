"""
bt_class_test.py
~~~~~~~~~~~~~~~~~~~~

This module tests the external functions from the BradleyTerry matchmaking
strategy. These functions are concerned with providing an interface for the
strategy within the platform execution environment.
"""

from matchmakinglab.matchmakers.bradley_terry.strategy import _model_match
from itertools import combinations
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    SKILL_RATING_KEY,
)
from unittest.mock import Mock
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BTCandidateGenerationMethod,
    BTOptimisationMethod,
    BradleyTerry,
)
import pytest

from matchmakinglab.models import REGION_KEY, ActiveMatch, MatchRequest, Player, Region


@pytest.mark.parametrize(
    "candidate_generation_method, optimisation_method",
    [
        # Weak Normal Equivalence Testing
        (BTCandidateGenerationMethod.NAIVE, BTOptimisationMethod.GREEDY),
        (BTCandidateGenerationMethod.NEAREST_NEIGHBOUR, BTOptimisationMethod.GREEDY),
        (BTCandidateGenerationMethod.UNDEFINED, BTOptimisationMethod.UNDEFINED),
    ],
)
def test_class_init(candidate_generation_method, optimisation_method):
    bt_instance = BradleyTerry(candidate_generation_method, optimisation_method)
    assert bt_instance._candidate_generation_method == candidate_generation_method
    assert bt_instance._optimisation_method == optimisation_method


def test_setup_player_features():
    pass


def test_update_player_features():
    pass


@pytest.mark.parametrize(
    "queue_snapshot, matched_indices, expected_remaining_indices",
    [
        (
            [],
            [],
            [],
        ),
        (
            [
                MatchRequest(Player(0, "Alice", {SKILL_RATING_KEY: BASE_SKILL_RATING})),
                MatchRequest(Player(1, "Bob", {SKILL_RATING_KEY: BASE_SKILL_RATING})),
            ],
            [0, 1],
            [],
        ),
        (
            [
                MatchRequest(Player(0, "Alice", {SKILL_RATING_KEY: BASE_SKILL_RATING})),
                MatchRequest(
                    Player(1, "Bob", {SKILL_RATING_KEY: BASE_SKILL_RATING + 10})
                ),
                MatchRequest(
                    Player(2, "Charlie", {SKILL_RATING_KEY: BASE_SKILL_RATING + 20})
                ),
            ],
            [0, 1],
            [2],
        ),
    ],
)
def test_run_algorithm_composition(
    mocker,
    queue_snapshot,
    matched_indices,
    expected_remaining_indices,
):
    for req in queue_snapshot:
        req.req_features = {REGION_KEY: Region.OCEANIA}

    players_matched = [queue_snapshot[index] for index in matched_indices]

    matching_result = (
        [ActiveMatch(match_cost=0)] if players_matched else [],
        players_matched,
    )

    queue_matching_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._queue_matching_function",
        return_value=matching_result,
    )

    bt_instance = BradleyTerry(
        BTCandidateGenerationMethod.NAIVE,
        Mock(),
    )

    matches, remaining = bt_instance.run_algorithm(queue_snapshot)

    assert matches == matching_result[0]

    assert {request.player.id for request in remaining} == {
        queue_snapshot[index].player.id for index in expected_remaining_indices
    }

    if not queue_snapshot:
        queue_matching_mock.assert_not_called()
    else:
        expected_models = [
            _model_match(A, B) for A, B in combinations(queue_snapshot, 2)
        ]

        queue_matching_mock.assert_called_once_with(
            expected_models,
            bt_instance._optimisation_method,
        )


def test_run_algorithm_raises_for_undefined_candidate_generation_method():
    request = MatchRequest(
        Player(
            0,
            "Alice",
            {SKILL_RATING_KEY: BASE_SKILL_RATING},
        ),
        {REGION_KEY: Region.OCEANIA},
    )

    bt_instance = BradleyTerry(
        BTCandidateGenerationMethod.UNDEFINED,
        Mock(),
    )

    with pytest.raises(
        ValueError,
        match="No implementation for candidate generation method",
    ):
        bt_instance.run_algorithm([request])
