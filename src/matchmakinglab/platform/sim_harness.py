from collections.abc import Callable

from matchmakinglab.core.models import Player
from matchmakinglab.core.snapshot import SimSnapshot
from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers.base_generator import RequestGenerator
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
    ) -> None:
        self.generator = generator
        self.platform = platform
        self.simulator = simulator or Simulator()
        self.state = PlatformState()
        self.requests_per_step = requests_per_step
        self.seed = seed
        self._clock = clock

        self._last_time: float | None = None
        self._sim_seconds = 0.0
        self._tick = 0
        self._total_requests = 0

    def step(self) -> SimSnapshot:
        """Advance the simulation one tick and return a snapshot of the result."""
        events: list[str] = []

        new_requests = self.generator.generate_requests(self.requests_per_step)
        self._total_requests += len(new_requests)

        for req in new_requests:
            user = req["user"]
            events.append(f"generated player {user}")
            self.platform.add_to_matchmaking_queue(user, req["req_features"], self.state)
            events.append(f"queued player {user}")

        active_before = len(self.state.get_active_games())

        proposals = self.platform.match_players(
            self.state.get_matchmaking_queue(),
            self.platform.strategy,
        )

        self.platform.start_matches(proposals, self.state.get_active_games())
        self.platform.update_player_features(
            self.state.get_finished_matches(), self.platform.strategy
        )
        self.platform.increment_wait_time(self.state.get_matchmaking_queue())

        for match in self.state.get_active_games()[active_before:]:
            events.append(
                f"matched {_fmt_team(match.team_A)} \u2194 {_fmt_team(match.team_B)}"
            )

        finished_before = len(self.state.get_finished_matches())

        self.simulator.simulate_matches(
            self.state.get_active_games(), self.state.get_finished_matches()
        )

        finished = self.state.get_finished_matches()[finished_before:]
        for match in finished:
            events.append(
                f"match finished: {_fmt_team(match.winning_team)} "
                f"vs {_fmt_team(match.losing_team)}"
            )
        if finished:
            events.append("ratings updated")

        now = self._clock()
        if self._last_time is not None:
            self._sim_seconds += now - self._last_time
        self._last_time = now

        self._tick += 1

        return SimSnapshot(
            tick=self._tick,
            queued=len(self.state.get_matchmaking_queue()),
            active_matches=len(self.state.get_active_games()),
            finished_matches=len(self.state.get_finished_matches()),
            sim_seconds=self._sim_seconds,
            request_rate=round(self._total_requests / self._sim_seconds, 1)
            if self._sim_seconds > 0
            else 0.0,
            event_lines=events,
        )
