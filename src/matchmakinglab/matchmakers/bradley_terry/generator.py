import random
from enum import Enum, auto

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
    Player,
    PlayerStatus,
    Region,
)
from matchmakinglab.matchmakers.base_generator import RequestGenerator


class GenerationType(Enum):
    NEW_PLAYER = auto()
    EXISTING_PLAYER = auto()


_GEN_TYPES = [GenerationType.NEW_PLAYER, GenerationType.EXISTING_PLAYER]

MAX_TRIES = 25


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
    """Generates a mixture of new and existing player requests using Bradley-Terry features.

    Maintains a local pool of predefined user accounts. Depending on the current size
    and saturation of the provided player database, it dynamically balances requests:

    * If empty, fills the batch entirely with brand new player entries.
    * If the pool is fully exhausted, attempts to fetch only active idle players from database state.
    * If partially populated, randomly mixes new signups and existing session pullbacks,
    with automated fallback protections if idle players are hard to locate.
    """

    def __init__(self, player_count: int = 500, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._pool = [f"player_{i:04d}" for i in range(player_count)]
        self._index = 0

    def generate_requests(self, number, player_database: dict) -> list:
        result = []

        # CASE ONE: EMPTY DATABASE
        if not player_database:
            if number > len(self._pool):
                raise ValueError("Request number is greater than max allowed players")

            for _ in range(number):
                result.append(
                    _gen_new_player_request(self._index, self._pool, self._rng)
                )
                self._index += 1
            return result

        # CASE TWO: FULL DATABASE
        elif self._index >= len(self._pool):
            result.extend(
                _gen_n_existing_requests(
                    number, self._index, self._pool, self._rng, player_database
                )
            )

        # CASE THREE: NON-EMPTY / NON-FULL
        else:
            for i in range(number):
                match self._rng.choice(_GEN_TYPES):
                    case GenerationType.NEW_PLAYER:
                        if self._index >= len(self._pool):
                            result.extend(
                                _gen_n_existing_requests(
                                    number - i,
                                    self._index,
                                    self._pool,
                                    self._rng,
                                    player_database,
                                )
                            )
                            break

                        else:
                            result.append(
                                _gen_new_player_request(
                                    self._index, self._pool, self._rng
                                )
                            )
                            self._index += 1

                    case GenerationType.EXISTING_PLAYER:
                        existing = _gen_existing_player_request(
                            self._index, self._pool, self._rng, player_database
                        )
                        if existing is None:
                            for _ in range(number - i):
                                if self._index >= len(self._pool):
                                    return result

                                result.append(
                                    _gen_new_player_request(
                                        self._index, self._pool, self._rng
                                    )
                                )
                                self._index += 1
                            break
                        else:
                            result.append(existing)

        return result


def _gen_new_player_request(index, pool, rng):
    username = pool[index]
    return {
        "user": username,
        "req_features": {
            LATENCY_KEY: rng.randint(5, 120),
            REGION_KEY: rng.choice(_ACTIVE_REGIONS),
        },
    }


def _gen_existing_player_request(index, pool, rng, database) -> dict | None:
    player = None
    username = None
    tries = 0

    while tries < MAX_TRIES and (player is None or player.status != PlayerStatus.IDLE):
        username = pool[rng.randint(0, index - 1)]
        player: Player | None = database.get(username)
        tries += 1

    if player is None or player.status != PlayerStatus.IDLE:
        return None
    else:
        return {
            "user": username,
            "req_features": {
                LATENCY_KEY: rng.randint(5, 120),
                REGION_KEY: player.default_region,
            },
        }


def _gen_n_existing_requests(n, index, pool, rng, database) -> list:
    result = []
    for _ in range(n):
        request = _gen_existing_player_request(index, pool, rng, database)
        if request is None:
            break
        else:
            result.append(request)

    return result
