from dataclasses import dataclass
from enum import Enum, auto
from itertools import combinations
from math import exp
from typing import Any

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
    FinishedMatch,
    MatchProposal,
    MatchRequest,
    Player,
    Region,
)
from matchmakinglab.matchmakers import MatchmakingStrategy

# --- KEYS ---
SKILL_RATING_KEY = "skill_rating"

# --- WEIGHTS ---
# Assumed to be positive scalars
#
# Step size for the rating update, applied to log(rating) and so a relative step
# in rating space. 0.02 keeps the estimated spread near parity with the truth it
# tracks (1.05x at 2000 ticks over five seeds, against 1.52x for the additive
# rule this replaced) at no cost in accuracy. Measured rates, 150 players,
# seed 1, 2000 ticks: 0.01 -> 1.03, 0.02 -> 1.03, 0.05 -> 1.71.
# See docs/matchmaking-implementations.md before raising it.
LEARNING_RATE = 0.02

BASE_SKILL_RATING = 100.0

# Ratings are floats. A relative step small enough to be well behaved is also
# small enough that an integer rating rounds it away, which stalls the update
# for a whole population - at LEARNING_RATE 0.01, no player's rating ever left
# 100 while the best ran to 240. See docs/matchmaking-implementations.md.
MIN_SKILL_RATING = 1.0

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
    skill_rating: float
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
        """Seed ``Player.player_features`` for a newly created player.

        The platform applies this when it creates a player, which is the only
        thing that guarantees SKILL_RATING_KEY is present. Any code that needs
        the rating must therefore read it defensively, as _extract_match_features
        does, so a player built outside this platform surfaces a clear error
        instead of a bare KeyError.
        """

        return {SKILL_RATING_KEY: BASE_SKILL_RATING}

    def update_player_features(self, finished_match: FinishedMatch):
        assert len(finished_match.winning_team) > 0
        assert len(finished_match.losing_team) > 0

        winner = finished_match.winning_team[0]
        loser = finished_match.losing_team[0]

        # Subscripted deliberately: this runs only for players the platform
        # created, and by the time a match finishes every queued player has
        # already been through _extract_match_features, which rejects an unrated
        # or malformed rating before any of this arithmetic happens.
        winner_rating = winner.player_features[SKILL_RATING_KEY]
        loser_rating = loser.player_features[SKILL_RATING_KEY]

        # r_w / (r_w + r_l) is already the Bradley-Terry probability in log
        # coordinates, since sigmoid(log r_w - log r_l) is this same ratio. Only
        # the update was in the wrong space.
        probability = winner_rating / (winner_rating + loser_rating)

        error = 1.0 - probability

        # A constant step on log(rating), so a constant ratio here. exp rather
        # than 1 +/- step: log(1 + step) is not -log(1 - step), so the
        # multiplicative form is the only one of the pair that moves the two
        # sides by equal and opposite amounts on the log scale, and the only one
        # that cannot produce a negative rating.
        factor = exp(LEARNING_RATE * error)

        winner.player_features[SKILL_RATING_KEY] = winner_rating * factor
        loser.player_features[SKILL_RATING_KEY] = max(
            MIN_SKILL_RATING, loser_rating / factor
        )

    def run_algorithm(
        self, queue_snapshot: list[MatchRequest]
    ) -> tuple[list[MatchProposal], list[MatchRequest]]:

        if len(queue_snapshot) == 0:
            return ([], queue_snapshot)

        match_models: list[MatchModel] = []

        match self._candidate_generation_method:
            case BTCandidateGenerationMethod.NAIVE:
                # A player cannot be their own opponent, so any pair naming the
                # same player on both sides is not a candidate at all. The
                # generator should not emit duplicate requests for one player, but
                # self-pairing is a correctness invariant of the matcher rather
                # than a property of its input.
                match_models = [
                    _model_match(A, B)
                    for A, B in combinations(queue_snapshot, 2)
                    if A.player != B.player
                ]
            case _:
                raise ValueError(
                    f"No implementation for candidate generation method: {self._candidate_generation_method}"
                )

        matches, players_matched = _queue_matching_function(
            match_models, self._optimisation_method
        )

        remaining = [
            request
            for request in queue_snapshot
            if request.player not in players_matched
        ]

        return matches, remaining


# --- MAIN ALGORITHMS & HELPER FUNCTIONS ---


# Global Optitimisation
def _queue_matching_function(
    match_models: list[MatchModel],
    optimisation_method: BTOptimisationMethod,
) -> tuple[list[MatchProposal], list[Player]]:
    """
    This is a wrapper for the global objective function that takes the whole queue
    and finds the optimum configuration of teams. The wrapper allows for different
    approaches to this optimisation to be configured.
    """
    result: tuple[list[MatchProposal], list[Player]] = ([], [])

    match optimisation_method:
        case BTOptimisationMethod.GREEDY:
            result = _greedy_optimisation(match_models)
        case _:
            raise ValueError(
                f"No implementation for optimisation method: {optimisation_method}"
            )

    return result


def _greedy_optimisation(
    match_models: list[MatchModel],
) -> tuple[list[MatchProposal], list[Player]]:

    match_models.sort(key=lambda x: x.match_cost)

    matched_players: list[Player] = []
    chosen_matches: list[MatchProposal] = []

    for match in match_models:
        if (
            match.request_A.player == match.request_B.player
            or match.request_A.player in matched_players
            or match.request_B.player in matched_players
        ):
            continue

        chosen_matches.append(
            MatchProposal(match.match_cost, [match.request_A], [match.request_B])
        )
        matched_players.append(match.request_A.player)
        matched_players.append(match.request_B.player)

    return chosen_matches, matched_players


# Match Modelling
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
    """Pull matchable attributes off a queued request, validating as we go.

    Uses .get for SKILL_RATING_KEY so a player whose player_features were never
    seeded by setup_player_features fails with a named ValueError here, rather
    than a KeyError deeper in candidate generation.
    """

    skill_rating = request.player.player_features.get(SKILL_RATING_KEY)

    if skill_rating is None:
        raise ValueError("A player skill is None")

    if isinstance(skill_rating, bool) or not isinstance(skill_rating, (int, float)):
        raise ValueError("A player skill is not a number")

    if skill_rating < MIN_SKILL_RATING:
        raise ValueError(f"Skill ratings must be at least {MIN_SKILL_RATING}")

    latency = request.req_features.get(LATENCY_KEY)

    if latency is None:
        latency = 0

    if not isinstance(latency, int):
        raise ValueError("Latency must be an int")

    if latency < 0:
        raise ValueError("Latency must be non-negative")

    region = request.req_features.get(REGION_KEY)

    if region is None or region is Region.UNDEFINED:
        raise ValueError("Region is missing")

    return MatchFeatures(
        skill_rating=skill_rating,
        latency=latency,
        region=region,
        queue_time=request.tick_wait_time,
    )


# Match Costing
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


def _bt_probability(i: float, j: float) -> int:
    if i + j == 0:  # divide by 0 case
        return 50

    result = i / (i + j)
    return round(result * 100)


def _competitiveness_score(bt_probability: int) -> int:
    return abs(bt_probability - TARGET_PROBABILITY)


def _latency_cost(i: int, j: int) -> int:
    return abs((i - j) * LATENCY_SCALAR)


def _region_difference(i: Region, j: Region) -> int:
    return SAME_REGION if i == j else DIFFERENT_REGION


def _queue_time_benefit(queue_time_A: int, queue_time_B: int) -> int:
    return abs((queue_time_A + queue_time_B) * QUEUE_BENEFIT_SCALAR)
