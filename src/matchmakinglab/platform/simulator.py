import random

from matchmakinglab.core.models import ActiveMatch, FinishedMatch

MIN_TICK_TIME = 5  # below 5 ticks, guarentees match continues
MAX_TICK_TIME = 60  # above 60 ticks, guarentees match end


def _simulate_match(match: ActiveMatch) -> FinishedMatch:
    # TODO: actual match simulation maths (win logic etc.). Currently the
    # winning/losing teams are just the two teams in request order.
    return FinishedMatch(match.tick_match_length, match.team_A, match.team_B)


class Simulator:
    def __init__(self) -> None:
        pass

    def simulate_matches(
        self, active_matches: list[ActiveMatch], finished_matches: list[FinishedMatch]
    ):
        # Advance the clock of every active match, then collect those that have
        # run for long enough. Two-pass avoids mutating the list while iterating.
        for match in active_matches:
            match.tick_match_length += 1

        finished = [
            m
            for m in active_matches
            if m.tick_match_length > random.randint(MIN_TICK_TIME, MAX_TICK_TIME)
        ]

        for match in finished:
            active_matches.remove(match)
            finished_matches.append(_simulate_match(match))
