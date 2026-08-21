from enum import StrEnum, unique
from dataclasses import dataclass, field
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


@dataclass
class Player:
    id: int
    username: str
    player_features: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchRequest:
    player: Player
    req_features: dict[str, Any] = field(default_factory=dict)
    tick_wait_time: int = 0


@dataclass
class ActiveMatch:
    team_A: list[Player] = field(default_factory=list)
    team_B: list[Player] = field(default_factory=list)
    tick_match_length: int = 0


@dataclass
class FinishedMatch:
    winning_team: list[Player] = field(default_factory=list)
    losing_team: list[Player] = field(default_factory=list)
