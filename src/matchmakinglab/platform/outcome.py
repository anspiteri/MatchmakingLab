"""Decides who wins a simulated match.

A match outcome model answers one question: given two teams, what is the
probability that team A takes the round? Keeping this behind an interface means
the simulator can be driven by the population's hidden real ability (the honest
case, and the default) or by a strategy's own estimate (cheaper, and useful for
isolating the rating system's behaviour from the rest of the loop).

Both implementations use the same Bradley-Terry form the strategy already uses
for pairing, so a probability here means the same thing as a probability in the
match cost function.
"""

from abc import ABC, abstractmethod

from matchmakinglab.core.models import TRUE_SKILL_KEY, Player


class MatchOutcomeModel(ABC):
    """Supplies the probability that ``team_a`` wins a round against ``team_b``."""

    @abstractmethod
    def win_probability(self, team_a: list[Player], team_b: list[Player]) -> float:
        """Return P(team_a wins a single round), in [0, 1].

        Implementations must be symmetric in the sense that swapping the teams
        gives the complementary probability, so no side is favoured merely by
        being listed first.
        """


def _team_strength(team: list[Player], key: str) -> float:
    """Sum a team's members on ``key``, rejecting any player that lacks it.

    Summing generalises the pairwise case to team sizes other than one: with
    equal-sized teams it is equivalent to averaging, and a team of strong
    players outranks a team of weak ones.

    A missing value means *unknown*, not *zero*, so it is rejected rather than
    defaulted. Defaulting would quietly make the unrated side an automatic
    loser, and a misspelled key would produce a simulation where one side always
    wins with no error at all — the same class of silent failure that the
    outcome model exists to remove. Failing loudly is the better trade: the
    platform seeds this key for every player it creates, so reaching this in a
    normal run means a key was renamed without its readers following.
    """
    total = 0.0

    for player in team:
        value = player.player_features.get(key)
        if value is None:
            raise ValueError(
                f"Player '{player.username}' has no '{key}' to decide a match "
                f"outcome from. Players created by the platform always have one."
            )
        total += float(value)

    return total


class TrueSkillOutcome(MatchOutcomeModel):
    """Decides rounds from each player's hidden real ability.

    This is the default because it keeps the simulation honest: results are
    decided by something the matchmaker never sees, so its estimates can be
    scored against an independent truth.
    """

    def __init__(self, skill_key: str = TRUE_SKILL_KEY) -> None:
        self._skill_key = skill_key

    def win_probability(self, team_a: list[Player], team_b: list[Player]) -> float:
        a = _team_strength(team_a, self._skill_key)
        b = _team_strength(team_b, self._skill_key)
        return _ratio(a, b)


class RatingOutcome(MatchOutcomeModel):
    """Decides rounds from a strategy's own skill estimate.

    Useful for running the rating system in isolation, but note it makes the loop
    circular: a matchmaker whose pairing is judged by its own estimate cannot be
    shown to be wrong. The strategy supplies the key it uses, so this stays
    agnostic about which rating scheme is in play.
    """

    def __init__(self, skill_key: str) -> None:
        self._skill_key = skill_key

    def win_probability(self, team_a: list[Player], team_b: list[Player]) -> float:
        a = _team_strength(team_a, self._skill_key)
        b = _team_strength(team_b, self._skill_key)
        return _ratio(a, b)


def _ratio(a: float, b: float) -> float:
    """Bradley-Terry strength ratio, with the degenerate cases handled.

    Two absent or zero-strength teams are a genuine 50/50 (there is no basis to
    prefer either), which keeps an unrated or hand-built player from silently
    becoming an automatic loser.
    """
    total = a + b
    if total == 0:
        return 0.5

    return a / total
