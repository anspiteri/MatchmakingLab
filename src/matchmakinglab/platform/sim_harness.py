from collections.abc import Callable
from random import Random

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
    TRUE_SKILL_KEY,
    FinishedMatch,
    Player,
)
from matchmakinglab.core.snapshot import SimSnapshot
from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    SKILL_RATING_KEY,
)
from matchmakinglab.platform.outcome import MatchOutcomeModel, TrueSkillOutcome
from matchmakinglab.platform.platform import Platform
from matchmakinglab.platform.simulator import Simulator


def _clock() -> float:
    import time

    return time.perf_counter()


def _fmt_team(team: list[Player]) -> str:
    return " & ".join(p.username for p in team)


class SimHarness:
    """Owns the full composition of the simulation run.

    The harness is the single point of contact between the simulation and the
    display layer. Callers only ever observe a :class:`SimSnapshot`, never the
    internals (Platform, Simulator, PlatformState), so those can be refactored
    freely beneath this boundary.
    """

    def __init__(
        self,
        generator: RequestGenerator,
        platform: Platform,
        simulator: Simulator | None = None,
        requests_per_step: int = 10,
        seed: int | None = None,
        clock: Callable[[], float] = _clock,
        outcome_model: MatchOutcomeModel | None = None,
    ) -> None:
        self.generator = generator
        self.platform = platform
        # The platform draws each new player's hidden real ability, so it needs
        # the same seed as the rest of the run — otherwise a seeded simulation
        # would still vary between identical runs.
        platform.use_rng(Random(seed))
        self.simulator = simulator or Simulator(
            seed, outcome_model if outcome_model is not None else TrueSkillOutcome()
        )
        self.state = PlatformState()
        self.requests_per_step = requests_per_step
        self.seed = seed
        self._clock = clock

        self._last_time: float | None = None
        self._sim_seconds = 0.0
        self._tick = 0
        self._total_requests = 0

        self._total_wait_time = 0
        self._total_matched_players = 0

        # Running tally for the favourite win rate, accumulated as matches finish
        # rather than recomputed from the finished list each tick: that list only
        # grows, so a rescan would cost more every tick and be O(n) over the whole
        # run.
        self._decided_matches = 0
        self._favourite_wins = 0

    def _record_match_quality(self, newly_finished: list[FinishedMatch]) -> None:
        """Fold newly finished matches into the favourite win rate.

        Ratings here are the ones from *before* the match was scored, so this must
        be called ahead of `update_player_features`.
        """
        for match in newly_finished:
            winning = sum(
                p.player_features[SKILL_RATING_KEY] for p in match.winning_team
            )
            losing = sum(p.player_features[SKILL_RATING_KEY] for p in match.losing_team)

            # Equal totals mean neither side was the favourite, so the match
            # carries no information about overconfidence and is left out of the
            # rate rather than counted as a loss for one of them.
            if winning != losing:
                self._decided_matches += 1
                if winning > losing:
                    self._favourite_wins += 1

    def _player_quality(self) -> tuple[float, float, float]:
        """Rating accuracy and the estimated/true spreads, over played players.

        One pass, and one population: every measure here is taken over the same
        set of distinct players who have actually played a match. Averaging over
        distinct players rather than over match appearances keeps these consistent
        with each other and with the over-dispersion figures in
        docs/matchmaking-implementations.md, which a per-match weighting would
        quietly disagree with — a busy player would otherwise carry the weight of
        several.

        Returns (rating accuracy, estimated spread, true spread).
        """
        ratings: list[float] = []
        truths: list[float] = []
        for player in self.state.player_database.values():
            if player.wins + player.loses == 0:
                continue
            ratings.append(float(player.player_features[SKILL_RATING_KEY]))
            truths.append(float(player.player_features[TRUE_SKILL_KEY]))

        if not ratings:
            return 0.0, 0.0, 0.0

        n = len(ratings)
        mean_rating = sum(ratings) / n
        mean_truth = sum(truths) / n
        covariance = sum(
            (r - mean_rating) * (t - mean_truth) for r, t in zip(ratings, truths)
        )
        spread_rating = sum((r - mean_rating) ** 2 for r in ratings) ** 0.5
        spread_truth = sum((t - mean_truth) ** 2 for t in truths) ** 0.5

        # Below two players, or with no spread in either quantity, the ratio has
        # no meaning; report 0.0 rather than dividing out a zero.
        accuracy = (
            covariance / (spread_rating * spread_truth)
            if n >= 2 and spread_rating > 0 and spread_truth > 0
            else 0.0
        )

        return (
            accuracy,
            max(ratings) - min(ratings),
            max(truths) - min(truths),
        )

    def step(self) -> SimSnapshot:
        """Advance the simulation one tick and return a snapshot of the result."""
        events: list[str] = []

        new_requests = self.generator.generate_requests(
            self.requests_per_step, self.state.player_database
        )
        self._total_requests += len(new_requests)

        for req in new_requests:
            user = req["user"]
            ping = req["req_features"][LATENCY_KEY]
            region = req["req_features"][REGION_KEY]

            if req["is_new"]:
                events.append(
                    f"generated NEW {user} - skill {BASE_SKILL_RATING}, ping: {ping}, region: {region}"
                )
            else:
                skill = req["req_features"][SKILL_RATING_KEY]
                events.append(
                    f"generated EXISTING {user} - skill {skill}, ping: {ping}, region: {region}"
                )

            self.platform.add_to_matchmaking_queue(
                user, req["req_features"], self.state
            )

        active_before = len(self.state.get_active_games())

        proposals = self.platform.match_players(
            self.state.get_matchmaking_queue(),
            self.platform.strategy,
        )

        self._total_wait_time += sum(
            req.tick_wait_time
            for p in proposals
            for team in (p.team_A, p.team_B)
            for req in team
        )

        self._total_matched_players += sum(
            len(p.team_A) + len(p.team_B) for p in proposals
        )

        avg_wait_time = (
            (self._total_wait_time / self._total_matched_players)
            if self._total_matched_players != 0
            else 0
        )

        # START MATCHES
        self.platform.start_matches(proposals, self.state.get_active_games())

        self.platform.increment_wait_time(self.state.get_matchmaking_queue())

        for match in self.state.get_active_games()[active_before:]:
            events.append(
                f"matched {_fmt_team(match.team_A)} \u2194 {_fmt_team(match.team_B)}"
            )

        # COLLECT FINISHED MATCHES
        newly_finished = self.simulator.simulate_matches(self.state.get_active_games())

        for match in newly_finished:
            events.append(
                f"match finished: {_fmt_team(match.winning_team)} "
                f"vs {_fmt_team(match.losing_team)}"
            )
        self.platform.end_matches(newly_finished, self.state.get_finished_matches())

        # Recorded before the update below, deliberately. Who the favourite was
        # is a question about the ratings as they stood going into the match; read
        # afterwards, the winner has just been boosted and the loser knocked down,
        # so the winner would be the favourite in almost every match and the metric
        # would report the update rule back to itself.
        self._record_match_quality(newly_finished)

        self.platform.update_player_features(newly_finished, self.platform.strategy)

        if newly_finished:
            events.append("ratings updated")

        # GET STATISTICS
        finished = self.state.get_finished_matches()

        if len(finished) != 0:
            avg_match_length = sum([m.match_length for m in finished]) / len(finished)
        else:
            avg_match_length = 0

        rating_accuracy, rating_spread, true_skill_spread = self._player_quality()

        now = self._clock()
        if self._last_time is not None:
            self._sim_seconds += now - self._last_time
        self._last_time = now

        self._tick += 1

        return SimSnapshot(
            population_size=len(self.state.player_database),
            tick=self._tick,
            queue=[r.player.username for r in self.state.get_matchmaking_queue()],
            active_matches=len(self.state.get_active_games()),
            finished_matches=len(self.state.get_finished_matches()),
            sim_seconds=self._sim_seconds,
            request_rate=round(self._total_requests / self._sim_seconds, 1)
            if self._sim_seconds > 0
            else 0.0,
            avg_wait=avg_wait_time,
            avg_match_len=avg_match_length,
            favourite_win_rate=(
                self._favourite_wins / self._decided_matches
                if self._decided_matches
                else 0.0
            ),
            rating_accuracy=rating_accuracy,
            rating_spread=rating_spread,
            true_skill_spread=true_skill_spread,
            event_lines=events,
        )
