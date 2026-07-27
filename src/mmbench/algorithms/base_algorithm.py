from abc import ABC, abstractmethod
from typing import Any


class MatchmakingAlgorithm(ABC):
    @abstractmethod
    def run_algorithm(self):
        pass

    @abstractmethod
    def setup_player_features(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def validate_player_features(self, input: dict[str, Any]):
        pass

    @abstractmethod
    def validate_req_features(self, input: dict[str, Any]):
        pass


class DefaultApproach(MatchmakingAlgorithm):
    def __init__(self):
        pass

    def run_algorithm(self):
        return super().run_algorithm()

    def setup_player_features(self) -> dict[str, Any]:
        return super().setup_player_features()

    def validate_player_features(self, input: dict[str, Any]):
        return super().validate_player_features(input)

    def validate_req_features(self, input: dict[str, Any]):
        return super().validate_req_features(input)
