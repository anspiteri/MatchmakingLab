from random import Random
from typing import Any

from matchmakinglab.core.models import (
    REGION_KEY,
    TRUE_SKILL_KEY,
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

# Bounds for a simulated player's real, hidden ability. Deliberately wider than
# the strategy's base rating (100) and centred on it, so a population starts out
# genuinely heterogeneous. A narrow or near-uniform population would leave the
# matcher with nothing to discover, and every approach would then look
# identical — see docs/matchmaking-implementations.md.
MIN_TRUE_SKILL = 40
MAX_TRUE_SKILL = 160


class Platform:
    def __init__(self, strategy: MatchmakingStrategy, rng: Random | None = None):
        self._id_count = 0
        self.strategy = strategy
        self._rng = rng

    def use_rng(self, rng: Random) -> None:
        """Attach the source of hidden-skill draws, if none was given at build.

        The harness calls this so a seeded run also seeds player ability. A
        platform built with its own rng keeps it: an explicitly supplied source
        is never silently replaced.
        """
        if self._rng is None:
            self._rng = rng

    def add_to_matchmaking_queue(
        self, username: str, req_features: dict[str, Any], state: PlatformState
    ):

        player: Player | None = state.get_player(username)

        if player is None:
            region = req_features.get(REGION_KEY)
            if not region:
                region = Region.OCEANIA

            player_features: dict[str, Any] = self.strategy.setup_player_features()
            player_features[TRUE_SKILL_KEY] = self._draw_true_skill()
            player = state.add_player(
                Player(self._id_count, username, 0, 0, region, player_features)
            )

            self._id_count += 1

        player.status = PlayerStatus.QUEUING
        state.enqueue_match_req(MatchRequest(player, req_features))

    def _draw_true_skill(self) -> int:
        """Draw a hidden real ability for a newly created player.

        The platform owns this value rather than the strategy: it models the
        player, not any particular matchmaking approach. It is drawn once at
        creation and never updated, which is what lets the simulation score a
        matchmaker's estimates against an independent truth.

        Without an ``rng`` the platform stays fully deterministic and every
        player shares the midpoint, which is the right behaviour for the many
        unit tests that construct ``Platform(BradleyTerry())`` directly — they
        are asserting on matchmaking mechanics, not on simulated player quality.
        """
        if self._rng is None:
            return (MIN_TRUE_SKILL + MAX_TRUE_SKILL) // 2

        return self._rng.randint(MIN_TRUE_SKILL, MAX_TRUE_SKILL)

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
            for player in match.winning_team:
                player.status = PlayerStatus.IDLE
                player.wins += 1

            for player in match.losing_team:
                player.status = PlayerStatus.IDLE
                player.loses += 1

            global_finished_list.append(match)

    def update_player_features(
        self, finished_matches: list[FinishedMatch], strategy: MatchmakingStrategy
    ):
        for match in finished_matches:
            strategy.update_player_features(match)

    def increment_wait_time(self, matchmaking_queue: list[MatchRequest]):
        for req in matchmaking_queue:
            req.tick_wait_time += 1
