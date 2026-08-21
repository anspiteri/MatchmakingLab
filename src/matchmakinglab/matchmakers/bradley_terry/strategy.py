from dataclasses import dataclass
from enum import Enum, auto
from itertools import combinations
from typing import Any
from matchmakinglab.matchmakers import MatchmakingStrategy
from matchmakinglab.models import (
    ActiveMatch,
    FinishedMatch,
    MatchRequest,
    Player,
    Region,
)

# --- KEYS --- (maybe split these up between general and bt specific)
SKILL_RATING_KEY = "skill_rating"
LATENCY_KEY = "latency"
REGION_KEY = "region"

# --- WEIGHTS ---
# Assumed to be positive scalars
BASE_SKILL_RATING = 100

TARGET_PROBABILITY = 50  # optimises for competitiveness i.e. 50/50 skill
TARGET_THRESHOLD = 10
THRESHOLD_INCREMENT = 10

LATENCY_SCALAR = 1

SAME_REGION = 0
DIFFERENT_REGION = 50

QUEUE_BENEFIT_SCALAR = 1


# --- ENUMERATORS ---
class BTCandidateGenerationMethod(Enum):
    NAIVE = auto()
    NEAREST_NEIGHBOUR = auto()
    UNDEFINED = auto()


class BTOptimisationMethod(Enum):
    GREEDY = auto()
    UNDEFINED = auto()


# --- HELPER CLASSES ---
@dataclass
class MatchModel:
    request_A: MatchRequest
    request_B: MatchRequest
    match_cost: int


@dataclass
class MatchFeatures:
    skill_rating: int
    latency: int
    region: Region
    queue_time: int


# --- MAIN CLASS IMPLEMENTATION ---
class BradleyTerry(MatchmakingStrategy):
    def __init__(
        self,
        candidate_generation_method=BTCandidateGenerationMethod.NAIVE,
        optimisation_method=BTOptimisationMethod.GREEDY,
    ):
        self._candidate_generation_method = candidate_generation_method
        self._optimisation_method = optimisation_method

    def setup_player_features(self) -> dict[str, Any]:
        return {SKILL_RATING_KEY: BASE_SKILL_RATING}

    def update_player_features(self, finished_match: FinishedMatch):
        pass

    def run_algorithm(
        self, queue_snapshot: list[MatchRequest]
    ) -> tuple[list[ActiveMatch], list[MatchRequest]]:

        if len(queue_snapshot) == 0:
            return ([], queue_snapshot)

        match_models: list[MatchModel] = []

        match self._candidate_generation_method:
            case BTCandidateGenerationMethod.NAIVE:
                match_models = [
                    _model_match(A, B) for A, B in combinations(queue_snapshot, 2)
                ]
            case _:
                pass

        matches, players_matched = _queue_matching_function(
            match_models, self._optimisation_method
        )

        remaining = list(set(queue_snapshot).difference(players_matched))

        return matches, remaining


# --- MAIN ALGORITHMS & HELPER FUNCTIONS ---
def _queue_matching_function(
    match_models: list[MatchModel],
    optimisation_method: BTOptimisationMethod,
) -> tuple[list[ActiveMatch], list[Player]]:
    """
    This can be viewed as the global objective function that:
        - Takes the whole queue and finds the optimum configuration of teams
        - and additionally can be configured with different approaches to this optimisation
    """
    result: tuple[list[ActiveMatch], list[Player]] = ([], [])

    match optimisation_method:
        case BTOptimisationMethod.GREEDY:
            result = _greedy_optimisation(match_models)
        case _:
            pass

    return result


def _greedy_optimisation(
    match_models: list[MatchModel],
) -> tuple[list[ActiveMatch], list[Player]]:

    match_models.sort(key=lambda x: x.match_cost)

    matched_players: list[Player] = []
    chosen_matches: list[ActiveMatch] = []

    for match in match_models:
        if (
            match.request_A.player in matched_players
            or match.request_B.player in matched_players
        ):
            pass

        chosen_matches.append(
            ActiveMatch([match.request_A.player], [match.request_B.player])
        )
        matched_players.append(match.request_A.player)
        matched_players.append(match.request_B.player)

    return chosen_matches, matched_players


def _model_match(request_A: MatchRequest, request_B: MatchRequest) -> MatchModel:
    features_A = _extract_match_features(request_A)
    features_B = _extract_match_features(request_B)

    match_cost = _match_cost_function(
        _competitiveness_score(
            _bt_probability(
                features_A.skill_rating,
                features_B.skill_rating,
            )
        ),
        _latency_cost(
            features_A.latency,
            features_B.latency,
        ),
        _region_difference(
            features_A.region,
            features_B.region,
        ),
        _queue_time_benefit(
            features_A.queue_time,
            features_B.queue_time,
        ),
    )

    return MatchModel(request_A, request_B, match_cost)


def _extract_match_features(request: MatchRequest) -> MatchFeatures:
    skill_rating = request.player.player_features.get(SKILL_RATING_KEY)

    if skill_rating is None:
        raise ValueError("A player skill is None")

    if skill_rating < 0:
        raise ValueError("Skill ratings must be non-negative")

    latency = request.req_features.get(LATENCY_KEY)

    if latency is None:
        latency = 0

    if latency < 0:
        raise ValueError("Latency must be non-negative")

    region = request.req_features.get(REGION_KEY)

    if region is None:
        raise ValueError("Region is missing")

    return MatchFeatures(
        skill_rating=skill_rating,
        latency=latency,
        region=region,
        queue_time=request.tick_wait_time,
    )


def _match_cost_function(
    competitiveness, latency_cost, region_difference, queue_time_benefit
) -> int:
    """
    Match Cost Function - how much it costs to match two players, lower is better

    @param competitiveness: how close to 50/50 competitiion (lower is better)
    @param latency_cost: the difference in latency between the two players (lower is better)
    @param region_difference: whether players share region (lower is better)
    @param queue_time_benefit: combined queue time of players (higher is better)
    """
    return competitiveness + latency_cost + region_difference - queue_time_benefit


def _bt_probability(i: int, j: int) -> int:
    if i + j == 0:  # divide by 0 case
        return 50

    result = i / (i + j)
    return int(round(result * 100))


def _competitiveness_score(bt_probability: int) -> int:
    return abs(bt_probability - TARGET_PROBABILITY)


def _latency_cost(i: int, j: int) -> int:
    return abs((i - j) * LATENCY_SCALAR)


def _region_difference(i: Region, j: Region) -> int:
    return SAME_REGION if i == j else DIFFERENT_REGION


def _queue_time_benefit(queue_time_A: int, queue_time_B: int) -> int:
    return abs((queue_time_A + queue_time_B) * QUEUE_BENEFIT_SCALAR)
