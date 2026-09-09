import random

from matchmakinglab.core.models import LATENCY_KEY, REGION_KEY, Region
from matchmakinglab.matchmakers.base_generator import RequestGenerator

# Non-UNDEFINED regions that can appear in request features.
_ACTIVE_REGIONS = [
    Region.NA,
    Region.SOUTH_AM,
    Region.EU,
    Region.ASIA,
    Region.OCEANIA,
    Region.AFRICA,
]


class BradleyTerryGenerator(RequestGenerator):
    """Emits distinct player requests each step with plausible BT features.

    A pool of usernames is rotated so the queue receives many distinct players,
    allowing the matchmaker to form real pairings and the queue to drain.
    """

    def __init__(self, player_count: int = 500, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._pool = [f"player_{i:04d}" for i in range(player_count)]
        self._index = 0

    def generate_requests(self, number) -> list:
        result = []
        for _ in range(number):
            username = self._pool[self._index % len(self._pool)]
            self._index += 1
            result.append(
                {
                    "user": username,
                    "req_features": {
                        LATENCY_KEY: self._rng.randint(5, 120),
                        REGION_KEY: self._rng.choice(_ACTIVE_REGIONS),
                    },
                }
            )

        return result
