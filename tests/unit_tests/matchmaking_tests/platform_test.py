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
    player = Player(0, "alice", {})

    assert state.add_player(player) is player
    assert state.get_player("alice") is player
    assert state.get_player("missing") is None


def test_state_queue_access_is_live():
    state = PlatformState()
    req = MatchRequest(Player(0, "alice", {}))

    state.enqueue_match_req(req)
    assert state.get_matchmaking_queue() == [req]

    state.get_matchmaking_queue().append(MatchRequest(Player(1, "bob", {})))
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

    assert state.get_player("alice").id != state.get_player("bob").id


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

    alice = Player(0, "alice", {})
    bob = Player(1, "bob", {})
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


def test_update_player_features_delegates_to_strategy(mocker):
    platform, _ = _make_platform()
    finished = FinishedMatch(match_length=5)
    strategy_mock = mocker.Mock()

    platform.update_player_features([finished], strategy_mock)

    strategy_mock.update_player_features.assert_called_once_with(finished)


def test_increment_wait_time():
    platform, _ = _make_platform()
    req = MatchRequest(Player(0, "alice", {}))

    platform.increment_wait_time([req])

    assert req.tick_wait_time == 1


# ---------- Simulator ----------


def test_simulate_matches_advances_all_clocks(mocker):
    simulator = Simulator()
    active = [
        ActiveMatch(match_cost=1),
        ActiveMatch(match_cost=2),
    ]
    finished: list[FinishedMatch] = []

    # Threshold above any current clock value -> nothing finishes.
    mocker.patch("matchmakinglab.platform.simulator.random.randint", return_value=60)
    simulator.simulate_matches(active, finished)

    assert [m.tick_match_length for m in active] == [1, 1]
    assert len(active) == 2
    assert finished == []


def test_simulate_matches_completes_long_enough_matches(mocker):
    simulator = Simulator()
    active = [ActiveMatch(match_cost=1, tick_match_length=6)]
    finished: list[FinishedMatch] = []

    # Low threshold -> the single match crosses it and finishes.
    mocker.patch("matchmakinglab.platform.simulator.random.randint", return_value=5)
    simulator.simulate_matches(active, finished)

    assert len(active) == 0
    assert len(finished) == 1
    assert finished[0].match_length == 7  # clock advanced to 7 before completion


def test_simulate_match_preserves_teams():
    alice = Player(0, "alice", {})
    bob = Player(1, "bob", {})
    match = ActiveMatch(
        match_cost=1, team_A=[alice], team_B=[bob], tick_match_length=9
    )

    finished = _simulate_match(match)

    assert finished.match_length == 9
    assert finished.winning_team == [alice]
    assert finished.losing_team == [bob]