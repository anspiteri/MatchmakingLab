from matchmaking_service.models import Player, Match, MatchRequest
from matchmaking_service.state import GameState

BASE_PLAYER_RATING = 1500

class GameService:
    def __init__(self, game_state: GameState):
        self._state = game_state
        self._id_count = 0

    def tick(self):
        # TODO: Implement tick operations
        # TODO: Determine how active matches and finished matches will operate.
        self.match_players()
        self.simulate_matches()
        self.update_ratings()

    def match_players(self):
        """
        This is the main match-making algorithm.

        Created matches are stored in State.
        """

    def simulate_matches():
        return None

    def update_ratings():
        return None

    def create_player(self, requested_username: str):
        """Attempts to create a new player"""

        # TODO: Proper validation
        # TODO: Generate ID or remove it altogether
        # TODO: Update exception handling with custom exception handling and
        # remove true/false

        id = self._id_count
        username = requested_username
        rating = BASE_PLAYER_RATING

        try:
            self._state.add_player(Player(id, username, rating))
        except Exception as e:
            return False
        else:
            self._id_count += 1
            return True

    def create_match_request(self, username: str):
        """Attempts to create a match request and add it to the queue"""
