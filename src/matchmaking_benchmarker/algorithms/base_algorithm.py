from abc import ABC, abstractmethod


class MatchmakingAlgorithm(ABC):
    @abstractmethod
    def run_algorithm(self):
        pass
