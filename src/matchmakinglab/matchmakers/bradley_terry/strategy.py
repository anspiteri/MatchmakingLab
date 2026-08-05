from itertools import combinations
from typing import Any, Optional
from matchmakinglab.matchmakers import MatchmakingStrategy
from matchmakinglab.models import ActiveMatch, FinishedMatch, MatchRequest, Player

SKILL_RATING_KEY = "skill_rating"
BASE_SKILL_RATING = 100

TARGET_PROBABILITY = 50
TARGET_THRESHOLD = 10
THRESHOLD_INCREMENT = 10


class PossibleMatch:
    def __init__(self, playerA: Player, playerB: Player, score: int):
        self.playerA = playerA
        self.playerB = playerB
        self.score = score


def _calc_bt_score(p_skill: Optional[int], q_skill: Optional[int]):
    if p_skill is None or q_skill is None:
        raise TypeError("Invalid integer: None")
    try:
        result = p_skill / (p_skill + q_skill)
    except ZeroDivisionError:
        raise ZeroDivisionError("Cannot divide by zero")
    else:
        return int(round(result * 100))


def _model_match(player_A: Player, player_B: Player):
    return PossibleMatch(
        player_A,
        player_B,
        _calc_bt_score(
            player_A.player_features.get(SKILL_RATING_KEY),
            player_B.player_features.get(SKILL_RATING_KEY),
        ),
    )


class BradleyTerry(MatchmakingStrategy):
    def __init__(self):
        pass

    def run_algorithm(
        self, matchmaking_queue: list[MatchRequest], active_games: list[ActiveMatch]
    ):

        # Stage One: Calculate probabilities for all combinations of queued players
        match_models: Optional[list[PossibleMatch]] = [
            _model_match(A.player, B.player)
            for A, B in combinations(matchmaking_queue, 2)
        ].sort(key=lambda x: abs(x.score - TARGET_PROBABILITY))

        if match_models is None:
            raise TypeError("Creating match models failed: None")

        # State Two: Match players within a specified threshold of closeness to 50%
        for possible_match in match_models:
            if abs(possible_match.score - TARGET_PROBABILITY) <= TARGET_THRESHOLD:
                matchmaking_queue.pop(possible_match.player_A)
                matchmaking_queue.pop(possible_match.player_B)
                # TODO: Need to figure out a way to remove players from match models list
                # TODO: Need to also implement ordering loosening of threshold depending on wait time. OR leave it out.
                active_games.append(
                    ActiveMatch(possible_match.player_A, possible_match.player_B)
                )

    def setup_player_features(self) -> dict[str, Any]:
        return {SKILL_RATING_KEY: BASE_SKILL_RATING}

    def update_player_features(self, finished_match: FinishedMatch):
        pass
