"""
bt_class_test.py
~~~~~~~~~~~~~~~~~~~~

This module tests the external functions from the BradleyTerry matchmaking
strategy. These functions are concerned with providing an interface for the
strategy within the platform execution environment.
"""

import math
from itertools import combinations
from unittest.mock import Mock

import pytest

from matchmakinglab.core.models import (
    REGION_KEY,
    TRUE_SKILL_KEY,
    ActiveMatch,
    FinishedMatch,
    MatchRequest,
    PlayerStatus,
    Region,
)
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    MIN_SKILL_RATING,
    SKILL_RATING_KEY,
    BradleyTerry,
    BTCandidateGenerationMethod,
    BTOptimisationMethod,
    _model_match,
)
from tests.helpers import make_skill_player


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


@pytest.mark.parametrize(
    "candidate_generation_method, optimisation_method",
    [
        (BTCandidateGenerationMethod.NAIVE, BTOptimisationMethod.GREEDY),
        (BTCandidateGenerationMethod.NEAREST_NEIGHBOUR, BTOptimisationMethod.GREEDY),
        (BTCandidateGenerationMethod.UNDEFINED, BTOptimisationMethod.UNDEFINED),
    ],
)
def test_setup_player_features(candidate_generation_method, optimisation_method):
    bt_instance = BradleyTerry(candidate_generation_method, optimisation_method)

    result = bt_instance.setup_player_features()

    assert isinstance(result, dict)
    assert SKILL_RATING_KEY in result
    assert result[SKILL_RATING_KEY] == BASE_SKILL_RATING


@pytest.mark.parametrize(
    "winner_skill, loser_skill, expected_winner_after, expected_loser_after",
    [
        # Equal skill - 50/50 probability, so a 1% step either way
        (100, 100, 101.005, 99.005),
        # Winner stronger - probability 0.6, so a 0.8% step
        (150, 100, 151.205, 99.203),
        # Underdog wins - probability 0.4, so a 1.2% step
        (100, 150, 101.207, 148.211),
        # The step is proportional, so a tenth of the rating moves a tenth as
        # far: the same 1% that takes 100 to 101 takes 10 to 10.1. An additive
        # step would have moved this pair by a full point, or not at all.
        (10, 10, 10.101, 9.900),
        # Floor at MIN_SKILL_RATING - a pair already at the bottom of the scale
        # would otherwise cross it. Only reachable at the very bottom: at
        # LEARNING_RATE 0.02 the largest step is 2%, so nothing above a rating
        # of ~1.02 can reach the floor in one update.
        (1, 1, 1.010, MIN_SKILL_RATING),
    ],
)
def test_update_player_features(
    winner_skill, loser_skill, expected_winner_after, expected_loser_after
):
    bt_instance = BradleyTerry()

    winner = make_skill_player(0, "winner", Region.OCEANIA, winner_skill)
    loser = make_skill_player(1, "loser", Region.OCEANIA, loser_skill)

    match = FinishedMatch(match_length=0, winning_team=[winner], losing_team=[loser])

    bt_instance.update_player_features(match)

    assert winner.player_features[SKILL_RATING_KEY] == pytest.approx(
        expected_winner_after, abs=0.001
    )
    assert loser.player_features[SKILL_RATING_KEY] == pytest.approx(
        expected_loser_after, abs=0.001
    )


def test_update_player_features_conserves_the_product_of_the_two_ratings():
    """The step is multiplicative, so the pair's product is left alone.

    This is the invariant the log-space rule exists to provide: the scale cannot
    inflate because there is nothing to inflate. An additive step conserves the
    *sum* instead, which only looks similar until the ratings separate.
    """
    bt_instance = BradleyTerry()

    winner = make_skill_player(0, "winner", Region.OCEANIA, 137.5)
    loser = make_skill_player(1, "loser", Region.OCEANIA, 64.25)

    before = 137.5 * 64.25

    bt_instance.update_player_features(
        FinishedMatch(match_length=0, winning_team=[winner], losing_team=[loser])
    )

    after = (
        winner.player_features[SKILL_RATING_KEY]
        * loser.player_features[SKILL_RATING_KEY]
    )

    assert after == pytest.approx(before, rel=1e-12)


def test_update_player_features_does_not_touch_win_loss_record():
    """Rating updates are independent of the win/loss bookkeeping."""
    bt_instance = BradleyTerry()

    winner = make_skill_player(
        0, "winner", Region.OCEANIA, 100, PlayerStatus.IDLE, wins=3, loses=1
    )
    loser = make_skill_player(
        1, "loser", Region.OCEANIA, 100, PlayerStatus.IDLE, wins=2, loses=5
    )

    match = FinishedMatch(match_length=0, winning_team=[winner], losing_team=[loser])
    bt_instance.update_player_features(match)

    assert (winner.wins, winner.loses) == (3, 1)
    assert (loser.wins, loser.loses) == (2, 5)


def test_update_player_features_asserts_on_empty_teams():
    bt_instance = BradleyTerry()

    winner = make_skill_player(0, "winner", Region.OCEANIA, 100)
    loser = make_skill_player(1, "loser", Region.OCEANIA, 100)

    with pytest.raises(AssertionError):
        bt_instance.update_player_features(
            FinishedMatch(match_length=0, winning_team=[], losing_team=[loser])
        )

    with pytest.raises(AssertionError):
        bt_instance.update_player_features(
            FinishedMatch(match_length=0, winning_team=[winner], losing_team=[])
        )


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
                MatchRequest(
                    make_skill_player(0, "Alice", Region.OCEANIA, BASE_SKILL_RATING)
                ),
                MatchRequest(
                    make_skill_player(1, "Bob", Region.OCEANIA, BASE_SKILL_RATING)
                ),
            ],
            [0, 1],
            [],
        ),
        (
            [
                MatchRequest(
                    make_skill_player(0, "Alice", Region.OCEANIA, BASE_SKILL_RATING)
                ),
                MatchRequest(
                    make_skill_player(1, "Bob", Region.OCEANIA, BASE_SKILL_RATING + 10)
                ),
                MatchRequest(
                    make_skill_player(
                        2, "Charlie", Region.OCEANIA, BASE_SKILL_RATING + 20
                    )
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

    players_matched = [queue_snapshot[index].player for index in matched_indices]

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


def test_run_algorithm_returns_empty_queue_untouched():
    """An empty queue short-circuits before candidate generation."""
    bt_instance = BradleyTerry()

    matches, remaining = bt_instance.run_algorithm([])

    assert matches == []
    assert remaining == []


def test_run_algorithm_raises_for_undefined_candidate_generation_method():
    request = MatchRequest(
        make_skill_player(0, "Alice", Region.OCEANIA, BASE_SKILL_RATING),
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


# ---------- Does the simulation actually produce learnable signal? ----------
#
# The rating update is only worth having if it converges on something. With the
# hidden skill seeded at creation and match outcomes drawn from it, that
# something is measurable: a matchmaker's estimate should come to track a
# player's real ability. These are the "intuition tests" the project diary
# asks for — they check the property the whole lab rests on, rather than the
# arithmetic of any one function.


def _harness(ticks: int, seed: int = 1):
    """Run a real simulation headlessly and hand back the harness."""
    from matchmakinglab.matchmakers.bradley_terry import generator as gen
    from matchmakinglab.platform.platform import Platform
    from matchmakinglab.platform.sim_harness import SimHarness

    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=150, seed=seed),
        Platform(BradleyTerry()),
        requests_per_step=10,
        seed=seed,
    )
    for _ in range(ticks):
        harness.step()
    return harness


def _played_players(harness) -> list:
    """Only players with a match record — the rest have ratings worth nothing."""
    played = [p for p in harness.state.player_database.values() if p.wins + p.loses > 0]
    assert len(played) > 20, "the run produced too few played players to judge"
    return played


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    spread_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    spread_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if spread_x == 0 or spread_y == 0:
        return 0.0
    return covariance / (spread_x * spread_y)


def _rating_accuracy(harness) -> float:
    """Correlation between what the strategy estimates and what is actually true."""
    played = _played_players(harness)
    return _pearson(
        [float(p.player_features[SKILL_RATING_KEY]) for p in played],
        [float(p.player_features[TRUE_SKILL_KEY]) for p in played],
    )


def test_ratings_learn_to_track_hidden_skill():
    """The core intuition: estimates converge on the truth they never see.

    This is the check that the simulator is doing its job. Outcomes are decided
    from `true_skill` while the strategy only ever reads its own `skill_rating`,
    so correlation between the two can only appear if the rating update is
    genuinely learning. A flat or negative result means results are not carrying
    usable signal, and every downstream metric would be noise.
    """
    assert _rating_accuracy(_harness(600)) > 0.7


def test_rating_learning_is_reproducible_under_a_seed():
    """Same seed, same learning outcome — a diagnostic you cannot repeat is no use."""
    assert _rating_accuracy(_harness(600, seed=1)) == _rating_accuracy(
        _harness(600, seed=1)
    )


# ---------- Rating scale calibration ----------
#
# The update is a constant step on log(rating), so it moves a rating by a fixed
# *ratio* and leaves the product of a matched pair alone. Two things are worth
# pinning: the scale must not inflate, and the rule's own invariant must hold.


def _dispersion(harness) -> float:
    played = _played_players(harness)

    estimated = [p.player_features[SKILL_RATING_KEY] for p in played]
    true = [p.player_features[TRUE_SKILL_KEY] for p in played]

    return (max(estimated) - min(estimated)) / (max(true) - min(true))


def test_rating_update_keeps_the_population_geometric_mean_at_the_base():
    """The scale is anchored: every update is a ratio, so nothing inflates.

    The old additive rule conserved the *sum* of the ratings instead, which held
    only until the spread grew large enough for the floor to start clamping. This
    is the structural form of the fix, so it is worth asserting directly rather
    than inferring from the spread. The floor would break it if it ever bound -
    at this rate it does not, the lowest rating seen over 2000 ticks is ~47.
    """
    played = _played_players(_harness(2000, seed=1))

    ratings = [p.player_features[SKILL_RATING_KEY] for p in played]
    geometric_mean = math.exp(sum(math.log(r) for r in ratings) / len(ratings))

    assert geometric_mean == pytest.approx(BASE_SKILL_RATING, rel=1e-9)


# The bound below is deliberately loose. Its job is to be a smoke alarm that
# fires if the inflation comes back - a swapped update rule, a much larger
# learning rate, a change of rating scale - not to pin the current numbers, which
# would make the test brittle and get deleted the first time a legitimate change
# moved them.
#
# Measured ratio of estimated spread to true spread, seed 1, 150 players, at
# 2000 ticks, against the log-space update at several rates:
#
#     LEARNING_RATE   0.01   0.02   0.05
#     dispersion      1.03   1.03   1.71
#
# The bound sits just under the 1.52x the replaced additive rule measured at the
# same seed and tick count, so reinstating that rule trips it. Over five seeds
# the current rate measures 0.98-1.12, so there is real headroom above it.
#
# 2000 ticks rather than 600 because the drift is not yet visible at 600: every
# rate in the table reads under 1.05 there, which would make the test blind to
# the thing it exists to catch.

MAX_RATING_SPREAD_RATIO = 1.5


def test_estimated_spread_stays_within_a_loose_bound_of_true_spread():
    ratio = _dispersion(_harness(2000, seed=1))

    assert ratio < MAX_RATING_SPREAD_RATIO, (
        f"Estimated rating spread is {ratio:.2f}x the true spread. Inflation has "
        f"grown past what the log-space update is known to do - see "
        f"docs/matchmaking-implementations.md."
    )
