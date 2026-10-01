import click

from matchmakinglab.matchmakers import (
    BTCandidateGenerationMethod,
    BTOptimisationMethod,
)
from matchmakinglab.matchmakers.base_generator import RequestGenerator
from matchmakinglab.matchmakers.bradley_terry.generator import DEFAULT_PLAYER_COUNT
from matchmakinglab.matchmakers.factory import BradleyTerryFactory
from matchmakinglab.platform.platform import Platform
from matchmakinglab.platform.sim_harness import (
    DEFAULT_REQUEST_RANGE,
    SimHarness,
    _validate_request_range,
)
from matchmakinglab.ui.app import MatchmakingLabApp

# ── Strategy Registry ──────────────────────────────────────────────
# To add a new strategy:
#   1. Create the strategy + generator + factory classes
#   2. Add an entry to STRATEGIES with a kebab-case key
#   3. Import the factory and any config enums above
# Config CLI flags are generated automatically from each strategy's
# "config" list, so no CLI plumbing changes are needed.

STRATEGIES = {
    "bradley-terry": {
        "factory": BradleyTerryFactory,
        "description": "Bradley-Terry pairwise comparison model",
        "config": [
            {
                "name": "candidate_generation_method",
                "type": BTCandidateGenerationMethod,
                "default": BTCandidateGenerationMethod.NAIVE,
                "help": "How match candidates are generated",
            },
            {
                "name": "optimisation_method",
                "type": BTOptimisationMethod,
                "default": BTOptimisationMethod.GREEDY,
                "help": "How matches are selected from candidates",
            },
        ],
    },
}

DEFAULT_STRATEGY = "bradley-terry"


# ── Simulation Setup ────────────────────────────────────────────────
# How the simulated world is populated, as opposed to how any one matchmaker
# works. Deliberately kept out of a strategy's sub-config: the harness draws
# arrivals for every approach alike, so putting these there would mean adding a
# second strategy duplicated all of them.
#
# `type` is int, str, an enum class for a sub-config choice, or "range" for a
# MIN:MAX pair. The flag and the guided prompt are generated from this list, so
# adding an option here adds it to both.

SIM_CONFIG = [
    {
        "name": "players",
        "type": int,
        "default": DEFAULT_PLAYER_COUNT,
        "help": "Size of the simulated player population",
    },
    {
        "name": "requests",
        "type": "range",
        "default": DEFAULT_REQUEST_RANGE,
        "help": "Requests arriving per tick, as MIN:MAX",
    },
]


# ── Helpers ────────────────────────────────────────────────────────
def _resolve_enum_value(enum_type, raw: str):
    """Convert a user-supplied string to an enum member (case-insensitive)."""
    return enum_type[raw.upper().replace("-", "_")]


_NON_SELECTABLE_MEMBERS = {"UNDEFINED"}


def _selectable_members(enum_type) -> list:
    return [m for m in enum_type if m.name not in _NON_SELECTABLE_MEMBERS]


def _format_choices(enum_type) -> str:
    return ", ".join(
        m.name.lower().replace("_", "-") for m in _selectable_members(enum_type)
    )


def _render_value(value) -> str:
    """Render an option's value the way a user would type it back."""
    if isinstance(value, tuple):
        return ":".join(str(v) for v in value)
    return str(value).lower()


def _parse_request_range(raw: str) -> tuple[int, int]:
    """Parse a MIN:MAX request range, accepting a dash separator too.

    Bounds are checked here rather than at the first tick, so a run that could
    never work is refused at startup with a readable reason.
    """
    separator = ":" if ":" in raw else "-"
    parts = raw.split(separator)

    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise click.ClickException(
            f"Invalid request range '{raw}'. Expected MIN:MAX of whole numbers, "
            f"e.g. 10:50."
        )

    try:
        return _validate_request_range((int(parts[0]), int(parts[1])))
    except ValueError as exc:
        raise click.ClickException(f"Invalid request range '{raw}'. {exc}") from None


def _parse_option_value(opt: dict, raw: str):
    """Convert one user-supplied string into this option's own type."""
    if opt["type"] is int:
        try:
            return int(raw)
        except ValueError:
            raise click.ClickException(
                f"Invalid value '{raw}' for {opt['name']}. Expected a whole number."
            ) from None

    if opt["type"] == "range":
        return _parse_request_range(raw)

    if opt["type"] is str:
        return raw

    try:
        return _resolve_enum_value(opt["type"], raw)
    except KeyError:
        raise click.ClickException(
            f"Invalid value '{raw}' for {opt['name']}. "
            f"Choose from: {_format_choices(opt['type'])}"
        ) from None


def _prompt_option(opt: dict):
    """Ask for one option interactively, then type the answer."""
    label = opt["help"]

    if opt["type"] not in (int, str, "range"):
        label = f"{label} [{_format_choices(opt['type'])}]"

    raw = click.prompt(
        f"  {label}",
        default=_render_value(opt["default"]),
        show_default=True,
    )

    # click itself substitutes the default for a blank line; this keeps a blank
    # answer meaning the same thing if the prompt is ever driven some other way.
    if not raw.strip():
        return opt["default"]

    return _parse_option_value(opt, raw)


def _prompt_config(config_options: list[dict]) -> dict:
    """Interactively prompt for each config option, displaying its default."""
    return {opt["name"]: _prompt_option(opt) for opt in config_options}


def _resolve_sim_setup(explicit: dict, interactive: bool) -> dict:
    """Resolve the simulation setup from defaults, flags, and prompts.

    An explicit flag always wins, and always suppresses its own prompt: asking
    `--players 200` and then querying population size anyway would be a bug, not
    a confirmation. With no flag the option comes from a prompt when the guided
    setup is running, and from its default otherwise.
    """
    resolved: dict = {}

    for opt in SIM_CONFIG:
        name = opt["name"]
        if name in explicit:
            resolved[name] = explicit[name]
        elif interactive:
            resolved[name] = _prompt_option(opt)
        else:
            resolved[name] = opt["default"]

    return resolved


def _validate_sim_setup(setup: dict) -> dict:
    """Check the setup against itself, not just each field in isolation.

    The generator can only hand out as many distinct new players as its pool
    holds, and asks for exactly that many on the first tick. A population
    smaller than the widest arrival batch would therefore die on tick one with a
    bare ValueError from deep in the generator.
    """
    players = setup["players"]
    if players < 2:
        raise click.ClickException(
            f"--players must be at least 2, got {players}. A single player can "
            f"never be matched against anyone."
        )

    high = setup["requests"][1]
    if high > players:
        raise click.ClickException(
            f"--requests asks for up to {high} requests per tick but --players is "
            f"only {players}. The widest batch must fit in the population, "
            f"otherwise the run cannot start."
        )

    return setup


def _build_help() -> str:
    """Build the long help text, documenting sub-config per strategy."""
    lines = [
        (
            "MatchmakingLab \u2014 a framework for prototyping and analysing "
            "competitive matchmaking algorithms."
        ),
        "",
        (
            "Without the --strategy or --default flags an interactive guided "
            "setup will walk you through strategy selection and configuration."
        ),
        "",
        "Usage:",
        "  matchmakinglab                        interactive guided setup",
        "  matchmakinglab --strategy <t> <cfg>   boot a strategy with positional config",
        "  matchmakinglab --default              boot bradley-terry with defaults",
        "",
        "Simulation setup (applies to every strategy; also prompted for in the",
        "guided setup, where a flag you passed skips its own question):",
    ]

    for opt in SIM_CONFIG:
        lines.append(
            f"  --{opt['name']} <{_render_value(opt['default'])}>  {opt['help']}"
        )

    lines += ["", "Sub-configuration (in positional order, after the strategy):"]

    for key, entry in STRATEGIES.items():
        if entry["config"]:
            lines.append(f"  {key}:")
            for i, opt in enumerate(entry["config"], start=1):
                lines.append(f"    {i}. {opt['name']} ({_format_choices(opt['type'])})")

    return "\n".join(lines)


def _collect_config_from_positional(
    config_values: tuple[str, ...], config_options: list[dict]
) -> dict:
    """Build a config dict from positional arguments, validating completeness."""
    names = [opt["name"] for opt in config_options]

    if len(config_values) != len(names):
        raise click.ClickException(
            f"Strategy requires {len(names)} config value(s) in order — "
            f"{', '.join(names)}. Got {len(config_values)}."
        )

    config: dict = {}
    for opt, value in zip(config_options, config_values):
        choice_str = _format_choices(opt["type"])
        choice_set = {
            m.name.lower().replace("_", "-") for m in _selectable_members(opt["type"])
        }
        if value.lower() not in choice_set:
            raise click.ClickException(
                f"Invalid value '{value}' for {opt['name']}. Choose from: {choice_str}"
            )
        config[opt["name"]] = _resolve_enum_value(opt["type"], value)

    return config


def _run_setup(
    strategy: str | None,
    default: bool,
    config_values: tuple[str, ...],
    sim_flags: dict,
) -> tuple[Platform, RequestGenerator, dict, str]:
    """Initialise the strategy, the generator, and the simulation setup.

    Returns the built objects plus the resolved setup and the chosen strategy
    name, so the caller does not have to resolve any of it twice.
    """
    strategy_given = strategy is not None

    if strategy_given and default:
        raise click.ClickException("Use either --strategy or --default, not both.")

    if default:
        strategy = DEFAULT_STRATEGY
    elif not strategy_given:
        strategy = click.prompt(
            "Select matchmaking strategy", default=DEFAULT_STRATEGY, show_default=True
        )

    assert strategy is not None
    strategy = strategy.lower()

    if strategy not in STRATEGIES:
        raise click.ClickException(
            f"Unknown strategy '{strategy}'. Choose from: {', '.join(STRATEGIES)}"
        )

    entry = STRATEGIES[strategy]
    factory_cls = entry["factory"]
    config_options = entry["config"]
    interactive = not default and not strategy_given

    click.echo(f"\nStrategy: {entry['description']}")

    if default:
        config = {opt["name"]: opt["default"] for opt in config_options}
    elif strategy_given:
        config = _collect_config_from_positional(config_values, config_options)
    else:
        click.echo("Configure strategy:\n")
        config = _prompt_config(config_options)
        click.echo()

    if interactive:
        click.echo("Configure simulation:\n")
    setup = _validate_sim_setup(_resolve_sim_setup(sim_flags, interactive))
    if interactive:
        click.echo()

    factory = factory_cls(config)
    platform = factory.create_platform()
    # The population is a generator concern: it is the generator's pool of
    # accounts to draw requests from, so it is passed in at construction rather
    # than reassigned afterwards.
    generator = factory.create_generator(setup["players"])

    return platform, generator, setup, strategy


class _HelpCommand(click.Command):
    def format_help_text(self, ctx, formatter):
        """Writes the help to the formatter, preserving explicit line breaks."""
        if self.help is None:
            return
        text = self.help.strip("\n")
        if text:
            indent = " " * formatter.current_indent
            for line in text.split("\n"):
                formatter.write(f"{indent}{line}\n")


# ── CLI ───────────────────────────────────────────────────
@click.command(cls=_HelpCommand, help=_build_help())
@click.option(
    "-s",
    "--strategy",
    type=click.Choice(list(STRATEGIES), case_sensitive=False),
    default=None,
    help=(
        "Matchmaking strategy to boot with, followed by its sub-configuration "
        "values in order. Omit for an interactive prompt."
    ),
)
@click.option(
    "-d",
    "--default",
    is_flag=True,
    default=False,
    help="Boot with the default strategy (bradley-terry) using default config, skipping all prompts.",
)
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Run without the Textual UI, logging each tick's stats to stdout.",
)
@click.option(
    "--ticks",
    type=int,
    default=1000,
    help="Number of ticks to run in --headless mode.",
)
@click.option(
    "--seed",
    type=int,
    default=None,
    help="Seed for reproducible runs (plumbed through to the harness).",
)
@click.option(
    "--players",
    type=int,
    default=None,
    help=f"Size of the simulated player population [default: {DEFAULT_PLAYER_COUNT}].",
)
@click.option(
    "--requests",
    "requests_range",
    type=str,
    default=None,
    help=(
        "Requests arriving per tick, as MIN:MAX "
        f"[default: {_render_value(DEFAULT_REQUEST_RANGE)}]."
    ),
)
@click.argument("config_values", nargs=-1)
def cli(
    strategy: str,
    default: bool,
    config_values: tuple[str, ...],
    headless: bool,
    ticks: int,
    seed: int,
    players: int,
    requests_range: str,
):
    # Only flags actually given are collected, so a setup option left off the
    # command line falls through to its prompt or default rather than being
    # pinned to a value the user never typed.
    sim_flags: dict = {}
    if players is not None:
        sim_flags["players"] = players
    if requests_range is not None:
        sim_flags["requests"] = _parse_request_range(requests_range)

    platform, generator, setup, chosen = _run_setup(
        strategy, default, config_values, sim_flags
    )

    click.echo("Platform setup.")

    harness = SimHarness(
        generator, platform, seed=seed, request_range=setup["requests"]
    )
    config_summary = (
        f"strategy: {chosen}  players: {setup['players']}  "
        f"requests: {_render_value(setup['requests'])}"
    )
    click.echo(config_summary)

    if headless:
        _run_headless(harness, ticks)
        return

    app = MatchmakingLabApp(harness, config_summary=config_summary, seed=seed)
    app.run()


def _run_headless(harness: SimHarness, ticks: int) -> None:
    """Drive the harness without the TUI, printing per-tick stats to stdout."""
    for _ in range(ticks):
        snapshot = harness.step()
        click.echo(
            f"tick={snapshot.tick} queue={len(snapshot.queue)} "
            f"active={snapshot.active_matches} finished={snapshot.finished_matches} "
            f"sim={snapshot.sim_seconds:0.1f}s"
        )
