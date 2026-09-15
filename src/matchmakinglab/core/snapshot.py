from dataclasses import dataclass, field


@dataclass
class SimSnapshot:
    """A read-only view of the simulation after one step.

    This is the contract between the simulation and the display layer. It only
    exposes stable, derived facts (counts, feed events, wall-clock sim time) so
    the UI never needs to reach into Platform/Simulator internals directly.
    """

    tick: int = 0
    queued: int = 0
    active_matches: int = 0
    finished_matches: int = 0
    sim_seconds: float = 0.0
    request_rate: float = 0.0
    mean_quality: float = 0.0
    avg_wait: float = 0.0
    avg_match_len: float = 0.0
    event_lines: list[str] = field(default_factory=list)
