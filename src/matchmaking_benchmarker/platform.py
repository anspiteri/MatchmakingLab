from matchmaking_benchmarker.algorithms.base_algorithm import MatchmakingAlgorithm


class Platform:
    def __init__(self, algorithm: MatchmakingAlgorithm):
        self._id_count = 0
        self._algorithm = algorithm

    def tick(self):
        self.match_players(self._algorithm)
        self.simulate_matches()
        self.update_ratings()

    def match_players(self, algorithm: MatchmakingAlgorithm):
        """
        This is the main match-making algorithm.

        Created matches are stored in State.
        """
        algorithm.run_algorithm()

    def simulate_matches(self):
        return None

    def update_ratings(self):
        return None
