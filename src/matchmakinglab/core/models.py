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
    id: int
    username: str
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
