from collections.abc import Callable
from heapq import nsmallest
from random import Random

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
    TRUE_SKILL_KEY,
    FinishedMatch,
    LeaderboardEntry,
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


# How many requests arrive per tick, as an inclusive range. Wider than a fixed
# rate on purpose, so the per-player match load varies over a run rather than
# arriving on a metronome. Measured caveat: the greedy matcher drains whatever
# it is given within the tick, so this varies *load* and not queue depth — the
# queue still sits near empty. See docs/architecture.md.
DEFAULT_REQUEST_RANGE = (10, 50)

# Rows the leaderboard panel holds. The panel scrolls, so this is a display cap
# rather than a correctness one: keeping the 1000th-ranked player reachable by
# scrolling is cheaper than ranking the whole population into a list nobody reads.
# Measured 0.12ms to select at 500 players and 0.56ms at 5000, against a ~1.9ms
# tick, so it does not need caching.
LEADERBOARD_MAX_ROWS = 100


def _validate_request_range(request_range: tuple[int, int]) -> tuple[int, int]:
    """Check an arrival range, returning it unchanged.

    Inclusive on both ends, so ``(10, 50)`` can draw any of 41 counts.

    A minimum of 0 is allowed, and is the point of a range over a fixed count:
    it makes some ticks quiet. An empty batch generates nothing, which costs
    nothing downstream — no division by the arrival count anywhere — so the only
    thing it changes is how many players each gets to play. ``0:50`` is a world
    with lulls in it; ``50:50`` is a metronome.
    """
    low, high = request_range
    if low < 0:
        raise ValueError(f"Request range minimum cannot be negative, got {low}")
    if high < low:
        raise ValueError(f"Request range maximum {high} is below its minimum {low}")
    return low, high


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
        requests_per_step: int | None = None,
        seed: int | None = None,
        clock: Callable[[], float] = _clock,
        outcome_model: MatchOutcomeModel | None = None,
        request_range: tuple[int, int] = DEFAULT_REQUEST_RANGE,
    ) -> None:
        self.generator = generator
        self.platform = platform
        # The platform draws each new player's hidden real ability, so it needs
        # the same seed as the rest of the run — otherwise a seeded simulation
        # would still vary between identical runs.
        platform.use_rng(Random(seed))
        # The generator draws who queues and what their latency and region are.
        # Seeding it here too is what makes --seed actually reproducible: without
        # this a run still varied between invocations given the same seed, because
        # the generator was the one component building itself an unseeded Random.
        generator.use_rng(Random(seed))
        self.simulator = simulator or Simulator(
            seed, outcome_model if outcome_model is not None else TrueSkillOutcome()
        )
        self.state = PlatformState()
        # An explicit requests_per_step pins arrivals to a fixed count; otherwise
        # each tick draws from request_range. Fixed arrivals are what most tests
        # want, and --requests N:N reaches the same behaviour from the CLI.
        self.requests_per_step = requests_per_step
        self.request_range = _validate_request_range(request_range)
        self.seed = seed
        self._clock = clock
        # Arrival counts draw from their own stream rather than the seed itself,
        # so introducing an arrival rate does not shift the draws the platform and
        # simulator already make — a run's player abilities and match outcomes stay
        # comparable as the request range is varied.
        self._request_rng = Random(seed) if seed is None else Random(seed + 1)

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

        self._last_snapshot: SimSnapshot | None = None

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

    def _leaderboard(self) -> list[LeaderboardEntry]:
        """Rank the population for the leaderboard panel.

        Ordered by estimated rating, then wins, then username. The last two keys
        are not decoration: every player starts at exactly the base rating, so
        without a total order the top rows would depend on heap order and change
        between runs of the same seed — a table that reshuffles every tick while
        nothing has happened cannot be read at all. Username last also makes the
        order independent of dictionary and insertion order.

        Ranks number the displayed rows, so they read 1..100 rather than skipping
        to whatever position in the population those players hold.
        """
        ranked = nsmallest(
            LEADERBOARD_MAX_ROWS,
            self.state.player_database.values(),
            key=lambda p: (
                -float(p.player_features[SKILL_RATING_KEY]),
                -p.wins,
                p.username,
            ),
        )

        return [
            LeaderboardEntry(
                rank=position,
                username=player.username,
                skill_rating=float(player.player_features[SKILL_RATING_KEY]),
                true_skill=float(player.player_features[TRUE_SKILL_KEY]),
                wins=player.wins,
                loses=player.loses,
                region=player.default_region,
            )
            for position, player in enumerate(ranked, start=1)
        ]

    def _requests_this_tick(self) -> int:
        """How many requests arrive this tick.

        Drawn here rather than in the generator: arrival rate is a property of
        the simulated world rather than of any one matchmaker, so every strategy
        gets it without its generator knowing, and generate_requests stays
        honest about its "give me exactly this many" contract.
        """
        if self.requests_per_step is not None:
            return self.requests_per_step
        low, high = self.request_range
        return self._request_rng.randint(low, high)

    def step(self) -> SimSnapshot:
        """Advance the simulation one tick and return a snapshot of the result."""
        events: list[str] = []

        new_requests = self.generator.generate_requests(
            self._requests_this_tick(), self.state.player_database
        )
        self._total_requests += len(new_requests)

        for req in new_requests:
            user = req["user"]
            ping = req["req_features"][LATENCY_KEY]
            region = req["req_features"][REGION_KEY]

            if req["is_new"]:
                events.append(
                    f"generated NEW {user} - skill {BASE_SKILL_RATING:.1f}, ping: {ping}, region: {region}"
                )
            else:
                skill = req["req_features"][SKILL_RATING_KEY]
                events.append(
                    f"generated EXISTING {user} - skill {skill:.1f}, ping: {ping}, region: {region}"
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

        snapshot = SimSnapshot(
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
            leaderboard=self._leaderboard(),
        )

        # Kept so a caller holding the harness can read back the newest tick
        # without taking a second one and perturbing the run.
        self._last_snapshot = snapshot

        return snapshot
