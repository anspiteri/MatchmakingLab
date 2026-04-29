from matchmaking_service.models import Player, Match, MatchRequest
from typing import Optional

class GameState:
    """
    In-memory store for players, match requests, and active matches.

    This class is intentionally lightweight and separate from business logic.
    It only manages storage and retrieval of domain objects.
    """

    def __init__(self):
        self._players: dict[str, Player] = {}
        self._queue: list[MatchRequest] = []
        self._matches: list[Match] = []

    # -----------------------
    # Player operations
    # -----------------------

    def add_player(self, player: Player):
        """Add a player to the state store."""
        if player is None:
            raise ValueError("Player cannot be None.")

        self._players[player.username] = player

    def get_player(self, username: str) -> Optional[Player]:
        """Retrieve a player by username."""
        return self._players.get(username)

    def get_player_population(self):
        """Return number of registered players."""
        return len(self._players)

    # -----------------------
    # Match request operations
    # -----------------------

    def add_match_request(self, request: MatchRequest):
        """Add a match request to the queue."""
        if request is None:
            raise ValueError("Request cannot be None.")

        self._queue.append(request)

    def get_all_match_requests(self):
        """Return all pending match requests."""
        return self._queue

    def get_match_request_number(self):
        """Return number of pending match requests."""
        return len(self._queue)

    # -----------------------
    # Match operations
    # -----------------------

    def add_match(self, match: Match):
        """Add an active match."""
        if match is None:
            raise ValueError("Match cannot be None.")

        self._matches.append(match)

    def get_all_matches(self):
        """Return all active matches."""
        return self._matches

    def get_number_of_matches(self):
        """Return number of active matches."""
        return len(self._matches)
