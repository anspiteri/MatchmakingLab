from random import Random

from matchmakinglab.core.models import ActiveMatch, FinishedMatch
from matchmakinglab.platform.outcome import MatchOutcomeModel, TrueSkillOutcome

# Points needed to take a match. A race to a fixed target cannot overrun: with
# one point awarded per round, some side necessarily reaches this first, and the
# longest possible match is 2 * POINTS_TO_WIN - 1 rounds.
POINTS_TO_WIN = 3

# Rounds played per tick. Kept at one so a round reads as a single tick of sim
# time and match length stays directly comparable to the number of ticks a match
# occupied.
ROUNDS_PER_TICK = 1


def _simulate_round(
    match: ActiveMatch, rng: Random, outcome_model: MatchOutcomeModel
) -> None:
    """Play one round of an active match, crediting a point to the winning side.

    The round winner is drawn from the outcome model's probability for team A.
    Drawing on team A's probability (rather than, say, always rolling for the
    first-listed side) is what keeps the simulation free of a positional bias:
    the team a player happens to be listed on cannot influence their odds.
    """
    probability = outcome_model.win_probability(match.team_A, match.team_B)

    if rng.random() < probability:
        match.score_A += 1
    else:
        match.score_B += 1

    match.tick_match_length += 1


def _is_finished(match: ActiveMatch, points_to_win: int) -> bool:
    return match.score_A >= points_to_win or match.score_B >= points_to_win


def _simulate_match(match: ActiveMatch) -> FinishedMatch:
    """Convert a completed match into a result.

    Only called once a side has reached the points target, so exactly one team
    is credited as the winner. Because the race is self-bounding, matches cannot
    tie: a side always reaches the target first, and a draw state would have
    nothing to represent.
    """
    if match.score_A > match.score_B:
        return FinishedMatch(match.tick_match_length, match.team_A, match.team_B)

    return FinishedMatch(match.tick_match_length, match.team_B, match.team_A)


class Simulator:
    def __init__(
        self,
        seed: int | None = None,
        outcome_model: MatchOutcomeModel | None = None,
        points_to_win: int = POINTS_TO_WIN,
    ) -> None:
        self._rng = Random(seed)
        # Defaults to the hidden real ability, so results stay independent of
        # the matchmaker being evaluated.
        self._outcome_model: MatchOutcomeModel = (
            outcome_model if outcome_model is not None else TrueSkillOutcome()
        )
        self._points_to_win = points_to_win

    def simulate_matches(
        self, active_matches: list[ActiveMatch]
    ) -> list[FinishedMatch]:
        """Advance every active match by a tick, returning those that finish.

        Matches are advanced first and collected afterwards so the finished list
        is not built while iterating the list being mutated.
        """
        for match in active_matches:
            for _ in range(ROUNDS_PER_TICK):
                _simulate_round(match, self._rng, self._outcome_model)

        finished = [m for m in active_matches if _is_finished(m, self._points_to_win)]

        for match in finished:
            active_matches.remove(match)

        return [_simulate_match(match) for match in finished]
