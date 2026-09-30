from dataclasses import dataclass, field


@dataclass
class SimSnapshot:
    """A read-only view of the simulation after one step.

    This is the contract between the simulation and the display layer. It only
    exposes stable, derived facts (counts, feed events, wall-clock sim time) so
    the UI never needs to reach into Platform/Simulator internals directly.

    The `favourite_win_rate`, `rating_accuracy` and spread fields are match
    *quality* measures rather than throughput: they describe how good the matches
    being formed are, not how fast they are being formed. See `SimHarness` for how
    they are accumulated.
    """

    population_size: int = 0
    tick: int = 0
    queue: list[str] = field(default_factory=list)
    active_matches: int = 0
    finished_matches: int = 0
    sim_seconds: float = 0.0
    request_rate: float = 0.0
    mean_quality: float = 0.0
    avg_wait: float = 0.0
    avg_match_len: float = 0.0
    #: Share of decided matches won by the higher-rated side. A matchmaker that is
    #: genuinely uncertain should sit near 0.5; well above it is overconfidence.
    #: 0.0 means no decided matches yet, not "the favourite always loses".
    favourite_win_rate: float = 0.0
    #: Correlation between estimated rating and hidden true skill across played
    #: players: how accurate the strategy's model of the playerbase is.
    rating_accuracy: float = 0.0
    #: Spread of estimated ratings across played players. The ratio of this to
    #: `true_skill_spread` is the documented over-dispersion measure.
    rating_spread: float = 0.0
    #: Spread of the hidden truth, over the same played players — the yardstick
    #: the estimate should be measured against.
    true_skill_spread: float = 0.0
    event_lines: list[str] = field(default_factory=list)
