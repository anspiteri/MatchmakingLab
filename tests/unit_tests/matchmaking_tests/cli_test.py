"""
cli_test.py
~~~~~~~~~~~

Tests the CLI startup plumbing: config resolution, positional config
validation and the strategy/generator setup path.
"""

import pytest
from click import ClickException

from matchmakinglab.cli import (
    STRATEGIES,
    _build_help,
    _collect_config_from_positional,
    _format_choices,
    _resolve_enum_value,
    _run_setup,
    _selectable_members,
)
from matchmakinglab.matchmakers import (
    BradleyTerry,
    BradleyTerryGenerator,
    BTCandidateGenerationMethod,
    BTOptimisationMethod,
)
from matchmakinglab.platform.platform import Platform

# ---------- Enum helpers ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("naive", BTCandidateGenerationMethod.NAIVE),
        ("NAIVE", BTCandidateGenerationMethod.NAIVE),
        ("nearest-neighbour", BTCandidateGenerationMethod.NEAREST_NEIGHBOUR),
        ("greedy", BTOptimisationMethod.GREEDY),
    ],
)
def test_resolve_enum_value(raw, expected):
    enum_type = type(expected)
    assert _resolve_enum_value(enum_type, raw) is expected


def test_selectable_members_excludes_undefined():
    members = _selectable_members(BTCandidateGenerationMethod)

    assert BTCandidateGenerationMethod.UNDEFINED not in members
    assert BTCandidateGenerationMethod.NAIVE in members
    assert BTCandidateGenerationMethod.NEAREST_NEIGHBOUR in members


def test_format_choices():
    assert _format_choices(BTCandidateGenerationMethod) == "naive, nearest-neighbour"
    assert _format_choices(BTOptimisationMethod) == "greedy"


# ---------- Build help ----------


def test_build_help_documents_strategy_subconfig():
    help_text = _build_help()

    assert "bradley-terry" in help_text
    assert "candidate_generation_method" in help_text
    assert "optimisation_method" in help_text


# ---------- Positional config validation ----------


def test_collect_config_from_positional_valid():
    config = _collect_config_from_positional(
        ("naive", "greedy"), STRATEGIES["bradley-terry"]["config"]
    )

    assert config == {
        "candidate_generation_method": BTCandidateGenerationMethod.NAIVE,
        "optimisation_method": BTOptimisationMethod.GREEDY,
    }


def test_collect_config_from_positional_rejects_wrong_count():
    with pytest.raises(ClickException, match="requires 2 config value"):
        _collect_config_from_positional(
            ("naive",), STRATEGIES["bradley-terry"]["config"]
        )


def test_collect_config_from_positional_rejects_invalid_value():
    with pytest.raises(ClickException, match="Invalid value"):
        _collect_config_from_positional(
            ("bogus", "greedy"), STRATEGIES["bradley-terry"]["config"]
        )


# ---------- Run setup ----------


def test_run_setup_defaults():
    platform, generator = _run_setup(None, True, ())

    assert isinstance(platform, Platform)
    assert isinstance(platform.strategy, BradleyTerry)
    assert platform.strategy._candidate_generation_method == (
        BTCandidateGenerationMethod.NAIVE
    )
    assert platform.strategy._optimisation_method == BTOptimisationMethod.GREEDY
    assert isinstance(generator, BradleyTerryGenerator)


def test_run_setup_from_positional_config():
    platform, _ = _run_setup(
        "bradley-terry", False, ("nearest-neighbour", "greedy")
    )

    strategy = platform.strategy
    assert isinstance(strategy, BradleyTerry)
    assert strategy._candidate_generation_method == (
        BTCandidateGenerationMethod.NEAREST_NEIGHBOUR
    )


def test_run_setup_rejects_default_with_strategy():
    with pytest.raises(ClickException, match="--strategy.*--default"):
        _run_setup("bradley-terry", True, ())


def test_run_setup_rejects_unknown_strategy():
    with pytest.raises(ClickException, match="Unknown strategy"):
        _run_setup("mystery", False, ())


def test_run_setup_interactive_prompt(mocker):
    mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy"],
    )

    platform, generator = _run_setup(None, False, ())

    assert isinstance(platform.strategy, BradleyTerry)
    assert platform.strategy._candidate_generation_method == (
        BTCandidateGenerationMethod.NAIVE
    )
    assert isinstance(generator, BradleyTerryGenerator)