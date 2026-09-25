from typing import Any

from matchmakinglab.core.models import (
    REGION_KEY,
    ActiveMatch,
    FinishedMatch,
    MatchProposal,
    MatchRequest,
    Player,
    PlayerStatus,
    Region,
)
from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers import MatchmakingStrategy


class Platform:
    def __init__(self, strategy: MatchmakingStrategy):
        self._id_count = 0
        self.strategy = strategy

    def add_to_matchmaking_queue(
        self, username: str, req_features: dict[str, Any], state: PlatformState
    ):

        player: Player | None = state.get_player(username)

        if player is None:
            region = req_features.get(REGION_KEY)
            if not region:
                region = Region.OCEANIA

            player_features: dict[str, Any] = self.strategy.setup_player_features()
            player = state.add_player(
                Player(self._id_count, username, region, player_features)
            )

            self._id_count += 1

        player.status = PlayerStatus.QUEUING
        state.enqueue_match_req(MatchRequest(player, req_features))

    def match_players(
        self,
        queue: list[MatchRequest],
        strategy: MatchmakingStrategy,
    ) -> list[MatchProposal]:

        matches, remaining = strategy.run_algorithm(queue)

        # Mutate the shared queue in place so unmatched requests remain queued
        # (reassigning a local would silently drop them from state).
        queue.clear()
        queue.extend(remaining)
        return matches

    def start_matches(
        self, match_proposals: list[MatchProposal], active_matches: list[ActiveMatch]
    ):
        for match in match_proposals:
            team_A = [req.player for req in match.team_A]
            team_B = [req.player for req in match.team_B]
            active_matches.append(ActiveMatch(match.match_cost, team_A, team_B))

            for player in team_A + team_B:
                player.status = PlayerStatus.PLAYING

    def end_matches(
        self,
        simulated_matches: list[FinishedMatch],
        global_finished_list: list[FinishedMatch],
    ):
        for match in simulated_matches:
            for player in match.winning_team + match.losing_team:
                player.status = PlayerStatus.IDLE

            global_finished_list.append(match)

    def update_player_features(
        self, finished_matches: list[FinishedMatch], strategy: MatchmakingStrategy
    ):
        for match in finished_matches:
            strategy.update_player_features(match)

    def increment_wait_time(self, matchmaking_queue: list[MatchRequest]):
        for req in matchmaking_queue:
            req.tick_wait_time += 1
