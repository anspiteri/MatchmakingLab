from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto, unique
from typing import Any

LATENCY_KEY = "latency"
REGION_KEY = "region"
TRUE_SKILL_KEY = "true_skill"


@unique
class Region(StrEnum):
    NA = "north-america"  # North America
    SOUTH_AM = "south-am"  # South America
    EU = "europe"  # Europe
    ASIA = "asia"  # Asia
    OCEANIA = "oceania"  # Oceania (Australia/NZ)
    AFRICA = "africa"  # Africa (South Africa)
    UNDEFINED = "undefined"


class PlayerStatus(Enum):
    IDLE = auto()
    QUEUING = auto()
    PLAYING = auto()


@dataclass
class Player:
    """A single human account on the platform.

    ``player_features`` is a bag of attributes with two distinct kinds of owner.

    Strategy-owned keys (e.g. ``skill_rating``) are written by the active
    matchmaker: it decides both the keys it writes and the keys it expects back,
    seeding them on creation via its own ``setup_player_features`` hook. Any code
    reading a strategy-specific key must tolerate its absence — use ``dict.get``
    and validate, rather than subscripting — otherwise a player that was not
    created by that strategy's platform (a hand-built fixture, another
    matchmaker's leftover state) raises ``KeyError`` or silently models an
    unrated player. ``tests.helpers.make_player`` deliberately leaves the bag
    empty for that reason; use ``make_skill_player`` when a test needs a seeded
    database.

    Platform-owned keys are seeded by the platform itself on creation.
    ``TRUE_SKILL_KEY`` is the only one so far: the simulated player's real,
    hidden ability. It is deliberately *not* strategy-owned, because it is a
    property of the player rather than of any one matchmaking approach — the
    next approach needs it just as much as this one. Match outcomes are decided
    from it, while a strategy's estimate (``skill_rating``) is what matchmaking
    actually reasons about. Keeping the two separate is what makes the rating
    system measurable: if outcomes were decided from the estimate, a matchmaker
    would be graded against its own opinion of the world. Nothing but the
    platform's creation path ever writes this key, and it never changes
    afterwards.
    """

    id: int
    username: str
    wins: int
    loses: int
    default_region: Region
    player_features: dict[str, Any] = field(default_factory=dict)
    status: PlayerStatus = PlayerStatus.IDLE


@dataclass
class MatchRequest:
    player: Player
    req_features: dict[str, Any] = field(default_factory=dict)
    tick_wait_time: int = 0


@dataclass
class MatchProposal:
    match_cost: int
    team_A: list[MatchRequest] = field(default_factory=list)
    team_B: list[MatchRequest] = field(default_factory=list)


@dataclass
class ActiveMatch:
    """A match in progress.

    ``score_A``/``score_B`` are the running round wins for each side, and
    ``tick_match_length`` doubles as the number of rounds played. A match ends
    when one side reaches the simulator's points target, so length is an
    *outcome* of how the match went rather than an independently chosen number:
    a lopsided pairing finishes quickly and a close one runs long.
    """

    match_cost: int
    team_A: list[Player] = field(default_factory=list)
    team_B: list[Player] = field(default_factory=list)
    tick_match_length: int = 0
    score_A: int = 0
    score_B: int = 0


@dataclass
class FinishedMatch:
    match_length: int
    winning_team: list[Player] = field(default_factory=list)
    losing_team: list[Player] = field(default_factory=list)
