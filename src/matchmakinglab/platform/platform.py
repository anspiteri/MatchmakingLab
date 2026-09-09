from typing import Any

from matchmakinglab.core.models import ActiveMatch, FinishedMatch, MatchRequest, Player
from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers import BradleyTerry, MatchmakingStrategy


class Platform:
    def __init__(self, strategy: MatchmakingStrategy = BradleyTerry()):
        self._id_count = 0
        self._strategy = strategy

    def add_to_matchmaking_queue(
        self, username: str, req_features: dict[str, Any], state: PlatformState
    ):

        player: Player | None = state.get_player(username)

        if player is None:
            player_features: dict[str, Any] = self._strategy.setup_player_features()
            player = state.add_player(Player(self._id_count, username, player_features))
            self._id_count += 1

        state.enqueue_match_req(MatchRequest(player, req_features))

    def tick(self, state: PlatformState):
        """
        During tick(), Platform briefly shares matchmaking queue, active games, and
        finished matches with PlatformState
        """
        self._match_players(
            state.get_matchmaking_queue(), state.get_active_games(), self._strategy
        )
        self._update_player_features(state.get_finished_matches(), self._strategy)
        self._increment_wait_time(state.get_matchmaking_queue())

    def _match_players(
        self,
        queue: list[MatchRequest],
        active_matches: list[ActiveMatch],
        strategy: MatchmakingStrategy,
    ):

        matches, remaining = strategy.run_algorithm(queue)

        active_matches.extend(matches)
        # Mutate the shared queue in place so unmatched requests remain queued
        # (reassigning a local would silently drop them from state).
        queue.clear()
        queue.extend(remaining)

    def _update_player_features(
        self, finished_matches: list[FinishedMatch], strategy: MatchmakingStrategy
    ):
        for match in finished_matches:
            strategy.update_player_features(match)

    def _increment_wait_time(self, matchmaking_queue: list[MatchRequest]):
        for req in matchmaking_queue:
            req.tick_wait_time += 1
