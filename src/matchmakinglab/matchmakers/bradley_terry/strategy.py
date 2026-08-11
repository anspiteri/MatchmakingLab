from itertools import combinations
from typing import Any, Optional
from matchmakinglab.matchmakers import MatchmakingStrategy
from matchmakinglab.models import (
    ActiveMatch,
    FinishedMatch,
    MatchRequest,
    Region,
)

# Keys -- maybe split these up between general and bt specific
SKILL_RATING_KEY = "skill_rating"
LATENCY_KEY = "latency"
REGION_KEY = "region"

# Weights
BASE_SKILL_RATING = 100

TARGET_PROBABILITY = 50  # optimises for competitiveness i.e. 50/50 skill
TARGET_THRESHOLD = 10
THRESHOLD_INCREMENT = 10

LATENCY_SCALAR = 1

SAME_REGION = 0
DIFFERENT_REGION = 50

QUEUE_BENEFIT_SCALAR = 1


def _bt_probability(i: int, j: int) -> int:
    result = i / (i + j)
    return int(round(result * 100))


def _competitiveness_score(bt_probability):
    return abs(bt_probability - TARGET_PROBABILITY)


def _latency_cost(i: Optional[int], j: Optional[int]):
    if i is None or j is None:
        return 0

    return abs(i - j) * LATENCY_SCALAR


def _region_difference(i: Region, j: Region):
    return SAME_REGION if i == j else DIFFERENT_REGION


def _queue_time_benefit(queue_time_A: int, queue_time_B: int):
    return (queue_time_A + queue_time_B) * QUEUE_BENEFIT_SCALAR


def _match_cost_function(
    competitiveness, latency_cost, region_difference, queue_time_benefit
) -> int:
    return competitiveness + latency_cost + region_difference - queue_time_benefit


def _model_match(player_A: MatchRequest, player_B: MatchRequest):

    skill_rating_A: Optional[int]
    skill_rating_B: Optional[int]

    skill_rating_A, skill_rating_B = (
        player_A.player.player_features.get(SKILL_RATING_KEY),
        player_B.player.player_features.get(SKILL_RATING_KEY),
    )

    # skill rating a is required feature
    if skill_rating_A is None or skill_rating_B is None:
        raise ValueError("A player skill is None")

    latency_A: Optional[int]
    latency_B: Optional[int]

    latency_A, latency_B = (
        player_A.req_features.get(LATENCY_KEY),
        player_A.req_features.get(LATENCY_KEY),
    )

    region_A: Optional[Region]
    region_B: Optional[Region]

    region_A, region_B = (
        player_A.req_features.get(REGION_KEY),
        player_B.req_features.get(REGION_KEY),
    )

    if region_A is None or region_B is None:
        raise ValueError("Region is missing")

    queue_time_A: Optional[int]
    queue_time_B: Optional[int]

    queue_time_A, queue_time_B = (player_A.tick_wait_time, player_B.tick_wait_time)

    return _match_cost_function(
        _competitiveness_score(_bt_probability(skill_rating_A, skill_rating_B)),
        _latency_cost(latency_A, latency_B),
        _region_difference(region_A, region_B),
        _queue_time_benefit(queue_time_A, queue_time_B),
    )


class BradleyTerry(MatchmakingStrategy):
    def __init__(self):
        pass

    def run_algorithm(
        self, queue_snapshot: list[MatchRequest]
    ) -> tuple[list[ActiveMatch], list[MatchRequest]]:

        if len(queue_snapshot) == 0:
            return ([], queue_snapshot)

        possible_matches = [
            _model_match(A, B) for A, B in combinations(queue_snapshot, 2)
        ]

        if possible_matches is None:
            raise TypeError("Creating match models failed: None")

        return ([], [])

    def setup_player_features(self) -> dict[str, Any]:
        return {SKILL_RATING_KEY: BASE_SKILL_RATING}

    def update_player_features(self, finished_match: FinishedMatch):
        pass
