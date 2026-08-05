from enum import StrEnum, unique
from typing import Any


@unique
class Region(StrEnum):
    NA = "north-america"  # North America
    SOUTH_AM = "south-am"  # South America
    EU = "europe"  # Europe
    ASIA = "asia"  # Asia
    OCEANIA = "oceania"  # Oceania (Australia/NZ)
    AFRICA = "africa"  # Africa (South Africa)


class Player:
    def __init__(self, id: int, username: str, player_features: dict[str, Any]):
        self.id = id
        self.username = username
        self.player_features = player_features


class MatchRequest:
    def __init__(self, player: Player, req_features: dict[str, Any]):
        self.player = player
        self.req_features = req_features


class ActiveMatch:
    def __init__(self, team_A: list[Player], team_B: list[Player]):
        self.team_A = team_A
        self.team_B = team_B
        self.tick_count = 0


class FinishedMatch:
    def __init__(self, winning_team: list[Player], losing_team: list[Player]):
        self.winning_team = winning_team
        self.losing_team = losing_team
