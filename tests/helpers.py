"""
helpers.py
~~~~~~~~~~

Shared test fixtures factories.

``Player`` is a plain dataclass whose fields are all positional, so every new
field inserted ahead of ``default_region`` silently breaks every construction
site in the suite. Routing all test player construction through
:func:`make_player` keeps that churn in one place and documents the win/loss
record that the platform now maintains for every player.
"""

from typing import Any

from matchmakinglab.core.models import Player, PlayerStatus, Region
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    SKILL_RATING_KEY,
)


def make_player(
    player_id: int = 0,
    username: str = "player",
    region: Region = Region.OCEANIA,
    player_features: dict[str, Any] | None = None,
    status: PlayerStatus = PlayerStatus.IDLE,
    wins: int = 0,
    loses: int = 0,
) -> Player:
    """Build a Player with sensible defaults for tests.

    ``player_features`` defaults to empty, mirroring ``Player`` itself, so this
    helper stays strategy-agnostic. Tests that need a Bradley-Terry skill
    rating should use :func:`make_skill_player` instead.
    """
    return Player(
        player_id,
        username,
        wins,
        loses,
        region,
        {} if player_features is None else player_features,
        status,
    )


def make_skill_player(
    player_id: int = 0,
    username: str = "player",
    region: Region = Region.OCEANIA,
    skill_rating: int = BASE_SKILL_RATING,
    status: PlayerStatus = PlayerStatus.IDLE,
    wins: int = 0,
    loses: int = 0,
) -> Player:
    """Build a Player carrying a Bradley-Terry skill rating.

    Use this whenever a test seeds a database that the BT request generator will
    pull from. ``_gen_existing_player_request`` subscripts
    ``player_features[SKILL_RATING_KEY]`` rather than using ``.get``: generation
    only ever sees players the platform created via ``setup_player_features``,
    so an unseeded entry in a hand-built database fixture is a test bug, not a
    runtime condition worth handling. A ``KeyError`` here means "use
    :func:`make_skill_player`", and is the intended signal.

    ``make_player`` is the right default everywhere else; a skill rating in a test
    that never touches rating logic just hides which behaviour is under test.
    """
    return make_player(
        player_id,
        username,
        region,
        {SKILL_RATING_KEY: skill_rating},
        status,
        wins,
        loses,
    )
