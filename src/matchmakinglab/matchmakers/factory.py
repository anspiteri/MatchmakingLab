# Takes matchmaking configuration and builds tightly coupled Strategy and Generator

from abc import ABC, abstractmethod

from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry.generator import BradleyTerryGenerator
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry
from matchmakinglab.platform.platform import Platform


class MatchmakerFactory(ABC):
    @abstractmethod
    def create_platform(self) -> Platform:
        pass

    @abstractmethod
    def create_generator(self) -> RequestGenerator:
        pass


class BradleyTerryFactory(MatchmakerFactory):
    def __init__(self):
        pass

    def create_platform(self) -> Platform:
        return Platform(BradleyTerry())

    def create_generator(self) -> RequestGenerator:
        return BradleyTerryGenerator()
