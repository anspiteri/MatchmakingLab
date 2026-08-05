from typing import Optional
from matchmakinglab.models import MatchRequest, ActiveMatch, FinishedMatch, Player


class PlatformState:
    def __init__(self) -> None:
        self._player_database: dict[str, Player] = {}

        self._matchmaking_queue: list[MatchRequest] = []
        self._active_matches: list[ActiveMatch] = []
        self._finished_matches: list[FinishedMatch] = []

    def add_player(self, player: Player) -> Player:
        """
        Assumes that player is not already in the database, otherwise data corruption due to overwrite
        """
        self._player_database[player.username] = player
        return player

    def get_player(self, username: str) -> Optional[Player]:
        return self._player_database.get(username)

    def enqueue_match_req(self, req: MatchRequest):
        self._matchmaking_queue.append(req)

    def get_matchmaking_queue(self):
        """
        Gives requester read/write privilege to queue.
        """
        return self._matchmaking_queue

    def add_active_match(self, active_match: ActiveMatch):
        self._active_matches.append(active_match)

    def get_active_games(self):
        """
        Gives requester read/write privilege to data structure.
        """
        return self._active_matches

    def enqueue_finished_match(self, finished_match: FinishedMatch):
        self._finished_matches.append(finished_match)

    def get_finished_matches(self):
        """
        Gives requester read/write privilege to data structure.
        """
        return self._finished_matches
