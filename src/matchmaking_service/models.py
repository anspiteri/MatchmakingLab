class Player:
    def __init__(self, id: int, username: str, rating: float):
        self.id = id
        self.username = username
        self.rating = rating

class Match:
    def __init__(self, players: list[Player]):
        self.players = players
        self.winner = None

class MatchRequest:
    def __init__(self, player: Player, time: int):
        self.player = player
        self.time = time
