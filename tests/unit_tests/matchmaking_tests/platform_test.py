"""
platform_test.py
~~~~~~~~~~~~~~~~

Tests the simulation infrastructure: PlatformState storage, the Platform
orchestration layer and the Simulator's match clock. These run headless and
exercise the layers below the SimHarness boundary directly.
"""


from matchmakinglab.core.models import (
    ActiveMatch,
    FinishedMatch,
    MatchProposal,
    MatchRequest,
    Player,
    PlayerStatus,
    Region,
)
from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry
from matchmakinglab.platform.platform import Platform
from matchmakinglab.platform.simulator import Simulator, _simulate_match


def _req_features() -> dict:
    return {"latency": 20, "region": Region.NA}


def _make_platform() -> tuple[Platform, PlatformState]:
    return Platform(BradleyTerry()), PlatformState()


# ---------- PlatformState ----------


def test_state_add_and_get_player():
    state = PlatformState()
    player = Player(0, "alice", Region.OCEANIA)

    assert state.add_player(player) is player
    assert state.get_player("alice") is player
    assert state.get_player("missing") is None


def test_state_queue_access_is_live():
    state = PlatformState()
    req = MatchRequest(Player(0, "alice", Region.OCEANIA))

    state.enqueue_match_req(req)
    assert state.get_matchmaking_queue() == [req]

    state.get_matchmaking_queue().append(MatchRequest(Player(1, "bob", Region.OCEANIA)))
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


def test_new_player_default_region_comes_from_request_features():
    platform, state = _make_platform()

    platform.add_to_matchmaking_queue("alice", {"latency": 25, "region": Region.EU}, state)

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

    alice = Player(0, "alice", Region.OCEANIA)
    bob = Player(1, "bob", Region.OCEANIA)
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
    alice = Player(0, "alice", Region.OCEANIA, status=PlayerStatus.PLAYING)
    bob = Player(1, "bob", Region.OCEANIA, status=PlayerStatus.PLAYING)
    finished = FinishedMatch(match_length=7, winning_team=[alice], losing_team=[bob])
    global_finished: list[FinishedMatch] = []

    platform.end_matches([finished], global_finished)

    assert alice.status == PlayerStatus.IDLE
    assert bob.status == PlayerStatus.IDLE
    assert global_finished == [finished]


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


def test_update_player_features_delegates_to_strategy(mocker):
    platform, _ = _make_platform()
    finished = FinishedMatch(match_length=5)
    strategy_mock = mocker.Mock()

    platform.update_player_features([finished], strategy_mock)

    strategy_mock.update_player_features.assert_called_once_with(finished)


def test_increment_wait_time():
    platform, _ = _make_platform()
    req = MatchRequest(Player(0, "alice", Region.OCEANIA))

    platform.increment_wait_time([req])

    assert req.tick_wait_time == 1


# ---------- Simulator ----------


def test_simulate_matches_advances_all_clocks(mocker):
    simulator = Simulator()
    active = [
        ActiveMatch(match_cost=1),
        ActiveMatch(match_cost=2),
    ]

    # Threshold above any current clock value -> nothing finishes.
    mocker.patch.object(simulator._rng, "randint", return_value=60)
    finished = simulator.simulate_matches(active)

    assert [m.tick_match_length for m in active] == [1, 1]
    assert len(active) == 2
    assert finished == []


def test_simulate_matches_completes_long_enough_matches(mocker):
    simulator = Simulator()
    active = [ActiveMatch(match_cost=1, tick_match_length=6)]

    # Low threshold -> the single match crosses it and finishes.
    mocker.patch.object(simulator._rng, "randint", return_value=5)
    finished = simulator.simulate_matches(active)

    assert len(active) == 0
    assert len(finished) == 1
    assert finished[0].match_length == 7  # clock advanced to 7 before completion


def test_simulate_match_preserves_teams():
    alice = Player(0, "alice", Region.OCEANIA)
    bob = Player(1, "bob", Region.OCEANIA)
    match = ActiveMatch(
        match_cost=1, team_A=[alice], team_B=[bob], tick_match_length=9
    )

    finished = _simulate_match(match)

    assert finished.match_length == 9
    assert finished.winning_team == [alice]
    assert finished.losing_team == [bob]