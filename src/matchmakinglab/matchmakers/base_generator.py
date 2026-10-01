from abc import ABC, abstractmethod
from random import Random


class RequestGenerator(ABC):
    @abstractmethod
    def generate_requests(self, number: int, player_database: dict) -> list:
        pass

    def use_rng(self, rng: Random) -> None:
        """Attach a source of randomness, unless the generator already has one.

        The harness calls this so a seeded run also seeds request generation —
        who queues, and with what latency and region, are draws like any other.
        A generator built with its own seed keeps it: an explicitly supplied
        source is never silently replaced. The default is a no-op, so a
        generator that does not draw at all needs no change.
        """
