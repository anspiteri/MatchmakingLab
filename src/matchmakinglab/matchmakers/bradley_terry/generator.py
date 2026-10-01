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
from matchmakinglab.matchmakers.bradley_terry.strategy import SKILL_RATING_KEY


class GenerationType(Enum):
    NEW_PLAYER = auto()
    EXISTING_PLAYER = auto()


_GEN_TYPES = [GenerationType.NEW_PLAYER, GenerationType.EXISTING_PLAYER]

MAX_TRIES = 25

# The simulated population. One account per generated user, drawn from a fixed
# pool, so this is a hard ceiling on how many players can ever exist in a run.
DEFAULT_PLAYER_COUNT = 500


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

    Every call yields distinct users: a player is a single human and can hold at
    most one request per batch, so a batch must never be able to queue a player
    against themselves.
    """

    def __init__(
        self, player_count: int = DEFAULT_PLAYER_COUNT, seed: int | None = None
    ) -> None:
        self._pool = [f"player_{i:04d}" for i in range(player_count)]
        self._index = 0
        # None means no source supplied yet: the harness attaches one for a seeded
        # run, mirroring Platform.use_rng, and an unseeded generator built directly
        # still resolves its own below.
        self._rng: random.Random | None = None if seed is None else random.Random(seed)

    def use_rng(self, rng: random.Random) -> None:
        if self._rng is None:
            self._rng = rng

    def _resolve_rng(self) -> random.Random:
        if self._rng is None:
            self._rng = random.Random()
        return self._rng

    def generate_requests(self, number, player_database: dict) -> list:
        result = []
        rng = self._resolve_rng()

        # CASE ONE: EMPTY DATABASE
        if not player_database:
            if number > len(self._pool):
                raise ValueError("Request number is greater than max allowed players")

            for _ in range(number):
                result.append(_gen_new_player_request(self._index, self._pool, rng))
                self._index += 1
            return result

        # CASE TWO: FULL DATABASE
        elif self._index >= len(self._pool):
            result.extend(
                _gen_n_existing_requests(
                    number, self._index, self._pool, rng, player_database
                )
            )

        # CASE THREE: NON-EMPTY / NON-FULL
        else:
            emitted: set[str] = set()

            for i in range(number):
                match rng.choice(_GEN_TYPES):
                    case GenerationType.NEW_PLAYER:
                        if self._index >= len(self._pool):
                            result.extend(
                                _gen_n_existing_requests(
                                    number - i,
                                    self._index,
                                    self._pool,
                                    rng,
                                    player_database,
                                    exclude=emitted,
                                )
                            )
                            break

                        else:
                            result.append(
                                _gen_new_player_request(self._index, self._pool, rng)
                            )
                            emitted.add(self._pool[self._index])
                            self._index += 1

                    case GenerationType.EXISTING_PLAYER:
                        existing = _gen_existing_player_request(
                            self._index,
                            self._pool,
                            rng,
                            player_database,
                            exclude=emitted,
                        )
                        if existing is None:
                            for _ in range(number - i):
                                if self._index >= len(self._pool):
                                    return result

                                result.append(
                                    _gen_new_player_request(
                                        self._index, self._pool, rng
                                    )
                                )
                                emitted.add(self._pool[self._index])
                                self._index += 1
                            break
                        else:
                            result.append(existing)
                            emitted.add(existing["user"])

        return result


def _gen_new_player_request(index, pool, rng):
    username = pool[index]
    return {
        "user": username,
        "req_features": {
            LATENCY_KEY: rng.randint(5, 120),
            REGION_KEY: rng.choice(_ACTIVE_REGIONS),
        },
        "is_new": True,
    }


def _gen_existing_player_request(
    index, pool, rng, database, exclude: set[str] | None = None
) -> dict | None:
    """Draw one idle player from the pool, or return None.

    ``exclude`` holds the usernames already emitted for the batch currently being
    built. Without it a randomly drawn player can be returned twice, putting two
    match requests for the same player into one queue — which the matcher would
    then be free to pair together, letting a player play themselves.
    """
    exclude = set() if exclude is None else exclude
    chosen: str | None = None
    tries = 0

    while tries < MAX_TRIES and chosen is None:
        username = pool[rng.randint(0, index - 1)]
        player: Player | None = database.get(username)
        if (
            player is not None
            and player.status == PlayerStatus.IDLE
            and username not in exclude
        ):
            chosen = username
        tries += 1

    if chosen is None:
        return None

    player = database[chosen]
    return {
        "user": chosen,
        "req_features": {
            LATENCY_KEY: rng.randint(5, 120),
            REGION_KEY: player.default_region,
            # Direct lookup: the platform always seeds this via the strategy's
            # setup_player_features, so an absent key means the player did not
            # come from a BradleyTerry-managed platform.
            SKILL_RATING_KEY: player.player_features[SKILL_RATING_KEY],
        },
        "is_new": False,
    }


def _gen_n_existing_requests(n, index, pool, rng, database, exclude=None) -> list:
    result = []
    emitted: set[str] = set() if exclude is None else set(exclude)

    for _ in range(n):
        request = _gen_existing_player_request(
            index, pool, rng, database, exclude=emitted
        )
        if request is None:
            break
        else:
            result.append(request)
            emitted.add(request["user"])

    return result
