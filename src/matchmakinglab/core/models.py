from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto, unique
from typing import Any

LATENCY_KEY = "latency"
REGION_KEY = "region"


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

    ``player_features`` is a strategy-owned bag of attributes. The core model
    treats it as opaque: it defaults to empty and the platform does not populate
    it. The active matchmaker decides both the keys it writes and the keys it
    expects back, seeding them on creation via its own setup hook.

    Consequently any code reading a strategy-specific key must tolerate its
    absence — use ``dict.get`` and validate, rather than subscripting — otherwise
    a player that was not created by that strategy's platform (a hand-built
    fixture, another matchmaker's leftover state) raises ``KeyError`` or silently
    models an unrated player. ``tests.helpers.make_player`` deliberately leaves
    the bag empty for that reason; use ``make_skill_player`` when a test needs a
    seeded database.
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
    match_cost: int
    team_A: list[Player] = field(default_factory=list)
    team_B: list[Player] = field(default_factory=list)
    tick_match_length: int = 0


@dataclass
class FinishedMatch:
    match_length: int
    winning_team: list[Player] = field(default_factory=list)
    losing_team: list[Player] = field(default_factory=list)
