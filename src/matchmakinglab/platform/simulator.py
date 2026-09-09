from matchmakinglab.core.models import ActiveMatch, FinishedMatch

# Placeholder: how many ticks a match runs before it finishes.
MATCH_LENGTH_TICKS = 4


def _simulate_match(match: ActiveMatch) -> FinishedMatch:
    # TODO: actual match simulation maths (win logic etc.). Currently the
    # winning/losing teams are just the two teams in request order.
    return FinishedMatch(match.team_A, match.team_B)


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
            m for m in active_matches if m.tick_match_length >= MATCH_LENGTH_TICKS
        ]

        for match in finished:
            active_matches.remove(match)
            finished_matches.append(_simulate_match(match))
