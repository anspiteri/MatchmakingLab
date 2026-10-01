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
    def create_generator(self, player_count: int) -> RequestGenerator:
        """Build the generator, sized to hold ``player_count`` distinct accounts.

        Population size is passed in rather than owned by the factory: it is a
        property of the simulated world, and the CLI resolves it alongside the
        rest of the simulation setup.
        """


class BradleyTerryFactory(MatchmakerFactory):
    def __init__(self, config: dict | None = None):
        self._config = config or {}

    def create_platform(self) -> Platform:
        return Platform(BradleyTerry(**self._config))

    def create_generator(self, player_count: int) -> RequestGenerator:
        return BradleyTerryGenerator(player_count=player_count)
