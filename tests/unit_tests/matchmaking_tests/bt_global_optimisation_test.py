"""
bt_global_optimisation_test.py
~~~~~~~~~~~~~~~~~~~~

This module tests the BradleyTerry matchmaking functions concerned with
optimising pairwise configuration for a given set of queued players.
"""

from unittest.mock import Mock

import pytest

from matchmakinglab.core.models import LATENCY_KEY, REGION_KEY, MatchRequest, Region
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BradleyTerry,
    BTOptimisationMethod,
    MatchModel,
    _greedy_optimisation,
    _queue_matching_function,
)
from tests.helpers import make_player, make_skill_player

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
        make_player(0, "user_0", Region.OCEANIA),
        make_player(1, "user_1", Region.OCEANIA),
        make_player(2, "user_2", Region.OCEANIA),
        make_player(3, "user_3", Region.OCEANIA),
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
            match.team_A[0].player.id,
            match.team_B[0].player.id,
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


# ---------- Self-match rejection (regression) ----------


def test_greedy_optimisation_rejects_a_self_pair():
    """Even handed the cheapest possible model, a player never plays itself."""
    player = make_player(0, "user_0", Region.OCEANIA)
    self_pair = MatchModel(MatchRequest(player, {}, 0), MatchRequest(player, {}, 0), 0)

    matches, matched_players = _greedy_optimisation([self_pair])

    assert matches == []
    assert matched_players == []


def test_greedy_optimisation_ignores_self_pair_but_still_matches_others():
    """A self-pair in the batch is dropped without poisoning valid matches."""
    players = [
        make_player(0, "user_0", Region.OCEANIA),
        make_player(1, "user_1", Region.OCEANIA),
    ]
    self_pair = MatchModel(
        MatchRequest(players[0], {}, 0), MatchRequest(players[0], {}, 0), 0
    )
    real_pair = MatchModel(
        MatchRequest(players[0], {}, 0), MatchRequest(players[1], {}, 0), 5
    )

    matches, matched_players = _greedy_optimisation([self_pair, real_pair])

    assert len(matches) == 1
    assert matches[0].team_A[0].player.id == 0
    assert matches[0].team_B[0].player.id == 1
    assert {player.id for player in matched_players} == {0, 1}


def test_greedy_optimisation_never_places_a_player_on_both_teams():
    players = [
        make_player(0, "user_0", Region.OCEANIA),
        make_player(1, "user_1", Region.OCEANIA),
        make_player(2, "user_2", Region.OCEANIA),
    ]
    # Two duplicate requests for player 0, so a self-pair is unavoidable.
    match_models = [
        MatchModel(MatchRequest(p, {}, 0), MatchRequest(p, {}, 0), 0) for p in players
    ] + [
        MatchModel(MatchRequest(players[0], {}, 0), MatchRequest(players[1], {}, 0), 3),
        MatchModel(MatchRequest(players[1], {}, 0), MatchRequest(players[2], {}, 0), 4),
    ]

    matches, _ = _greedy_optimisation(match_models)

    for match in matches:
        team_a = {request.player.id for request in match.team_A}
        team_b = {request.player.id for request in match.team_B}
        assert not team_a & team_b


def test_run_algorithm_does_not_model_a_self_pair(mocker):
    """Candidate generation filters self-pairs before they reach the optimiser."""
    player = make_skill_player(0, "user_0", Region.OCEANIA)
    requests = [
        MatchRequest(player, {REGION_KEY: Region.OCEANIA, LATENCY_KEY: 10}, 0),
        MatchRequest(player, {REGION_KEY: Region.OCEANIA, LATENCY_KEY: 10}, 0),
    ]

    model_match = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._model_match",
        return_value=MatchModel(requests[0], requests[1], 0),
    )
    matching = mocker.patch(
        "matchmakinglab.matchmakers.bradley_terry.strategy._queue_matching_function",
        return_value=([], []),
    )

    BradleyTerry().run_algorithm(requests)

    model_match.assert_not_called()
    matching.assert_called_once_with([], BTOptimisationMethod.GREEDY)
