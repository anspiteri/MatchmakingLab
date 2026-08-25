"""
bt_global_optimisation_test.py
~~~~~~~~~~~~~~~~~~~~

This module tests the BradleyTerry matchmaking functions concerned with
optimising pairwise configuration for a given set of queued players.
"""

import pytest

from unittest.mock import Mock
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    _queue_matching_function,
    _greedy_optimisation,
    BTOptimisationMethod,
    MatchModel,
)
from matchmakinglab.models import Player, MatchRequest

# ---------- Composition Correctness -------------


@pytest.mark.parametrize(
    "method", [BTOptimisationMethod.GREEDY, BTOptimisationMethod.UNDEFINED]
)
def test_queue_matching_composition(mocker, method):
    model_fake_1 = MatchModel(Mock(), Mock(), 0)
    model_fake_2 = MatchModel(Mock(), Mock(), 0)
    model_fake_3 = MatchModel(Mock(), Mock(), 0)
    model_fake_4 = MatchModel(Mock(), Mock(), 0)
    model_fake_5 = MatchModel(Mock(), Mock(), 0)
    model_fake_6 = MatchModel(Mock(), Mock(), 0)

    match_models = [
        model_fake_1,
        model_fake_2,
        model_fake_3,
        model_fake_4,
        model_fake_5,
        model_fake_6,
    ]

    greedy_mock = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._greedy_optimisation",
        return_value=([], []),
    )

    match method:
        case BTOptimisationMethod.UNDEFINED:
            with pytest.raises(ValueError):
                matches, players_matched = _queue_matching_function(
                    match_models, method
                )
                greedy_mock.assert_not_called()
                assert matches == []
                assert players_matched == []

        case BTOptimisationMethod.GREEDY:
            matches, players_matched = _queue_matching_function(match_models, method)
            greedy_mock.assert_called_once_with(match_models)
            assert matches == []
            assert players_matched == []

        case _:
            assert False


# ---------- Optimisation Correctness -------------


@pytest.mark.parametrize(
    "model_data, expected_pairs, expected_cost",
    [
        # Two independent cheapest matches.
        (
            [
                (0, 1, 0),  # (id, id, match_cost)
                (2, 3, 1),
                (0, 2, 5),
                (1, 3, 10),
            ],
            {(0, 1), (2, 3)},  # expected_pairs
            1,
        ),
        # The cheapest match prevents another player from being matched
        # with their next-best option.
        (
            [
                (0, 1, 0),
                (1, 2, 5),
                (0, 2, 10),
                (2, 3, 10),
            ],
            {(0, 1), (2, 3)},
            10,
        ),
        # Odd number of players: one player is left unmatched.
        (
            [
                (0, 1, 0),
                (1, 2, 5),
            ],
            {(0, 1)},
            0,
        ),
        # Only one viable match.
        (
            [
                (0, 1, 10),
            ],
            {(0, 1)},
            10,
        ),
        # Greedy is NOT globally optimal.
        (
            [
                (0, 1, 1),
                (0, 2, 2),
                (1, 3, 2),
                (2, 3, 100),
            ],
            {(0, 1), (2, 3)},
            101,
        ),
    ],
)
def test_greedy_optimisation(model_data, expected_pairs, expected_cost):
    players = [
        Player(0, "user_0", {}),
        Player(1, "user_1", {}),
        Player(2, "user_2", {}),
        Player(3, "user_3", {}),
    ]

    match_models = [
        MatchModel(
            MatchRequest(players[player_a], {}, 0),
            MatchRequest(players[player_b], {}, 0),
            cost,
        )
        for player_a, player_b, cost in model_data
    ]

    matches, matched_players = _greedy_optimisation(match_models)

    actual_pairs = {
        (
            match.team_A[0].id,
            match.team_B[0].id,
        )
        for match in matches
    }

    actual_matched_players = {player.id for player in matched_players}

    expected_players = {player_id for pair in expected_pairs for player_id in pair}

    actual_cost = sum(match.match_cost for match in matches)

    assert actual_pairs == expected_pairs
    assert actual_matched_players == expected_players
    assert len(matched_players) == len(actual_matched_players)
    assert actual_cost == expected_cost
