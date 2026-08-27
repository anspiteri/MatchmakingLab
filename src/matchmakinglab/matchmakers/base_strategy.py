from abc import ABC, abstractmethod
from typing import Any

from matchmakinglab.core.models import ActiveMatch, FinishedMatch, MatchRequest


class MatchmakingStrategy(ABC):
    @abstractmethod
    def setup_player_features(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def update_player_features(self, finished_match: FinishedMatch):
        pass

    @abstractmethod
    def run_algorithm(
        self, queue_snapshot: list[MatchRequest]
    ) -> tuple[list[ActiveMatch], list[MatchRequest]]:
        pass
