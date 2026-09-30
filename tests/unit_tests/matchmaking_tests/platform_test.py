"""
platform_test.py
~~~~~~~~~~~~~~~~

Tests the simulation infrastructure: PlatformState storage, the Platform
orchestration layer and the Simulator's match clock. These run headless and
exercise the layers below the SimHarness boundary directly.
"""

import random

from matchmakinglab.core.models import (
    TRUE_SKILL_KEY,
    ActiveMatch,
    FinishedMatch,
    MatchProposal,
    MatchRequest,
    PlayerStatus,
    Region,
)
from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry
from matchmakinglab.platform.platform import (
    MAX_TRUE_SKILL,
    MIN_TRUE_SKILL,
    Platform,
)
from matchmakinglab.platform.simulator import (
    POINTS_TO_WIN,
    Simulator,
    _simulate_match,
)
from tests.helpers import make_player, make_skill_player


def _req_features() -> dict:
    return {"latency": 20, "region": Region.NA}


def _make_platform() -> tuple[Platform, PlatformState]:
    return Platform(BradleyTerry()), PlatformState()


# ---------- PlatformState ----------


def test_state_add_and_get_player():
    state = PlatformState()
    player = make_player(0, "alice")

    assert state.add_player(player) is player
    assert state.get_player("alice") is player
    assert state.get_player("missing") is None


def test_state_queue_access_is_live():
    state = PlatformState()
    req = MatchRequest(make_player(0, "alice"))

    state.enqueue_match_req(req)
    assert state.get_matchmaking_queue() == [req]

    state.get_matchmaking_queue().append(MatchRequest(make_player(1, "bob")))
    assert len(state.get_matchmaking_queue()) == 2


def test_state_active_and_finished_matches():
    state = PlatformState()
    active = ActiveMatch(match_cost=1)
    finished = FinishedMatch(match_length=5)

    assert state.get_active_games() == []
    assert state.get_finished_matches() == []

    state.add_active_match(active)
    state.enqueue_finished_match(finished)

    assert state.get_active_games() == [active]
    assert state.get_finished_matches() == [finished]


# ---------- Platform ----------


def test_platform_exposes_strategy():
    strategy = BradleyTerry()
    platform = Platform(strategy)
    assert platform.strategy is strategy


def test_add_to_matchmaking_queue_creates_player_with_features():
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)

    player = state.get_player("alice")
    assert player is not None
    assert player.player_features  # populated by strategy.setup_player_features

    requests = state.get_matchmaking_queue()
    assert len(requests) == 1
    assert requests[0].player is player
    assert requests[0].req_features["latency"] == 20


def test_add_to_matchmaking_queue_reuses_existing_player():
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)
    player = state.get_player("alice")
    platform.add_to_matchmaking_queue("alice", _req_features(), state)

    assert state.get_player("alice") is player

    requests = state.get_matchmaking_queue()
    assert len(requests) == 2
    assert all(req.player is player for req in requests)


def test_add_to_matchmaking_queue_assigns_distinct_ids():
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)
    platform.add_to_matchmaking_queue("bob", _req_features(), state)

    alice = state.get_player("alice")
    bob = state.get_player("bob")

    assert alice is not None
    assert bob is not None
    assert alice.id != bob.id


def test_add_to_matchmaking_queue_sets_status_queuing():
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)
    player = state.get_player("alice")
    assert player is not None
    assert player.status == PlayerStatus.QUEUING

    # Re-queueing an existing player keeps the QUEUING status.
    platform.add_to_matchmaking_queue("alice", _req_features(), state)
    assert player.status == PlayerStatus.QUEUING


def test_new_player_starts_with_empty_win_loss_record():
    """A freshly signed-up player has no recorded wins or losses."""
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)

    player = state.get_player("alice")
    assert player is not None
    assert player.wins == 0
    assert player.loses == 0


def test_new_player_default_region_comes_from_request_features():
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue(
        "alice", {"latency": 25, "region": Region.EU}, state
    )

    player = state.get_player("alice")
    assert player is not None
    assert player.default_region == Region.EU


def test_new_player_default_region_falls_back_to_oceania():
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue("alice", {"latency": 25}, state)

    player = state.get_player("alice")
    assert player is not None
    assert player.default_region == Region.OCEANIA


def test_match_players_drains_queue_in_place():
    platform, state = _make_platform()
    for name in ("alice", "bob"):
        platform.add_to_matchmaking_queue(name, _req_features(), state)

    queue = state.get_matchmaking_queue()
    matches = platform.match_players(queue, platform.strategy)

    assert queue == []  # the shared queue object, now drained
    assert len(matches) == 1
    assert state.get_active_games() == []  # matching does not start matches


def test_match_players_leaves_unmatched_requests_queued():
    platform, state = _make_platform()
    for name in ("alice", "bob", "carol"):
        platform.add_to_matchmaking_queue(name, _req_features(), state)

    queue = state.get_matchmaking_queue()
    matches = platform.match_players(queue, platform.strategy)

    assert len(matches) == 1
    assert len(queue) == 1  # odd count leaves one request behind
    remaining = queue[0].player.username
    assert remaining in {"alice", "bob", "carol"}


def test_start_matches_converts_proposals_to_active_matches():
    platform, _ = _make_platform()

    alice = make_player(0, "alice")
    bob = make_player(1, "bob")
    proposal = MatchProposal(
        match_cost=5,
        team_A=[MatchRequest(alice, {})],
        team_B=[MatchRequest(bob, {})],
    )

    active: list[ActiveMatch] = []
    platform.start_matches([proposal], active)

    assert len(active) == 1
    assert active[0].match_cost == 5
    assert active[0].team_A == [alice]
    assert active[0].team_B == [bob]
    assert active[0].tick_match_length == 0
    assert alice.status == PlayerStatus.PLAYING
    assert bob.status == PlayerStatus.PLAYING


def test_end_matches_sets_players_idle_and_appends_finished():
    platform, _ = _make_platform()
    alice = make_player(0, "alice", status=PlayerStatus.PLAYING)
    bob = make_player(1, "bob", status=PlayerStatus.PLAYING)
    finished = FinishedMatch(match_length=7, winning_team=[alice], losing_team=[bob])
    global_finished: list[FinishedMatch] = []

    platform.end_matches([finished], global_finished)

    assert alice.status == PlayerStatus.IDLE
    assert bob.status == PlayerStatus.IDLE
    assert global_finished == [finished]


def test_end_matches_records_a_win_for_the_winning_team():
    platform, _ = _make_platform()
    alice = make_player(0, "alice", status=PlayerStatus.PLAYING)
    bob = make_player(1, "bob", status=PlayerStatus.PLAYING)
    finished = FinishedMatch(match_length=7, winning_team=[alice], losing_team=[bob])

    platform.end_matches([finished], [])

    assert alice.wins == 1
    assert alice.loses == 0
    assert bob.wins == 0
    assert bob.loses == 1


def test_end_matches_records_one_result_per_player_in_multi_player_teams():
    platform, _ = _make_platform()
    winners = [make_player(i, f"w{i}", status=PlayerStatus.PLAYING) for i in range(3)]
    losers = [
        make_player(3 + i, f"l{i}", status=PlayerStatus.PLAYING) for i in range(2)
    ]
    finished = FinishedMatch(match_length=7, winning_team=winners, losing_team=losers)

    platform.end_matches([finished], [])

    assert all(p.wins == 1 and p.loses == 0 for p in winners)
    assert all(p.wins == 0 and p.loses == 1 for p in losers)
    assert all(p.status == PlayerStatus.IDLE for p in winners + losers)


def test_end_matches_accumulates_records_across_repeated_matches():
    platform, _ = _make_platform()
    alice = make_player(0, "alice", status=PlayerStatus.PLAYING)
    bob = make_player(1, "bob", status=PlayerStatus.PLAYING)

    platform.end_matches(
        [FinishedMatch(5, winning_team=[alice], losing_team=[bob])], []
    )
    platform.end_matches(
        [FinishedMatch(5, winning_team=[alice], losing_team=[bob])], []
    )
    platform.end_matches(
        [FinishedMatch(5, winning_team=[bob], losing_team=[alice])], []
    )

    assert (alice.wins, alice.loses) == (2, 1)
    assert (bob.wins, bob.loses) == (1, 2)


def test_end_matches_with_no_finished_matches_is_a_no_op():
    platform, _ = _make_platform()
    alice = make_player(0, "alice", status=PlayerStatus.PLAYING)
    global_finished: list[FinishedMatch] = []

    platform.end_matches([], global_finished)

    assert global_finished == []
    assert (alice.wins, alice.loses) == (0, 0)
    assert alice.status == PlayerStatus.PLAYING  # still in progress


def test_full_player_state_cycle_via_simulator():
    platform, state = _make_platform()
    for name in ("alice", "bob"):
        platform.add_to_matchmaking_queue(name, _req_features(), state)

    queue = state.get_matchmaking_queue()
    assert all(req.player.status == PlayerStatus.QUEUING for req in queue)

    active: list[ActiveMatch] = []
    platform.start_matches(platform.match_players(queue, platform.strategy), active)

    players = [p for m in active for p in m.team_A + m.team_B]
    assert players
    assert all(p.status == PlayerStatus.PLAYING for p in players)

    simulator = Simulator(seed=1)
    finished: list[FinishedMatch] = []
    for _ in range(200):
        finished = simulator.simulate_matches(active)
        if finished:
            break

    global_finished: list[FinishedMatch] = []
    platform.end_matches(finished, global_finished)

    assert all(p.status == PlayerStatus.IDLE for p in players)
    assert global_finished == finished
    # Each finished match credits one win and one loss across its two teams.
    assert sum(p.wins for p in players) == len(finished)
    assert sum(p.loses for p in players) == len(finished)


def test_update_player_features_delegates_to_strategy(mocker):
    platform, _ = _make_platform()
    finished = FinishedMatch(match_length=5)
    strategy_mock = mocker.Mock()

    platform.update_player_features([finished], strategy_mock)

    strategy_mock.update_player_features.assert_called_once_with(finished)


def test_increment_wait_time():
    platform, _ = _make_platform()
    req = MatchRequest(make_player(0, "alice"))

    platform.increment_wait_time([req])

    assert req.tick_wait_time == 1


# ---------- Simulator ----------
#
# A match is a race to POINTS_TO_WIN: each tick every active match plays a
# round, the round winner is drawn from the outcome model's probability, and the
# match ends when a side reaches the target. Two properties fall out of that and
# are asserted throughout — a match cannot overrun the bound, and no side is
# favoured by the order it happens to be listed in.


def _run_to_completion(
    active: list[ActiveMatch], simulator: Simulator, limit: int = 100
) -> list[FinishedMatch]:
    """Tick until everything finishes (or the guard trips)."""
    finished: list[FinishedMatch] = []
    for _ in range(limit):
        finished.extend(simulator.simulate_matches(active))
        if not active:
            break
    return finished


def test_simulate_matches_advances_every_clock_by_one_round():
    simulator = Simulator(seed=1)
    active = [ActiveMatch(match_cost=1), ActiveMatch(match_cost=2)]

    simulator.simulate_matches(active)

    assert [m.tick_match_length for m in active] == [1, 1]
    # One round means exactly one point is credited, and the match is still live.
    assert sum(m.score_A + m.score_B for m in active) == 2
    assert all(m.score_A < POINTS_TO_WIN and m.score_B < POINTS_TO_WIN for m in active)


def test_simulate_matches_only_removes_finished_matches():
    simulator = Simulator(seed=2)
    # One match has already reached the target, the other has barely started.
    # (A match merely one point short would not reliably finish: if the other
    # side takes that round, neither side is at the target.)
    done = ActiveMatch(match_cost=1, score_A=POINTS_TO_WIN)
    barely_started = ActiveMatch(match_cost=2, score_B=1)
    active = [done, barely_started]

    finished = simulator.simulate_matches(active)

    assert len(finished) == 1
    assert [m.match_cost for m in active] == [2]


def test_match_ends_when_a_side_reaches_the_points_target():
    simulator = Simulator(seed=3)
    alice = make_skill_player(0, "alice")
    bob = make_skill_player(1, "bob")
    # Evenly matched, so the race is genuinely undecided before the final round.
    match = ActiveMatch(
        match_cost=1,
        team_A=[alice],
        team_B=[bob],
        score_A=POINTS_TO_WIN - 1,
        score_B=POINTS_TO_WIN - 1,
    )
    active = [match]

    finished = simulator.simulate_matches(active)

    assert len(finished) == 1
    # Whoever took the last point wins, whichever side that was.
    result = finished[0]
    if result.winning_team == [alice]:
        assert result.losing_team == [bob]
    else:
        assert result.winning_team == [bob]
        assert result.losing_team == [alice]


def test_every_finished_match_credits_one_whole_side():
    """A result is a clean win for one side, never a split or a draw.

    The race to a points target cannot tie, so a draw state would have nothing
    to represent; this pins that the two sides are always distinct.
    """
    simulator = Simulator(seed=4)
    alice = make_skill_player(0, "alice")
    bob = make_skill_player(1, "bob")

    active = [ActiveMatch(match_cost=1, team_A=[alice], team_B=[bob])]
    finished = _run_to_completion(active, simulator)

    assert len(finished) == 1
    result = finished[0]
    sides = {
        tuple(p.id for p in result.winning_team),
        tuple(p.id for p in result.losing_team),
    }
    assert sides == {(alice.id,), (bob.id,)}


def test_a_match_always_finishes_and_never_overruns_its_bound():
    """The race is self-bounding, so no duration cap is needed."""
    simulator = Simulator(seed=5)
    # Evenly matched: the longest possible contest.
    active = [ActiveMatch(match_cost=1)]

    finished = _run_to_completion(active, simulator)

    assert len(finished) == 1
    assert active == []
    assert 1 <= finished[0].match_length <= 2 * POINTS_TO_WIN - 1


def test_either_side_can_win_a_repeated_pairing():
    """Regression test for the old placeholder, which always credited team A.

    Run the same pairing many times: if results depended on which side a player
    was listed on, one side would win every time.
    """
    alice = make_skill_player(0, "alice")
    bob = make_skill_player(1, "bob")

    winners = set()
    for seed in range(60):
        simulator = Simulator(seed=seed)
        match = ActiveMatch(match_cost=1, team_A=[alice], team_B=[bob])
        finished = _run_to_completion([match], simulator)
        assert len(finished) == 1
        winners.add(tuple(p.id for p in finished[0].winning_team))

    assert len(winners) == 2, "one side won every time — a positional bias remains"


def test_the_stronger_player_wins_more_often():
    """Outcome must depend on ability, not on chance alone."""
    strong = make_skill_player(0, "strong", true_skill=160, skill_rating=100)
    weak = make_skill_player(1, "weak", true_skill=40, skill_rating=100)

    wins = 0
    trials = 400
    for seed in range(trials):
        simulator = Simulator(seed=seed)
        match = ActiveMatch(match_cost=1, team_A=[strong], team_B=[weak])
        finished = _run_to_completion([match], simulator)
        if finished[0].winning_team[0].id == strong.id:
            wins += 1

    assert wins > trials * 0.6, f"strong side won only {wins}/{trials} matches"


def test_match_play_never_mutates_a_players_hidden_skill():
    """The truth the outcomes are drawn from must stay fixed.

    If the simulation edited its own ground truth it would be marking its own
    homework, and every metric derived from it would be meaningless.
    """
    alice = make_skill_player(0, "alice", true_skill=140)
    bob = make_skill_player(1, "bob", true_skill=60)

    before = {
        alice.id: alice.player_features[TRUE_SKILL_KEY],
        bob.id: bob.player_features[TRUE_SKILL_KEY],
    }
    simulator = Simulator(seed=6)
    _run_to_completion(
        [ActiveMatch(match_cost=1, team_A=[alice], team_B=[bob])], simulator
    )

    for player in (alice, bob):
        assert player.player_features[TRUE_SKILL_KEY] == before[player.id]


def test_same_seed_produces_the_same_winners():
    def run(seed: int) -> list[tuple[int, ...]]:
        alice = make_skill_player(0, "alice", true_skill=140)
        bob = make_skill_player(1, "bob", true_skill=60)
        simulator = Simulator(seed=seed)
        finished = _run_to_completion(
            [ActiveMatch(match_cost=1, team_A=[alice], team_B=[bob])], simulator
        )
        return [(tuple(p.id for p in m.winning_team), m.match_length) for m in finished]

    assert run(7) == run(7)


def test_simulate_match_reports_the_side_that_reached_the_target():
    alice = make_skill_player(0, "alice")
    bob = make_skill_player(1, "bob")
    match = ActiveMatch(
        match_cost=1,
        team_A=[alice],
        team_B=[bob],
        tick_match_length=4,
        score_A=POINTS_TO_WIN,
        score_B=1,
    )

    finished = _simulate_match(match)

    assert finished.match_length == 4
    assert finished.winning_team == [alice]
    assert finished.losing_team == [bob]


# ---------- Hidden true skill ----------
#
# `true_skill` is the simulated player's real, hidden ability: drawn once at
# creation, never updated, and the thing match outcomes are decided from. It is
# what makes a matchmaker's estimate measurable at all — if outcomes were decided
# from the estimate, the matchmaker would be graded against its own opinion.
#
# The platform owns this key rather than the strategy, because it models the
# player and not any one matchmaking approach.


def test_new_player_is_seeded_with_a_hidden_true_skill():
    platform = Platform(BradleyTerry(), rng=random.Random(1))
    state = PlatformState()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)

    player = state.get_player("alice")
    assert player is not None
    assert TRUE_SKILL_KEY in player.player_features
    assert MIN_TRUE_SKILL <= player.player_features[TRUE_SKILL_KEY] <= MAX_TRUE_SKILL


def test_hidden_true_skill_does_not_replace_the_strategy_rating():
    """The hidden value is additive — the strategy still seeds its own key."""
    platform = Platform(BradleyTerry(), rng=random.Random(1))
    state = PlatformState()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)

    player = state.get_player("alice")
    assert player is not None
    assert player.player_features["skill_rating"] == 100
    assert TRUE_SKILL_KEY in player.player_features


def test_new_players_get_genuinely_different_true_skills():
    """Guards against a degenerate all-equal population.

    If every simulated player shared one ability there would be nothing for a
    matchmaker to discover, and every approach would score identically. A silent
    flattening like that would make the whole lab look broken in a way that is
    easy to mistake for a matchmaking bug.
    """
    platform = Platform(BradleyTerry(), rng=random.Random(7))
    state = PlatformState()

    for i in range(40):
        platform.add_to_matchmaking_queue(f"player_{i}", _req_features(), state)

    values = {p.player_features[TRUE_SKILL_KEY] for p in state.player_database.values()}

    assert len(values) > 1
    # A healthy population uses most of the configured range rather than
    # clustering on one or two values.
    assert len(values) > 20


def test_true_skill_is_drawn_once_and_never_changes_on_requeue():
    platform = Platform(BradleyTerry(), rng=random.Random(1))
    state = PlatformState()

    platform.add_to_matchmaking_queue("alice", _req_features(), state)
    player = state.get_player("alice")
    assert player is not None
    original = player.player_features[TRUE_SKILL_KEY]

    platform.add_to_matchmaking_queue("alice", _req_features(), state)

    assert player.player_features[TRUE_SKILL_KEY] == original


def test_platform_without_an_rng_stays_deterministic():
    """The default `Platform(BradleyTerry())` shape must keep working.

    Many tests construct the platform with no rng because they are asserting on
    matchmaking mechanics, not on simulated player quality. A platform that
    raised or required a seeded rng would break all of them.
    """
    platform = Platform(BradleyTerry())
    state = PlatformState()

    for i in range(5):
        platform.add_to_matchmaking_queue(f"player_{i}", _req_features(), state)

    values = {p.player_features[TRUE_SKILL_KEY] for p in state.player_database.values()}
    assert len(values) == 1


def test_seeded_rng_produces_reproducible_true_skills():
    def draw(seed: int) -> list[int]:
        platform = Platform(BradleyTerry(), rng=random.Random(seed))
        state = PlatformState()
        for i in range(10):
            platform.add_to_matchmaking_queue(f"player_{i}", _req_features(), state)
        return [
            p.player_features[TRUE_SKILL_KEY]
            for _, p in sorted(state.player_database.items())
        ]

    assert draw(42) == draw(42)
    assert draw(42) != draw(43)
