from typing import Any, Optional
from mmbench.algorithms.base_algorithm import DefaultApproach, MatchmakingAlgorithm
from mmbench.state import PlatformState
from mmbench.models import MatchRequest, Player


class Platform:
    def __init__(self, algorithm: MatchmakingAlgorithm = DefaultApproach()):
        self._id_count = 0
        self._algorithm = algorithm

    def add_to_matchmaking_queue(
        self, username: str, req_features: dict[str, Any], state: PlatformState
    ):

        player: Optional[Player] = state.get_player(username)

        if player is None:
            player_features: dict[str, Any] = self._algorithm.setup_player_features()
            player = state.add_player(Player(self._id_count, username, player_features))
            self._id_count += 1

        state.enqueue_match_req(MatchRequest(player, req_features))

    def tick(self):
        self.match_players(self._algorithm)
        self.simulate_matches()
        self.update_ratings()
        self.update_display()

    def match_players(self, algorithm: MatchmakingAlgorithm):
        algorithm.run_algorithm()

    def simulate_matches(self):
        return None

    def update_ratings(self):
        return None

    def update_display(self):
        return None
