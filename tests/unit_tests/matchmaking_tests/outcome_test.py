"""
outcome_test.py
~~~~~~~~~~~~~~~

Tests the match outcome models: the probability each side is given for winning
a round. These sit between the simulator and the players, so what matters most
is that they are symmetric (no side favoured by ordering) and monotonic in skill
(a stronger side is never given a lower chance).
"""

import pytest

from matchmakinglab.core.models import Region
from matchmakinglab.matchmakers.bradley_terry.strategy import (
    BASE_SKILL_RATING,
    SKILL_RATING_KEY,
)
from matchmakinglab.platform.outcome import (
    MatchOutcomeModel,
    RatingOutcome,
    TrueSkillOutcome,
)
from tests.helpers import make_skill_player

MODELS = [
    pytest.param(TrueSkillOutcome(), id="true-skill"),
    pytest.param(RatingOutcome(SKILL_RATING_KEY), id="rating"),
]


def _team(*skills: int) -> list:
    return [
        make_skill_player(
            i,
            f"p{i}",
            Region.OCEANIA,
            skill_rating=skill,
            true_skill=skill,
        )
        for i, skill in enumerate(skills)
    ]


# ---------- Contract ----------


@pytest.mark.parametrize("model", MODELS)
def test_evenly_matched_teams_get_even_odds(model):
    probability = model.win_probability(_team(100), _team(100))

    assert probability == pytest.approx(0.5)


@pytest.mark.parametrize("model", MODELS)
def test_probabilities_are_complementary_when_teams_are_swapped(model):
    """Swapping the sides must return the complement.

    This is the property that stops a side being favoured merely by being listed
    first, which is exactly the defect the previous placeholder had.
    """
    forward = model.win_probability(_team(150), _team(100))
    reverse = model.win_probability(_team(100), _team(150))

    assert forward + reverse == pytest.approx(1.0)


@pytest.mark.parametrize("model", MODELS)
def test_probability_is_always_a_valid_chance(model):
    for a, b in ((0, 0), (1, 999), (999, 1), (40, 160), (160, 40)):
        probability = model.win_probability(_team(a), _team(b))
        assert 0.0 <= probability <= 1.0


@pytest.mark.parametrize("model", MODELS)
def test_weaker_team_is_never_favoured(model):
    strong = _team(160)
    weak = _team(40)

    assert model.win_probability(strong, weak) > 0.5
    assert model.win_probability(weak, strong) < 0.5


@pytest.mark.parametrize("model", MODELS)
def test_stronger_team_is_more_likely_as_the_gap_widens(model):
    gaps = [1, 2, 3, 4, 5]
    weak = _team(100)

    chances = [model.win_probability(_team(100 + gap), weak) for gap in gaps]

    assert chances == sorted(chances)


def _all_models():
    """The concrete models, as instances rather than parametrised test ids."""
    return [TrueSkillOutcome(), RatingOutcome(SKILL_RATING_KEY)]


@pytest.mark.parametrize("model", MODELS)
def test_team_strength_sums_across_members(model):
    """Strength accumulates, so a strong side outranks a weak one of any size."""
    # Even at equal size, the stronger side is favoured.
    assert model.win_probability(_team(120, 120), _team(60, 60)) > 0.5
    # And depth is not cancelled by a size advantage on the other side.
    assert model.win_probability(_team(160, 160, 160), _team(100)) > 0.5


@pytest.mark.parametrize("model", MODELS)
def test_equal_sized_teams_are_ordered_by_average_strength(model):
    """With matching team sizes, summing is equivalent to averaging."""
    assert model.win_probability(_team(80, 120), _team(100, 100)) == pytest.approx(0.5)
    assert model.win_probability(_team(140, 140), _team(100, 100)) > 0.5
    assert model.win_probability(_team(60, 60), _team(100, 100)) < 0.5


@pytest.mark.parametrize("model", MODELS)
def test_unrated_players_fail_loudly_rather_than_auto_losing(model):
    """A missing value means unknown, not zero strength.

    Defaulting it to zero would make every unrated player an automatic loser,
    and a misspelled key would yield a simulation where one side always wins
    with no error raised — precisely the silent failure the outcome model exists
    to remove.
    """
    unrated = [make_player_with_empty_features()]

    # Each model reports the key it was actually reading.
    with pytest.raises(ValueError, match="no 'true_skill'"):
        TrueSkillOutcome().win_probability(_team(100), unrated)
    with pytest.raises(ValueError, match="no 'skill_rating'"):
        RatingOutcome(SKILL_RATING_KEY).win_probability(_team(100), unrated)
    with pytest.raises(ValueError, match="no 'skill_rating'"):
        RatingOutcome(SKILL_RATING_KEY).win_probability(unrated, _team(100))


def test_unrated_players_raise_for_the_hidden_skill_too():
    """A hand-built player has no hidden skill either."""
    model = TrueSkillOutcome()

    with pytest.raises(ValueError, match="no 'true_skill'"):
        model.win_probability(_team(100), [make_player_with_empty_features()])


def make_player_with_empty_features():
    """A player with an empty feature bag, as `make_player` produces."""
    from tests.helpers import make_player

    return make_player(99, "unrated", Region.OCEANIA)


# ---------- Abstraction ----------


def test_base_model_cannot_be_instantiated():
    with pytest.raises(TypeError):
        MatchOutcomeModel()


def test_subclass_must_implement_win_probability():
    class Incomplete(MatchOutcomeModel):
        pass

    with pytest.raises(TypeError):
        Incomplete()


# ---------- Which key gets read ----------


def test_true_skill_outcome_ignores_the_strategy_rating():
    """The honest case: a mis-estimated rating must not change the odds.

    This is what keeps the simulation independent of the matchmaker. If the
    outcome tracked the rating, a matchmaker could be shown to be right purely by
    agreeing with itself.
    """
    model = TrueSkillOutcome()

    well_estimated = model.win_probability(_team(150), _team(100))
    mis_estimated = model.win_probability(_team(150, 150), _team(100, 100))

    # Same real ability, different ratings — the odds must not move.
    assert well_estimated == pytest.approx(mis_estimated)


def test_rating_outcome_follows_the_key_it_is_given():
    """It reads the supplied rating rather than assuming a fixed scheme."""
    model = RatingOutcome(SKILL_RATING_KEY)

    favourite = [
        make_skill_player(0, "fav", Region.OCEANIA, skill_rating=160, true_skill=40)
    ]
    underdog = [
        make_skill_player(1, "dog", Region.OCEANIA, skill_rating=40, true_skill=160)
    ]

    # Real ability says the underdog should win; the rating model disagrees
    # because it can only see the estimate.
    assert model.win_probability(favourite, underdog) > 0.5
    assert TrueSkillOutcome().win_probability(favourite, underdog) < 0.5


def test_rating_outcome_reads_a_custom_key():
    """A different rating scheme can be supplied without touching the model."""
    from matchmakinglab.core.models import Player, PlayerStatus

    def player(name: str, value: int) -> Player:
        return Player(0, name, 0, 0, Region.OCEANIA, {"elo": value}, PlayerStatus.IDLE)

    model = RatingOutcome("elo")

    assert model.win_probability(
        [player("a", 160)], [player("b", 40)]
    ) == pytest.approx(0.8)
    assert model.win_probability(
        [player("a", 100)], [player("b", 100)]
    ) == pytest.approx(0.5)


def test_base_rating_is_evenly_matched_under_both_models():
    """A fresh player's rating matches the midpoint true skill by default."""
    for model in _all_models():
        assert model.win_probability(
            _team(BASE_SKILL_RATING), _team(BASE_SKILL_RATING)
        ) == pytest.approx(0.5)
