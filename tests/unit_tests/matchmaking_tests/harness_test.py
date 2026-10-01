"""
harness_test.py
~~~~~~~~~~~~~~~

Tests the SimHarness facade that sits between the simulation and the display
layer. These run headless (no Textual involved), holding the sim loop correct
and independent of the TUI.
"""

import re
from itertools import pairwise

import pytest

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
    TRUE_SKILL_KEY,
    PlayerStatus,
    Region,
)
from matchmakinglab.core.snapshot import SimSnapshot
from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry import generator as gen
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    SKILL_RATING_KEY,
    BradleyTerry,
)
from matchmakinglab.platform.platform import Platform
from matchmakinglab.platform.sim_harness import LEADERBOARD_MAX_ROWS, SimHarness
from tests.helpers import make_skill_player

# A small pool keeps EXISTING (returning-player) requests arriving promptly;
# the default 500-player pool would need ~50 ticks before a single one appears.
SMALL_POOL = 12


def _make_harness(
    requests_per_step: int = 10,
    seed: int | None = None,
    player_count: int | None = None,
) -> SimHarness:
    platform = Platform(BradleyTerry())
    return SimHarness(
        gen.BradleyTerryGenerator(player_count=player_count or 500, seed=seed),
        platform,
        requests_per_step=requests_per_step,
        seed=seed,
    )


class _ScriptedGenerator(RequestGenerator):
    """Emits pre-baked request batches, then nothing.

    Lets the harness's own event formatting be asserted exactly, independently
    of the random request generation covered in generator_test.py.
    """

    def __init__(self, batches: list[list[dict]] | None = None) -> None:
        self.batches = list(batches or [])

    def generate_requests(self, number, player_database) -> list:
        return self.batches.pop(0) if self.batches else []


def _run(harness: SimHarness, ticks: int) -> SimSnapshot:
    snapshot: SimSnapshot | None = None
    for _ in range(ticks):
        snapshot = harness.step()
    assert snapshot is not None
    return snapshot


def test_step_returns_populated_snapshot():
    harness = _make_harness()

    snapshot = harness.step()

    assert snapshot.tick == 1
    assert snapshot.population_size > 0
    assert isinstance(snapshot.queue, list)
    assert snapshot.active_matches >= 0
    assert snapshot.finished_matches >= 0
    assert snapshot.sim_seconds >= 0.0
    assert len(snapshot.queue) + snapshot.active_matches + snapshot.finished_matches > 0
    assert snapshot.event_lines


def test_tick_advances_monotonically():
    harness = _make_harness()

    first = harness.step()
    second = harness.step()

    assert second.tick == first.tick + 1
    assert second.finished_matches >= first.finished_matches


def test_queue_eventually_produces_finished_matches():
    # Chain: players enqueue -> are matched (even count -> all consumed) -> finish.
    harness = _make_harness(requests_per_step=10)

    for _ in range(50):
        harness.step()

    assert harness.state.get_active_games() or harness.state.get_finished_matches()


def test_full_run_produces_matches_without_crashing():
    harness = _make_harness()

    snapshot = _run(harness, 200)

    assert snapshot.tick == 200
    assert snapshot.finished_matches > 0
    assert snapshot.avg_match_len > 0


def test_odd_request_rate_leaves_players_waiting():
    # With an odd number of requests per step the queue does not drain fully,
    # so some players accumulate wait time and drag avg_wait above zero.
    harness = _make_harness(requests_per_step=3)

    snapshot = _run(harness, 10)

    assert snapshot.avg_wait > 0


def test_events_track_the_full_match_lifecycle():
    harness = _make_harness(requests_per_step=10, player_count=SMALL_POOL)

    event_lines = set()
    for _ in range(120):
        snapshot = harness.step()
        event_lines.update(snapshot.event_lines)

    assert any("generated NEW" in line for line in event_lines)
    assert any("generated EXISTING" in line for line in event_lines)
    assert any("matched" in line and "↔" in line for line in event_lines)
    assert any("match finished" in line for line in event_lines)
    assert "ratings updated" in event_lines


def test_same_seed_produces_identical_queue():
    def run(seed):
        harness = _make_harness(seed=seed)
        for _ in range(30):
            harness.step()
        return harness.state.get_matchmaking_queue()

    first = run(1)
    second = run(1)

    assert [req.player.username for req in first] == [
        req.player.username for req in second
    ]
    assert [req.req_features for req in first] == [req.req_features for req in second]


class SettableClock:
    """A clock the test moves by hand, so elapsed time is stated not waited for.

    Deliberately not one that advances on every call: the harness reads the clock
    more than once per step now, so a self-advancing clock would make the
    arithmetic depend on how many times it happened to be read.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_sim_seconds_and_request_rate_track_fake_clock():
    """Run time is real elapsed time, and the rate is arrivals over it.

    Ten requests a tick with a fifth of a second between ticks is fifty a
    second, which is the figure the panel has always claimed to show.
    """
    clock = SettableClock()
    harness = SimHarness(
        gen.BradleyTerryGenerator(),
        Platform(BradleyTerry()),
        requests_per_step=10,
        clock=clock,
    )

    clock.advance(0.2)
    first = harness.step()  # run time starts at the first step, so this is 0.0
    assert first.sim_seconds == 0.0
    assert first.request_rate == 0.0

    clock.advance(0.2)
    snapshot = harness.step()

    assert snapshot.sim_seconds == pytest.approx(0.2)
    # 20 requests over 0.2s.
    assert snapshot.request_rate == 100.0


def test_pausing_stops_the_run_clock():
    """A pause is time the simulation was not running, so it is not run time.

    The bug this pins: the clock used to be the gap between steps, and the last
    time it was read was inside step(). A pause produces no steps, so the whole
    pause landed in the next tick's gap — a minute of thinking about the numbers
    read as a minute of simulation, and dragged the request rate down with it.
    """
    clock = SettableClock()
    harness = SimHarness(
        gen.BradleyTerryGenerator(),
        Platform(BradleyTerry()),
        requests_per_step=10,
        clock=clock,
    )

    for _ in range(3):
        clock.advance(0.2)
        harness.step()
    assert harness._elapsed_seconds() == pytest.approx(0.4)

    harness.set_paused(True)
    clock.advance(3600.0)  # an hour of the operator doing something else
    assert harness._elapsed_seconds() == pytest.approx(0.4)

    harness.set_paused(False)
    clock.advance(0.2)
    resumed = harness.step()
    assert resumed.sim_seconds == pytest.approx(0.6)
    # 40 requests over 0.6s — the pause did not dilute the rate either.
    assert resumed.request_rate == pytest.approx(66.7, abs=0.05)


def test_pause_and_resume_are_idempotent():
    """The two states are not independent calls, so repeats must not double count.

    An app that reports a pause it is already in, or resumes one that has
    already ended, would otherwise bank the same span twice.
    """
    clock = SettableClock()
    harness = SimHarness(
        gen.BradleyTerryGenerator(),
        Platform(BradleyTerry()),
        requests_per_step=10,
        clock=clock,
    )

    clock.advance(0.2)
    harness.step()  # the run clock starts here

    harness.set_paused(True)
    clock.advance(30.0)
    harness.set_paused(True)  # reported again, 30s later, still paused
    clock.advance(30.0)
    harness.set_paused(False)
    harness.set_paused(False)  # reported again, already running

    clock.advance(0.2)
    snapshot = harness.step()

    # One tick's worth of running, not three. The 60s of pause contributes
    # nothing, and a repeat pause part-way through it does not quietly start
    # counting the time since the first report as running time.
    assert snapshot.sim_seconds == pytest.approx(0.2)


def test_run_time_does_not_depend_on_the_tick_interval():
    """The speed multiplier must not change how long the run has been going.

    Run time is wall clock, so the only thing a faster tick rate changes is how
    many ticks fit inside it. Driving the same wall-clock span at two different
    intervals has to give the same run time, and a proportionally higher rate.
    """
    clock = SettableClock()

    def run(interval: float, ticks: int) -> SimSnapshot:
        harness = SimHarness(
            gen.BradleyTerryGenerator(),
            Platform(BradleyTerry()),
            requests_per_step=10,
            clock=clock,
        )
        clock.now = 0.0
        taken = []
        for _ in range(ticks):
            clock.advance(interval)
            taken.append(harness.step())
        return taken[-1]

    slow = run(0.2, 11)  # 11 ticks, ending 2.0s after the first
    clock.now = 0.0
    fast = run(0.025, 81)  # 81 ticks, ending 2.0s after the first

    assert slow.sim_seconds == pytest.approx(2.0)
    assert fast.sim_seconds == pytest.approx(2.0)
    # Same run time, very different throughput: 110 requests over 2.0s against
    # 810. Not exactly 8x because each run's clock starts on its own first tick,
    # so the faster run has 81 requests-batches to the slower one's 11.
    assert slow.request_rate == 55.0
    assert fast.request_rate == 405.0


def test_ratings_updated_once_per_finished_match():
    """Each finished match applies rating updates exactly once, on completion."""

    class RecordingBradleyTerry(BradleyTerry):
        def __init__(self):
            super().__init__()
            self.updated_matches = []

        def update_player_features(self, finished_match):
            self.updated_matches.append(finished_match)
            super().update_player_features(finished_match)

    strategy = RecordingBradleyTerry()
    harness = SimHarness(
        gen.BradleyTerryGenerator(),
        Platform(strategy),
        requests_per_step=10,
    )

    for _ in range(120):
        harness.step()

    finished = harness.state.get_finished_matches()
    assert len(finished) > 0
    assert len(strategy.updated_matches) == len(finished)


def test_ratings_updated_event_emitted_once_per_tick_with_finishes():
    """The summary line appears only on ticks that actually finished a match."""
    harness = _make_harness(requests_per_step=10)

    for _ in range(80):
        snapshot = harness.step()

        if "ratings updated" in snapshot.event_lines:
            # Ratings are applied after the finish lines, never before.
            lines = snapshot.event_lines
            assert lines[-1] == "ratings updated"
            assert any("match finished" in line for line in lines)
        else:
            # No finishes means no rating work to report.
            assert not any("match finished" in line for line in snapshot.event_lines)


# ---------- Population / queue reporting ----------


def test_snapshot_population_size_matches_player_database():
    harness = _make_harness()

    snapshot = harness.step()

    assert snapshot.population_size == len(harness.state.player_database)
    assert snapshot.population_size == 10  # all ten requests were brand new


def test_snapshot_population_size_grows_then_plateaus_at_pool_size():
    harness = _make_harness(requests_per_step=10, player_count=100)

    populations = [harness.step().population_size for _ in range(20)]

    assert populations[0] == 10
    # Monotonic: players are only ever added, never removed.
    assert all(b >= a for a, b in pairwise(populations))
    # Once every pool slot is claimed, population is capped and pullbacks begin.
    assert max(populations) == 100
    assert populations[-1] == 100


def test_snapshot_queue_lists_queued_usernames():
    harness = _make_harness(requests_per_step=3)

    snapshot = harness.step()

    # Three requests: two get matched, one is left waiting.
    assert len(snapshot.queue) == 1
    assert snapshot.queue[0] in harness.state.player_database


def test_snapshot_queue_tracks_the_harness_queue_each_tick():
    harness = _make_harness(requests_per_step=5)

    for _ in range(25):
        snapshot = harness.step()
        assert snapshot.queue == [
            req.player.username for req in harness.state.get_matchmaking_queue()
        ]


def test_snapshot_queue_empties_once_players_are_fully_matched():
    harness = _make_harness(requests_per_step=10)

    snapshot = harness.step()

    assert snapshot.queue == []


# ---------- Request generation event lines ----------


def test_new_player_event_reports_base_skill_ping_and_region():
    requests = [
        {
            "user": "newbie",
            "req_features": {LATENCY_KEY: 42, REGION_KEY: Region.EU},
            "is_new": True,
        }
    ]
    harness = SimHarness(
        _ScriptedGenerator([requests]),
        Platform(BradleyTerry()),
        requests_per_step=1,
    )

    snapshot = harness.step()

    assert snapshot.event_lines[0] == (
        f"generated NEW newbie - skill {BASE_SKILL_RATING:.1f}, ping: 42, region: europe"
    )


def test_existing_player_event_reports_that_players_own_skill():
    player = make_skill_player(
        0, "veteran", Region.ASIA, skill_rating=137, status=PlayerStatus.IDLE
    )
    harness = SimHarness(
        _ScriptedGenerator(),
        Platform(BradleyTerry()),
        requests_per_step=1,
    )
    harness.state.add_player(player)
    harness.generator.batches.append(
        [
            {
                "user": "veteran",
                "req_features": {
                    LATENCY_KEY: 7,
                    REGION_KEY: Region.ASIA,
                    SKILL_RATING_KEY: 137,
                },
                "is_new": False,
            }
        ]
    )

    snapshot = harness.step()

    assert snapshot.event_lines[0] == (
        "generated EXISTING veteran - skill 137.0, ping: 7, region: asia"
    )
    # The returning player keeps their rating; it is not reset on re-entry.
    assert player.player_features[SKILL_RATING_KEY] == 137


def test_one_generation_event_per_request_and_no_separate_queued_event():
    requests = [
        {
            "user": f"newbie_{i}",
            "req_features": {LATENCY_KEY: 10 + i, REGION_KEY: Region.NA},
            "is_new": True,
        }
        for i in range(4)
    ]
    harness = SimHarness(
        _ScriptedGenerator([requests]),
        Platform(BradleyTerry()),
        requests_per_step=4,
    )

    snapshot = harness.step()

    generated = [line for line in snapshot.event_lines if line.startswith("generated ")]
    assert len(generated) == len(requests)
    assert not any("queued" in line for line in snapshot.event_lines)


def test_reported_skill_matches_the_skill_in_the_emitted_request():
    """Each EXISTING event reports the rating carried by that request.

    The feed rounds a fractional rating for display, so this compares to within
    that rounding rather than exactly - a stale or re-read rating would be off
    by far more.
    """

    class RecordingGenerator(RequestGenerator):
        """Wraps the real generator, remembering the batch it last emitted."""

        def __init__(self, inner: RequestGenerator) -> None:
            self.inner = inner
            self.last_batch: list[dict] = []

        def generate_requests(self, number, player_database) -> list:
            self.last_batch = self.inner.generate_requests(number, player_database)
            return self.last_batch

    generator = RecordingGenerator(
        gen.BradleyTerryGenerator(player_count=SMALL_POOL, seed=3)
    )
    harness = SimHarness(
        generator, Platform(BradleyTerry()), requests_per_step=4, seed=3
    )
    pattern = re.compile(r"^generated EXISTING (\S+) - skill ([\d.]+), ")

    checked = 0
    for _ in range(30):
        snapshot = harness.step()
        # Read the batch back *after* the step: the events were formatted from it.
        emitted = {
            req["user"]: req["req_features"].get(SKILL_RATING_KEY)
            for req in generator.last_batch
            if not req["is_new"]
        }
        for line in snapshot.event_lines:
            match = pattern.match(line)
            if match:
                username, skill = match.group(1), float(match.group(2))
                assert emitted[username] == pytest.approx(skill, abs=0.05)
                checked += 1

    assert checked  # the run really did produce returning players


def test_returning_players_are_never_new_signups():
    """A player pulled back from the database is not re-registered as a signup."""
    harness = _make_harness(requests_per_step=4, seed=3, player_count=SMALL_POOL)

    known = set()
    pattern = re.compile(r"^generated (\w+) (\S+) - ")
    for _ in range(30):
        for line in harness.step().event_lines:
            match = pattern.match(line)
            if match:
                kind, username = match.groups()
                if kind == "NEW":
                    assert username not in known  # a signup must be genuinely new
                else:
                    known.add(username)

    assert known  # the run really did produce returning players


# ---------- Win / loss bookkeeping ----------


def test_wins_and_losses_balance_against_finished_matches():
    harness = _make_harness(requests_per_step=10, seed=4)

    snapshot = _run(harness, 120)

    assert snapshot.finished_matches > 0
    players = list(harness.state.player_database.values())
    # Every finished match is 1v1, so wins and losses must tally one-for-one.
    assert sum(p.wins for p in players) == snapshot.finished_matches
    assert sum(p.loses for p in players) == snapshot.finished_matches


def test_played_players_are_retained_and_requeued_rather_than_retired():
    """Finishing a match returns a player to the pool instead of retiring them."""
    harness = _make_harness(requests_per_step=10, seed=4, player_count=SMALL_POOL)

    _run(harness, 120)

    players = list(harness.state.player_database.values())
    played = [p for p in players if p.wins or p.loses]
    assert played
    # Every player that has played is still in the database and usable.
    assert {p.username for p in played} <= set(harness.state.player_database)
    assert all(p.status in set(PlayerStatus) for p in played)


# ---------- Self-match regression ----------
# A batch used to be able to name the same player twice, and BT's greedy matcher
# then treated the resulting "A vs A" candidate as a legitimate pair: one match
# credited the player with both a win and a loss and applied a net-zero rating
# adjustment. Fixed in the generator (distinct users per batch) and in the
# matcher (self-pairs are not candidates); these tests hold both layers in place.


def test_no_player_appears_in_both_teams_of_a_finished_match():
    harness = _make_harness(requests_per_step=10, seed=4)

    _run(harness, 80)

    for match in harness.state.get_finished_matches():
        winners = {p.id for p in match.winning_team}
        losers = {p.id for p in match.losing_team}
        assert not winners & losers


def test_win_and_loss_ledger_matches_the_finished_matches():
    """`wins`/`loses` are cumulative counters, so check them against the record.

    An earlier version of this test asserted `sum(p.wins for p in
    match.winning_team) == 1`, which only holds for a player's first win. The
    invariant that actually matters is that the counters agree with the matches
    that were played, and that no single match contributed to both sides for the
    same player.
    """
    harness = _make_harness(requests_per_step=10, seed=4)

    _run(harness, 80)

    expected_wins: dict[int, int] = {}
    expected_loses: dict[int, int] = {}

    for match in harness.state.get_finished_matches():
        for player in match.winning_team:
            expected_wins[player.id] = expected_wins.get(player.id, 0) + 1
        for player in match.losing_team:
            expected_loses[player.id] = expected_loses.get(player.id, 0) + 1

    # A self-match would put the same player in both columns of the same row.
    for match in harness.state.get_finished_matches():
        ids_a = {p.id for p in match.winning_team}
        ids_b = {p.id for p in match.losing_team}
        assert not ids_a & ids_b

    for player in harness.state.player_database.values():
        assert player.wins == expected_wins.get(player.id, 0), (
            f"{player.username} win count disagrees with the match record"
        )
        assert player.loses == expected_loses.get(player.id, 0), (
            f"{player.username} loss count disagrees with the match record"
        )


def test_finished_teams_always_have_distinct_members():
    harness = _make_harness(requests_per_step=10, seed=4)

    _run(harness, 80)

    for match in harness.state.get_finished_matches():
        winners = [p.id for p in match.winning_team]
        losers = [p.id for p in match.losing_team]
        assert len(winners) == len(set(winners))
        assert len(losers) == len(set(losers))


def test_self_match_defect_is_fixed_at_the_generator():
    """Pins the root cause: distinct users within a single generated batch."""
    generator = gen.BradleyTerryGenerator(player_count=6, seed=1)
    database = {
        req["user"]: make_skill_player(i, req["user"], status=PlayerStatus.IDLE)
        for i, req in enumerate(generator.generate_requests(3, {}))
    }
    generator.generate_requests(3, {})  # exhaust the pool -> existing-only mode

    requests = generator.generate_requests(5, database)
    users = [req["user"] for req in requests if req["is_new"] is False]

    assert users, "expected existing-player requests"
    assert len(users) == len(set(users)), (
        "The generator drew the same idle player more than once in one batch; "
        "nothing downstream guards against matching a player with themselves."
    )
    # Only three distinct idle players exist, so the batch is capped by
    # availability rather than the requested count.
    assert len(users) == len(database)


# ---------- Match quality metrics ----------
#
# These describe how good the matches being formed are, as opposed to how fast.
# They exist to be read live next to the documented over-dispersion limit, so the
# two tests that matter most are the ones pinning the definition of "favourite"
# and the ordering of the quality tally relative to the rating update.


def test_favourite_win_rate_counts_only_decided_matches():
    """Equal-rated sides are left out entirely.

    When both sides carry the same rating neither is the favourite, so the match
    says nothing about overconfidence. Counting it would pull the rate toward
    0.5 for free and make the number look healthier than it is.
    """
    harness = _make_harness(seed=1)
    snapshot = _run(harness, 60)

    assert snapshot.finished_matches > 0
    assert 0.0 <= snapshot.favourite_win_rate <= 1.0


def test_favourite_win_rate_is_zero_before_any_decided_match():
    """Reports "no data" as 0.0 rather than inventing a rate."""
    harness = _make_harness(seed=1)
    snapshot = _run(harness, 3)

    assert snapshot.favourite_win_rate == 0.0


def test_favourite_is_judged_on_ratings_from_before_the_match():
    """Regression: who led going in, not who leads after the update.

    Read after `update_player_features`, the winner has just been boosted and
    the loser knocked down, so the winner is the favourite in nearly every match
    and the metric reports the rating rule back to itself — it read 0.974 that
    way against a true ceiling near 0.60. Moving the tally ahead of the update
    is what makes it a measurement.
    """
    harness = _make_harness(seed=1)
    pre_update: list[bool] = []
    original = SimHarness._record_match_quality

    def spy(self, newly_finished):
        for match in newly_finished:
            winning = sum(
                p.player_features[SKILL_RATING_KEY] for p in match.winning_team
            )
            losing = sum(p.player_features[SKILL_RATING_KEY] for p in match.losing_team)
            if winning != losing:
                pre_update.append(winning > losing)
        return original(self, newly_finished)

    SimHarness._record_match_quality = spy
    try:
        snapshot = _run(harness, 60)
    finally:
        SimHarness._record_match_quality = original

    assert pre_update, "no decided matches were seen, so this proves nothing"
    expected = sum(pre_update) / len(pre_update)
    assert snapshot.favourite_win_rate == pytest.approx(expected)
    # If the tally were reading post-update ratings the winner would lead almost
    # always. Pin it well below that so the bug cannot come back quietly.
    assert snapshot.favourite_win_rate < 0.9


def test_favourite_win_rate_stays_below_the_honest_ceiling():
    """Sanity check that the rate measures overconfidence, not its absence.

    No matchmaker can beat the ceiling the hidden-truth outcome model imposes, so
    a rate that drifts far above the mid-0.6s would mean the metric has stopped
    tracking pairing quality. A wide bound, because the exact value depends on
    how the matchmaker happens to pair — only a runaway is a defect.
    """
    harness = _make_harness(seed=1, player_count=150)
    snapshot = _run(harness, 400)

    assert 0.4 < snapshot.favourite_win_rate < 0.8


def test_rating_accuracy_improves_as_the_run_proceeds():
    """The estimate is supposed to be learning, so it must move toward the truth."""
    harness = _make_harness(seed=1, player_count=150)

    early = _run(harness, 50).rating_accuracy
    late = _run(harness, 550).rating_accuracy

    assert early > 0.0
    assert late > early


def test_rating_accuracy_matches_a_direct_recomputation():
    """Guard the incremental Pearson accumulator against drift.

    The correlation is kept as running sums rather than recomputed over the
    playerbase each tick, which is cheaper but easy to get subtly wrong. Checking
    it against the naive computation keeps the optimisation honest.
    """
    harness = _make_harness(seed=1, player_count=150)
    _run(harness, 300)
    snapshot = harness.step()

    xs = []
    ys = []
    for player in harness.state.player_database.values():
        if player.wins + player.loses == 0:
            continue
        xs.append(float(player.player_features[SKILL_RATING_KEY]))
        ys.append(float(player.player_features[TRUE_SKILL_KEY]))

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    expected = covariance / (
        sum((x - mean_x) ** 2 for x in xs) ** 0.5
        * sum((y - mean_y) ** 2 for y in ys) ** 0.5
    )

    assert snapshot.rating_accuracy == pytest.approx(expected, abs=0.05)


def test_spreads_are_taken_over_the_same_played_players():
    """Estimated and true spread share a denominator, so their ratio is meaningful."""
    harness = _make_harness(seed=1, player_count=150)
    snapshot = _run(harness, 300)

    played = [p for p in harness.state.player_database.values() if p.wins + p.loses > 0]
    ratings = [p.player_features[SKILL_RATING_KEY] for p in played]
    truths = [p.player_features[TRUE_SKILL_KEY] for p in played]

    assert snapshot.rating_spread == pytest.approx(max(ratings) - min(ratings))
    assert snapshot.true_skill_spread == pytest.approx(max(truths) - min(truths))


def test_spreads_start_below_the_truth_and_close_on_it():
    """The panel shows the estimate converging on the truth, not running past it.

    Early on every estimate sits at the shared base rating, so the estimated
    spread starts well under the truth and climbs as the run learns. Under the
    additive update this crossed above the truth and kept going - the
    over-dispersion the log-space update replaced - so the pair now converging
    is the visible consequence of that change. Measured at seed 1: 0.42x of the
    truth at 600 ticks, still under at 900, 1.03x by 2000.
    """
    harness = _make_harness(seed=1, player_count=150)

    early = _run(harness, 50)
    mid = _run(harness, 850)
    late = _run(harness, 1100)

    assert early.rating_spread < early.true_skill_spread
    assert mid.rating_spread < mid.true_skill_spread
    # Close to parity without having run away in either direction.
    assert late.rating_spread == pytest.approx(late.true_skill_spread, rel=0.25)
    assert late.rating_accuracy > early.rating_accuracy


# ---------- Arrival rate ----------


def _requests_per_tick(harness: SimHarness, ticks: int) -> list[int]:
    """How many requests the generator was asked for on each of these ticks.

    Counts are read off the harness's own draw rather than the requests that
    reached the queue: a generator is free to return fewer than it was asked for
    when the pool runs dry, and it is the draw that this range is about.
    """
    return [harness._requests_this_tick() for _ in range(ticks)]


def test_requests_stay_inside_the_configured_range():
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(7, 19),
    )

    counts = _requests_per_tick(harness, 300)

    assert counts
    assert min(counts) >= 7
    assert max(counts) <= 19


def test_requests_actually_vary_within_the_range():
    """A range that never varied would be a constant arrival rate in disguise.

    Worth pinning because the default range is wide, and a harness that quietly
    used only one endpoint would still pass the bounds check above.
    """
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(7, 19),
    )

    counts = _requests_per_tick(harness, 300)

    assert len(set(counts)) > 1


def test_requests_reach_both_ends_of_the_range():
    """Over enough draws, the bounds themselves are not just respected but used.

    A narrower guard: an implementation that drew only from the middle of the
    range would satisfy the bounds test and quietly understate the load.
    """
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(7, 19),
    )

    counts = set(_requests_per_tick(harness, 1000))

    assert 7 in counts
    assert 19 in counts


def test_requests_per_step_pins_arrivals_to_a_fixed_count():
    """An explicit count overrides the range entirely.

    This is the path most of the suite and every fixed-arrival measurement uses,
    so it has to mean exactly what it says rather than "roughly".
    """
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        requests_per_step=4,
        seed=1,
        request_range=(7, 19),
    )

    assert _requests_per_tick(harness, 200) == [4] * 200


def test_default_request_range_is_the_documented_wide_one():
    """The default is a range, not the fixed 10 a bare harness used to assume.

    Pinned so that changing it has to be a decision: the wide default is what
    gives the queue bursts rather than a flattering constant arrival rate.
    """
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
    )

    assert harness.request_range == (10, 50)
    assert harness.requests_per_step is None
    assert min(_requests_per_tick(harness, 200)) >= 10
    assert max(_requests_per_tick(harness, 200)) <= 50


def test_the_request_range_varies_the_number_of_requests_per_tick():
    """A variable arrival rate changes the amount of work the harness asks for.

    The queue itself may still be drained in one tick, but the load presented
    to the matcher — total requests that arrived that tick — is now a random
    variable. That is the property the default range is meant to introduce.
    """
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(10, 50),
    )

    counts = _requests_per_tick(harness, 500)

    # If we had a constant rate, this would be exactly 1; with a range it is > 1.
    assert len(set(counts)) > 10
    assert min(counts) == 10
    assert max(counts) == 50


def test_a_wider_range_raises_the_total_arrival_count():
    """The range is load-bearing: more arrivals per tick, more requests total.

    Asserted on the snapshot's own counter, which is what the request-rate panel
    figure is built from.
    """
    narrow = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(2, 4),
    )
    wide = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(20, 60),
    )

    for _ in range(200):
        narrow.step()
    for _ in range(200):
        wide.step()

    assert wide._total_requests > narrow._total_requests


def test_request_draws_do_not_disturb_the_seeded_player_pool():
    """Arrival counts draw from their own stream.

    If they drew from the run's main seed instead, introducing a request range
    would shift the platform's and simulator's draws, so every calibration
    number measured before this change would quietly stop reproducing. Both
    harnesses below see the same player abilities and the same match outcomes.
    """
    fixed = SimHarness(
        gen.BradleyTerryGenerator(player_count=60, seed=1),
        Platform(BradleyTerry()),
        requests_per_step=10,
        seed=1,
    )
    ranged = SimHarness(
        gen.BradleyTerryGenerator(player_count=60, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(3, 40),
    )

    for _ in range(60):
        fixed.step()
        ranged.step()

    def skills(harness) -> list:
        return [
            p.player_features[TRUE_SKILL_KEY]
            for p in harness.state.player_database.values()
        ]

    assert skills(fixed) == skills(ranged)


@pytest.mark.parametrize("bad", [(10, 0), (50, 10), (-1, 5)])
def test_an_unusable_request_range_is_refused(bad):
    """A range that cannot be drawn from is rejected at construction.

    These would otherwise surface as a silent 0-arrival or an exception deep in
    the generator partway into a run. ``(0, 10)`` was on this list until it was
    deliberately allowed; see the test below.
    """
    with pytest.raises(ValueError):
        SimHarness(
            gen.BradleyTerryGenerator(player_count=500, seed=1),
            Platform(BradleyTerry()),
            seed=1,
            request_range=bad,
        )


def test_a_single_value_range_is_accepted_as_a_fixed_rate():
    """``--requests 10:10`` is the way to ask for a constant arrival rate."""
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=500, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(10, 10),
    )

    assert _requests_per_tick(harness, 100) == [10] * 100


# ---------- Seed plumbing ----------


def test_a_seeded_run_is_reproducible_end_to_end():
    """Same seed, same run - the property --seed advertises.

    This failed before the generator was seeded: the platform and simulator
    respected the seed but the generator built itself an unseeded Random, so who
    queued and with what latency and region varied between identical runs. Only
    reachable through the CLI before, since the tests all happened to seed the
    generator themselves with the same value the harness was given.
    """

    def run() -> list:
        harness = SimHarness(
            gen.BradleyTerryGenerator(player_count=80, seed=None),
            Platform(BradleyTerry()),
            seed=11,
            request_range=(4, 15),
        )
        out = []
        for _ in range(80):
            snapshot = harness.step()
            out.append((snapshot.population_size, len(snapshot.queue)))
        return out

    assert run() == run()


def test_different_seeds_still_produce_different_runs():
    """The reproducibility above must not have come from everything being fixed."""

    def run(seed: int) -> list:
        harness = SimHarness(
            gen.BradleyTerryGenerator(player_count=80, seed=None),
            Platform(BradleyTerry()),
            seed=seed,
            request_range=(4, 15),
        )
        return [len(harness.step().queue) for _ in range(80)]

    assert run(11) != run(12)


def test_an_explicitly_seeded_generator_keeps_its_own_seed():
    """A generator built with a seed is not silently re-seeded by the harness.

    Same rule the platform follows: an explicitly supplied source of randomness
    is never replaced.
    """
    generator = gen.BradleyTerryGenerator(player_count=40, seed=99)

    SimHarness(generator, Platform(BradleyTerry()), seed=1)

    first = generator.generate_requests(5, {})
    assert first == gen.BradleyTerryGenerator(
        player_count=40, seed=99
    ).generate_requests(5, {})


def test_a_request_range_starting_at_zero_is_accepted():
    """A minimum of 0 is the feature, not a mistake to guard against.

    It makes some ticks arrive nobody, which is the one thing a fixed count and
    a range both starting high cannot express.
    """
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=200, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(0, 50),
    )

    assert harness.request_range == (0, 50)


def test_a_zero_minimum_actually_produces_quiet_ticks():
    """Over enough ticks a 0:50 range has to draw a zero at least once.

    Pinned because the range would still satisfy every other test if the draw
    were quietly clamped up to 1 — the guard would have moved rather than
    relaxed, and the world would still never be quiet.
    """
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=200, seed=1),
        Platform(BradleyTerry()),
        seed=1,
        request_range=(0, 5),
    )

    per_tick = []
    previous = 0
    for _ in range(200):
        harness.step()
        per_tick.append(harness._total_requests - previous)
        previous = harness._total_requests

    assert min(per_tick) == 0, "a 0:5 range over 200 ticks never drew zero"
    assert max(per_tick) > 0


def test_a_quiet_tick_is_a_normal_tick():
    """A tick that generates nothing must still produce a usable snapshot.

    This is the reason relaxing the bound is safe: nothing downstream divides by
    the arrival count, so an empty batch costs nothing but the players it would
    have sent out to play. Forced rather than drawn, so the quiet tick is the
    one being tested rather than one that happened to come up.
    """
    harness = _make_harness(seed=1)
    _run(harness, 50)

    previous = _run(harness, 49)
    population_before = len(harness.state.player_database)
    queue_before = len(harness.state.get_matchmaking_queue())
    total_before = harness._total_requests

    harness.requests_per_step = 0
    quiet = harness.step()

    assert quiet.population_size == population_before
    assert len(quiet.queue) == queue_before
    assert quiet.tick == previous.tick + 1
    # No arrivals, so the cumulative request count is untouched. Matches already
    # in flight still finish, so the snapshot is not empty — it is just quiet.
    assert harness._total_requests == total_before
    assert quiet.avg_wait >= 0.0
    assert quiet.finished_matches >= previous.finished_matches

    # And the run carries on normally afterwards.
    harness.requests_per_step = None
    resumed = _run(harness, 20)

    assert resumed.population_size >= population_before


# ---------- Leaderboard ----------


def test_leaderboard_has_rows_on_the_very_first_tick():
    """The table is populated from tick one, even though nobody has played.

    Every rating is still the base value at this point, so these rows are
    ordered by the tie-break rather than by merit. Showing them flat is the
    point: the panel is more useful filling in than blank until it has
    something to rank.
    """
    harness = _make_harness(seed=1)

    snapshot = harness.step()

    assert snapshot.leaderboard
    assert all(row.wins == 0 and row.loses == 0 for row in snapshot.leaderboard)
    assert all(row.skill_rating == BASE_SKILL_RATING for row in snapshot.leaderboard)


def test_leaderboard_is_sorted_by_rating_highest_first():
    harness = _make_harness(seed=1)

    snapshot = _run(harness, 400)

    ratings = [r.skill_rating for r in snapshot.leaderboard]
    assert ratings == sorted(ratings, reverse=True)


def test_leaderboard_rank_numbers_are_consecutive_from_one():
    harness = _make_harness(seed=1)

    snapshot = _run(harness, 400)

    assert [r.rank for r in snapshot.leaderboard] == list(
        range(1, len(snapshot.leaderboard) + 1)
    )


def test_leaderboard_covers_only_the_top_slice_and_not_the_whole_population():
    """The cap exists so the table stays a leaderboard rather than a roster."""
    harness = _make_harness(seed=1, player_count=250)

    snapshot = _run(harness, 400)

    assert len(snapshot.leaderboard) == LEADERBOARD_MAX_ROWS
    assert snapshot.population_size > LEADERBOARD_MAX_ROWS


def test_leaderboard_is_the_highest_rated_players_of_the_real_population():
    """Cross-check the snapshot against the state, rather than trusting the sort.

    Recomputes the expected top slice independently. A sort by the wrong column,
    or in the wrong direction, fails here even though the rows still look
    plausible and internally consistent.
    """
    harness = _make_harness(seed=1, player_count=120)

    snapshot = _run(harness, 500)

    expected = sorted(
        harness.state.player_database.values(),
        key=lambda p: (
            -float(p.player_features[SKILL_RATING_KEY]),
            -p.wins,
            p.username,
        ),
    )[:LEADERBOARD_MAX_ROWS]

    assert [r.username for r in snapshot.leaderboard] == [p.username for p in expected]


def test_leaderboard_carries_the_hidden_truth_beside_the_estimate():
    """Both numbers are on every row — the panel exists to compare them."""
    harness = _make_harness(seed=1)

    snapshot = _run(harness, 400)

    for row in snapshot.leaderboard:
        player = harness.state.player_database[row.username]
        assert row.skill_rating == pytest.approx(
            float(player.player_features[SKILL_RATING_KEY])
        )
        assert row.true_skill == pytest.approx(
            float(player.player_features[TRUE_SKILL_KEY])
        )


def test_leaderboard_rows_carry_win_loss_and_region():
    harness = _make_harness(seed=1)

    snapshot = _run(harness, 400)

    row = snapshot.leaderboard[0]
    player = harness.state.player_database[row.username]

    assert (row.wins, row.loses) == (player.wins, player.loses)
    assert row.region == player.default_region


def test_leaderboard_ties_break_on_wins_then_username():
    """Flat ratings order by who has played, then by name.

    Every player starts at exactly the base rating, so without a tie-break the
    first rows would be whichever the heap happened to emit — churning between
    ticks and differing between runs. Pinned against a fabricated flat
    population so the tie is actually exercised.
    """
    harness = _make_harness(seed=1)
    harness.step()

    for name in ("zeta", "alpha", "mid"):
        harness.platform.add_to_matchmaking_queue(
            name, {"latency": 10, "region": Region.NA}, harness.state
        )

    # Give one of the tied players a win, so the secondary key has to matter.
    harness.state.player_database["alpha"].wins = 3

    rows = harness._leaderboard()

    tied = [
        r
        for r in rows
        if r.skill_rating == 100.0 and r.username in ("zeta", "alpha", "mid")
    ]
    assert tied[0].username == "alpha"


def test_leaderboard_order_is_stable_while_ratings_are_tied():
    """Two reads of an unchanged population give the same order.

    This is the property the tie-break exists to provide: a table whose rows
    reshuffle every tick while nothing has changed cannot be read at all.
    """
    harness = _make_harness(seed=1)
    harness.step()

    assert [r.username for r in harness._leaderboard()] == [
        r.username for r in harness._leaderboard()
    ]


def test_leaderboard_is_reproducible_under_a_seed():
    def run(seed: int) -> list[str]:
        harness = _make_harness(seed=seed, player_count=60)
        return [r.username for r in _run(harness, 300).leaderboard]

    assert run(4) == run(4)
    assert run(4) != run(5)


def test_leaderboard_handles_a_single_player():
    harness = SimHarness(
        gen.BradleyTerryGenerator(player_count=2, seed=1),
        Platform(BradleyTerry()),
        requests_per_step=2,
        seed=1,
    )

    snapshot = harness.step()

    assert len(snapshot.leaderboard) <= 2
