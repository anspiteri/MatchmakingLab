from abc import ABC, abstractmethod
from typing import Any

from matchmakinglab.models import ActiveMatch, FinishedMatch, MatchRequest


class MatchmakingStrategy(ABC):
    @abstractmethod
    def run_algorithm(
        self, matchmaking_queue: list[MatchRequest], active_games: list[ActiveMatch]
    ):
        pass

    @abstractmethod
    def setup_player_features(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def update_player_features(self, finished_match: FinishedMatch):
        pass
