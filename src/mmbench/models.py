from enum import StrEnum, unique


@unique
class Region(StrEnum):
    NA = "north-america"  # North America
    SOUTH_AM = "south-am"  # South America
    EU = "europe"  # Europe
    ASIA = "asia"  # Asia
    OCEANIA = "oceania"  # Oceania (Australia/NZ)
    AFRICA = "africa"  # Africa (South Africa)


class Player:
    def __init__(
        self, id: int, username: str, skill_rating: float, stats: dict[str, float]
    ):
        self.id = id
        self.username = username
        self.skill_rating = skill_rating
        self.stats = stats


class MatchRequest:
    def __init__(self, player: Player, time: int, latency: float, region: Region):
        self.player = player
        self.time = time
        self.latency = latency
        self.region = region


class NewMatch:
    def __init__(self, team_A: list[Player], team_B: list[Player]):
        self.team_A = team_A
        self.team_B = team_B


class MatchResults:
    def __init__(self, winning_team: list[Player], losing_team: list[Player]):
        self.winning_team = winning_team
        self.losing_team = losing_team
