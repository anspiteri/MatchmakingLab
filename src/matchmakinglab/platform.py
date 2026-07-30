from typing import Any, Optional
from matchmakinglab.matchmakers import MatchmakingStrategy, BradleyTerry
from matchmakinglab.state import PlatformState
from matchmakinglab.models import FinishedMatch, MatchRequest, Player


class Platform:
    def __init__(self, strategy: MatchmakingStrategy = BradleyTerry()):
        self._id_count = 0
        self._strategy = strategy

    def add_to_matchmaking_queue(
        self, username: str, req_features: dict[str, Any], state: PlatformState
    ):

        player: Optional[Player] = state.get_player(username)

        if player is None:
            player_features: dict[str, Any] = self._strategy.setup_player_features()
            player = state.add_player(Player(self._id_count, username, player_features))
            self._id_count += 1

        state.enqueue_match_req(MatchRequest(player, req_features))

    def tick(self, state: PlatformState):
        self._match_players(state.get_matchmaking_queue(), self._strategy)
        self._simulate_matches()
        self._update_player_features(state.get_finished_matches(), self._strategy)
        self._update_display()

    def _match_players(self, queue: list[MatchRequest], strategy: MatchmakingStrategy):
        strategy.run_algorithm(queue)

    def _simulate_matches(self):
        return None

    def _update_player_features(
        self, finished_matches: list[FinishedMatch], strategy: MatchmakingStrategy
    ):
        for match in finished_matches:
            strategy.update_player_features(match)

    def _update_display(self):
        return None
