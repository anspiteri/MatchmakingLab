from enum import Enum, auto
from itertools import combinations
from typing import Any, Optional
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
class MatchModel:
    def __init__(self, A: MatchRequest, B: MatchRequest, match_cost: int):
        self.A = A
        self.B = B
        self.match_cost = match_cost


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
        if match.A.player in matched_players or match.B.player in matched_players:
            pass

        chosen_matches.append(ActiveMatch([match.A.player], [match.B.player]))
        matched_players.append(match.A.player)
        matched_players.append(match.B.player)

    return chosen_matches, matched_players


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

    if skill_rating_A < 0 or skill_rating_B < 0:
        raise ValueError("Skill ratings must be non-negative")

    latency_A: Optional[int]
    latency_B: Optional[int]

    latency_A, latency_B = (
        player_A.req_features.get(LATENCY_KEY),
        player_A.req_features.get(LATENCY_KEY),
    )

    if latency_A is None:
        latency_A = 0

    if latency_B is None:
        latency_B = 0

    if latency_A < 0 or latency_B < 0:
        raise ValueError("Latency must be non-negative")

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

    match_cost = _match_cost_function(
        _competitiveness_score(_bt_probability(skill_rating_A, skill_rating_B)),
        _latency_cost(latency_A, latency_B),
        _region_difference(region_A, region_B),
        _queue_time_benefit(queue_time_A, queue_time_B),
    )

    return MatchModel(player_A, player_B, match_cost)


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
