from typing import Any
from matchmakinglab.matchmakers.base_class import MatchmakingStrategy
from matchmakinglab.models import FinishedMatch, MatchRequest

BASE_SKILL_RATING = 1500


class BradleyTerry(MatchmakingStrategy):
    def __init__(self):
        pass

    def run_algorithm(self, queue: list[MatchRequest]):
        pass

    def setup_player_features(self) -> dict[str, Any]:
        return {"skill_rating": BASE_SKILL_RATING}

    def update_player_features(self, finished_match: FinishedMatch):
        pass
