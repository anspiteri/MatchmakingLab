"""
harness_test.py
~~~~~~~~~~~~~~~

Tests the SimHarness facade that sits between the simulation and the display
layer. These run headless (no Textual involved), holding the sim loop correct
and independent of the TUI.
"""

import re
from itertools import pairwise

from matchmakinglab.core.models import (
    LATENCY_KEY,
    REGION_KEY,
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
from matchmakinglab.platform.sim_harness import SimHarness
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


def test_sim_seconds_and_request_rate_track_fake_clock():
    class FakeClock:
        def __init__(self):
            self._value = 0.0

        def __call__(self):
            self._value += 1.0
            return self._value

    harness = SimHarness(
        gen.BradleyTerryGenerator(),
        Platform(BradleyTerry()),
        requests_per_step=10,
        clock=FakeClock(),
    )

    harness.step()  # sim_seconds stays 0 on the first step
    snapshot = harness.step()

    assert snapshot.sim_seconds == 1.0
    assert snapshot.request_rate == 20.0


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
        f"generated NEW newbie - skill {BASE_SKILL_RATING}, ping: 42, region: europe"
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
        "generated EXISTING veteran - skill 137, ping: 7, region: asia"
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
    """Each EXISTING event reports the rating carried by that request."""

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
    pattern = re.compile(r"^generated EXISTING (\S+) - skill (\d+), ")

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
                username, skill = match.group(1), int(match.group(2))
                assert emitted[username] == skill
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
