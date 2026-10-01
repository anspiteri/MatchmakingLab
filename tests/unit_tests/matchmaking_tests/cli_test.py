"""
cli_test.py
~~~~~~~~~~~

Tests the CLI startup plumbing: config resolution, positional config
validation and the strategy/generator setup path.
"""

import pytest
from click import ClickException
from click.testing import CliRunner

from matchmakinglab import cli as cli_module
from matchmakinglab.cli import (
    STRATEGIES,
    _build_help,
    _collect_config_from_positional,
    _format_choices,
    _HelpCommand,
    _prompt_config,
    _resolve_enum_value,
    _run_headless,
    _run_setup,
    _selectable_members,
    cli,
)
from matchmakinglab.matchmakers import (
    BradleyTerry,
    BradleyTerryGenerator,
    BTCandidateGenerationMethod,
    BTOptimisationMethod,
)
from matchmakinglab.matchmakers.bradley_terry import generator as bt_generator
from matchmakinglab.matchmakers.bradley_terry.strategy import BradleyTerry as BT
from matchmakinglab.platform.platform import Platform
from matchmakinglab.platform.sim_harness import SimHarness

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
    platform, generator, setup, name = _run_setup(None, True, (), {})

    assert isinstance(platform, Platform)
    assert isinstance(platform.strategy, BradleyTerry)
    assert platform.strategy._candidate_generation_method == (
        BTCandidateGenerationMethod.NAIVE
    )
    assert platform.strategy._optimisation_method == BTOptimisationMethod.GREEDY
    assert isinstance(generator, BradleyTerryGenerator)
    assert setup == {"players": 500, "requests": (10, 50)}
    assert name == "bradley-terry"


def test_run_setup_sizes_the_generator_from_the_population():
    _, generator, setup, _ = _run_setup(
        None, True, (), {"players": 12, "requests": (3, 6)}
    )

    assert setup["players"] == 12
    assert isinstance(generator, BradleyTerryGenerator)
    assert len(generator.generate_requests(12, {})) == 12


def test_run_setup_passes_flags_through_to_the_setup():
    _, _, setup, _ = _run_setup(None, True, (), {"players": 30, "requests": (2, 9)})

    assert setup == {"players": 30, "requests": (2, 9)}


def test_run_setup_from_positional_config():
    platform, _, _, _ = _run_setup(
        "bradley-terry", False, ("nearest-neighbour", "greedy"), {}
    )

    strategy = platform.strategy
    assert isinstance(strategy, BradleyTerry)
    assert strategy._candidate_generation_method == (
        BTCandidateGenerationMethod.NEAREST_NEIGHBOUR
    )


def test_run_setup_rejects_default_with_strategy():
    with pytest.raises(ClickException, match="--strategy.*--default"):
        _run_setup("bradley-terry", True, (), {})


def test_run_setup_rejects_unknown_strategy():
    with pytest.raises(ClickException, match="Unknown strategy"):
        _run_setup("mystery", False, (), {})


def test_run_setup_interactive_prompt(mocker):
    # Strategy, its two sub-config values, then the two simulation setup values.
    mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy", "80", "3:7"],
    )

    platform, generator, setup, _ = _run_setup(None, False, (), {})

    assert isinstance(platform.strategy, BradleyTerry)
    assert platform.strategy._candidate_generation_method == (
        BTCandidateGenerationMethod.NAIVE
    )
    assert isinstance(generator, BradleyTerryGenerator)
    assert setup == {"players": 80, "requests": (3, 7)}


def test_run_setup_interactive_prompt_falls_back_to_defaults(mocker):
    mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy", "", ""],
    )

    _, _, setup, _ = _run_setup(None, False, (), {})

    assert setup == {"players": 500, "requests": (10, 50)}


def test_run_setup_flags_suppress_their_own_prompt(mocker):
    """A flag already answered is not asked again.

    Prompts are the four with no value behind them; if --players also prompted,
    the value typed on the command line would be silently ignored in favour of
    whatever the user then typed.
    """
    prompt = mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy", "4:6"],
    )

    _, _, setup, _ = _run_setup(None, False, (), {"players": 40})

    assert prompt.call_count == 4
    assert setup == {"players": 40, "requests": (4, 6)}


def test_run_setup_does_not_prompt_outside_the_guided_setup(mocker):
    prompt = mocker.patch("matchmakinglab.cli.click.prompt")

    _run_setup(None, True, (), {})
    _run_setup("bradley-terry", False, ("naive", "greedy"), {})

    assert prompt.call_count == 0


# ---------- Setup validation ----------


def test_run_setup_rejects_a_population_smaller_than_a_request_batch():
    with pytest.raises(ClickException, match="widest batch must fit"):
        _run_setup(None, True, (), {"players": 8, "requests": (1, 50)})


def test_run_setup_rejects_a_population_below_two():
    with pytest.raises(ClickException, match="at least 2"):
        _run_setup(None, True, (), {"players": 1})


# ---------- Prompt config ----------


def test_prompt_config_resolves_defaults(mocker):
    prompt = mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["naive", "greedy"],
    )

    config = _prompt_config(STRATEGIES["bradley-terry"]["config"])

    assert config == {
        "candidate_generation_method": BTCandidateGenerationMethod.NAIVE,
        "optimisation_method": BTOptimisationMethod.GREEDY,
    }
    # The prompt text advertises the selectable choices and the default value.
    assert "candidate_generation_method" not in prompt.call_args_list[0].args[0]
    assert "nearest-neighbour" in prompt.call_args_list[0].args[0]


def test_prompt_config_with_no_options_returns_empty():
    assert _prompt_config([]) == {}


# ---------- Registry ----------


def test_build_help_skips_strategies_without_config(monkeypatch):
    """A registered strategy with no sub-config is omitted from the help body."""
    monkeypatch.setitem(
        cli_module.STRATEGIES,
        "minimal",
        {
            "factory": STRATEGIES["bradley-terry"]["factory"],
            "description": "No options",
            "config": [],
        },
    )

    help_text = _build_help()

    assert "minimal" not in help_text
    assert "bradley-terry" in help_text


# ---------- Headless mode ----------


def test_run_headless_prints_one_line_per_tick(capsys):
    harness = SimHarness(
        bt_generator.BradleyTerryGenerator(player_count=50, seed=1),
        Platform(BT()),
        requests_per_step=4,
        seed=1,
    )

    _run_headless(harness, 3)

    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("tick=")
    ]
    assert len(lines) == 3
    assert lines[0].startswith("tick=1 queue=")
    assert "active=" in lines[0]
    assert "finished=" in lines[0]
    assert "sim=" in lines[0]


def test_run_headless_reports_queue_length_not_a_list(capsys):
    """Headless output reports how many players are waiting, as a bare number."""
    harness = SimHarness(
        bt_generator.BradleyTerryGenerator(player_count=50, seed=1),
        Platform(BT()),
        requests_per_step=3,
        seed=1,
    )

    _run_headless(harness, 1)

    first = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("tick=")
    )
    # An odd request rate always leaves exactly one player unmatched.
    assert first.split("queue=")[1].split()[0] == "1"


def test_run_headless_with_zero_ticks_prints_nothing(capsys):
    harness = SimHarness(
        bt_generator.BradleyTerryGenerator(player_count=10),
        Platform(BT()),
        requests_per_step=2,
    )

    _run_headless(harness, 0)

    assert capsys.readouterr().out == ""


# ---------- End to end command ----------


def test_cli_default_headless_runs():
    result = CliRunner().invoke(cli, ["--default", "--headless", "--ticks", "2"])

    assert result.exit_code == 0, result.output
    assert "Strategy: Bradley-Terry" in result.output
    assert "Platform setup." in result.output
    assert len([l for l in result.output.splitlines() if l.startswith("tick=")]) == 2


def test_cli_strategy_with_positional_config_runs_headless():
    result = CliRunner().invoke(
        cli,
        [
            "--strategy",
            "bradley-terry",
            "naive",
            "greedy",
            "--headless",
            "--ticks",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "tick=1" in result.output


def test_cli_strategy_name_is_case_insensitive():
    result = CliRunner().invoke(
        cli,
        [
            "--strategy",
            "BRADLEY-TERRY",
            "naive",
            "greedy",
            "--headless",
            "--ticks",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output


def test_cli_rejects_conflicting_flags():
    result = CliRunner().invoke(cli, ["--default", "--strategy", "bradley-terry"])

    assert result.exit_code != 0
    assert "not both" in result.output


def test_cli_rejects_missing_positional_config():
    result = CliRunner().invoke(
        cli, ["--strategy", "bradley-terry", "naive", "--headless"]
    )

    assert result.exit_code != 0
    assert "requires 2 config value" in result.output


def test_cli_interactive_setup_boots_platform(mocker):
    # Strategy, its two sub-config values, then the two simulation setup values.
    prompt = mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy", "150", "4:9"],
    )
    headless = mocker.patch("matchmakinglab.cli._run_headless")

    result = CliRunner().invoke(cli, ["--headless", "--ticks", "1"])

    assert result.exit_code == 0, result.output
    assert prompt.call_count == 5
    # The interactive path still routes through the headless runner.
    headless.assert_called_once()


def test_cli_interactive_setup_applies_the_answered_values(mocker):
    mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy", "150", "4:9"],
    )
    mocker.patch("matchmakinglab.cli._run_headless")

    result = CliRunner().invoke(cli, ["--headless", "--ticks", "1"])

    assert "players: 150  requests: 4:9" in result.output


def test_cli_interactive_setup_accepts_defaults_left_blank(mocker):
    """An empty answer takes the default, the way an empty prompt answer always has.

    Worth pinning because the simulation setup is the first part of the guided
    path with a value that is not a strategy enum, so it is the first place a
    blank line could turn into a parse error instead of the advertised default.
    """
    mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy", "", ""],
    )
    mocker.patch("matchmakinglab.cli._run_headless")

    result = CliRunner().invoke(cli, ["--headless", "--ticks", "1"])

    assert result.exit_code == 0, result.output
    assert "players: 500  requests: 10:50" in result.output


def test_cli_flags_skip_their_prompt_in_the_interactive_setup(mocker):
    """A flag answers the question it would otherwise ask.

    Prompt count is the strategy choice plus its two sub-config values only: the
    two setup questions are skipped because the flags already supplied them.
    """
    prompt = mocker.patch(
        "matchmakinglab.cli.click.prompt",
        side_effect=["bradley-terry", "naive", "greedy"],
    )
    mocker.patch("matchmakinglab.cli._run_headless")

    result = CliRunner().invoke(
        cli, ["--headless", "--ticks", "1", "--players", "150", "--requests", "4:9"]
    )

    assert result.exit_code == 0, result.output
    assert prompt.call_count == 3
    assert "players: 150  requests: 4:9" in result.output


def test_cli_flags_override_the_default_setup(mocker):
    mocker.patch("matchmakinglab.cli.MatchmakingLabApp")

    result = CliRunner().invoke(
        cli, ["--default", "--players", "60", "--requests", "5:8"]
    )

    assert result.exit_code == 0, result.output
    assert "players: 60  requests: 5:8" in result.output


@pytest.mark.parametrize(
    "args, expected",
    [
        (["--requests", "50:10"], "below its minimum"),
        (["--requests", "10"], "Expected MIN:MAX"),
        (["--requests", "ten:fifty"], "Expected MIN:MAX"),
        (["--requests", "0:10"], "minimum must be at least 1"),
        (["--players", "1"], "must be at least 2"),
        (["--players", "8", "--requests", "1:50"], "widest batch must fit"),
    ],
)
def test_cli_rejects_an_unusable_setup(args, expected):
    result = CliRunner().invoke(cli, ["--default", "--headless", "--ticks", "1"] + args)

    assert result.exit_code != 0
    assert expected in result.output


def test_cli_accepts_a_dash_separated_request_range(mocker):
    mocker.patch("matchmakinglab.cli._run_headless")

    result = CliRunner().invoke(
        cli, ["--default", "--headless", "--ticks", "1", "--requests", "4-6"]
    )

    assert result.exit_code == 0, result.output
    assert "requests: 4:6" in result.output


def test_cli_launches_the_tui_when_not_headless(mocker):
    app_cls = mocker.patch("matchmakinglab.cli.MatchmakingLabApp")

    result = CliRunner().invoke(cli, ["--default"])

    assert result.exit_code == 0, result.output
    app_cls.assert_called_once()
    _, kwargs = app_cls.call_args
    assert (
        kwargs["config_summary"]
        == "strategy: bradley-terry  players: 500  requests: 10:50"
    )
    assert kwargs["seed"] is None
    app_cls.return_value.run.assert_called_once_with()


def test_cli_headless_summary_includes_seed(mocker):
    app_cls = mocker.patch("matchmakinglab.cli.MatchmakingLabApp")

    result = CliRunner().invoke(cli, ["--default", "--seed", "7"])

    assert result.exit_code == 0, result.output
    _, kwargs = app_cls.call_args
    assert kwargs["seed"] == 7


# ---------- Help rendering ----------


def test_cli_help_preserves_paragraph_breaks():
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    # The custom help command keeps the blank lines from the source template.
    assert "Usage:" in result.output
    assert "Sub-configuration" in result.output
    assert "bradley-terry:" in result.output
    assert "candidate_generation_method" in result.output
    assert "optimisation_method" in result.output


def test_cli_help_documents_the_simulation_setup():
    """The setup options are documented in the hand-written help block.

    Their generated --help entries are click's own, but the block that explains
    how the two kinds of configuration relate is not, so it has to carry them.
    """
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Simulation setup" in result.output
    assert "--players" in result.output
    assert "--requests" in result.output


def test_sim_config_is_the_single_source_for_flags_and_prompts():
    """Each setup option declares itself once, for both surfaces.

    The flag and the guided question are generated from this list. An option
    added here appears in both, and one that somehow reached only one of them
    would be the sort of thing a user finds out about the wrong way.
    """
    names = {opt["name"] for opt in cli_module.SIM_CONFIG}
    # Matched on the long flag, not the parameter name: --requests is parsed
    # into `requests_range` because a bare `requests` would shadow nothing but
    # reads as the range it is.
    flags = {o for p in cli_module.cli.params for o in p.opts if o.startswith("--")}

    assert names == {"players", "requests"}
    assert {f"--{name}" for name in names} <= flags


class _RecordingFormatter:
    """Minimal stand-in for click's HelpFormatter."""

    current_indent = 0

    def __init__(self):
        self.written: list[str] = []

    def write(self, text):
        self.written.append(text)


def _help_command(help_text):
    command = _HelpCommand("x")
    command.help = help_text
    return command


def test_help_command_without_text_writes_nothing():
    formatter = _RecordingFormatter()

    _help_command(None).format_help_text(None, formatter)

    assert formatter.written == []


def test_help_command_with_blank_text_writes_nothing():
    formatter = _RecordingFormatter()

    _help_command("\n\n").format_help_text(None, formatter)

    assert formatter.written == []


def test_help_command_indents_each_line():
    formatter = _RecordingFormatter()
    formatter.current_indent = 2

    _help_command("first\nsecond").format_help_text(None, formatter)

    assert formatter.written == ["  first\n", "  second\n"]
