import click

from matchmakinglab.core.state import PlatformState
from matchmakinglab.matchmakers import (
    BradleyTerryFactory,
    BTCandidateGenerationMethod,
    BTOptimisationMethod,
)

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


def _prompt_config(config_options: list[dict]) -> dict:
    """Interactively prompt for each config option, displaying its default."""
    resolved = {}

    for opt in config_options:
        name = opt["name"]
        default = opt["default"]

        raw = click.prompt(
            f"  {opt['help']} [{_format_choices(opt['type'])}]",
            default=default.name.lower().replace("_", "-"),
            show_default=True,
            type=click.STRING,
        )

        resolved[name] = _resolve_enum_value(opt["type"], raw)

    return resolved


def _build_help() -> str:
    """Build the long help text, documenting sub-config per strategy."""
    lines = [
        "MatchmakingLab \u2014 a framework for prototyping and analysing "
        "competitive matchmaking algorithms.",
        "",
        "Without the --strategy or --default flags an interactive guided "
        "setup will walk you through strategy selection and configuration.",
        "",
        "Usage:",
        "  matchmakinglab                        interactive guided setup",
        "  matchmakinglab --strategy <t> <cfg>   boot a strategy with positional config",
        "  matchmakinglab --default              boot bradley-terry with defaults",
        "",
        "Sub-configuration (in positional order, after the strategy):",
    ]

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


# ── CLI ────────────────────────────────────────────────────────────
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
@click.argument("config_values", nargs=-1)
def cli(
    strategy: str,
    default: bool,
    config_values: tuple[str, ...],
):
    """Initialise the platform with the chosen strategy and config."""
    strategy_given = strategy is not None

    if strategy_given and default:
        raise click.ClickException("Use either --strategy or --default, not both.")

    if default:
        strategy = DEFAULT_STRATEGY
    elif not strategy_given:
        strategy = click.prompt(
            "Select matchmaking strategy", default=DEFAULT_STRATEGY, show_default=True
        )

    strategy = strategy.lower()

    if strategy not in STRATEGIES:
        raise click.ClickException(
            f"Unknown strategy '{strategy}'. Choose from: {', '.join(STRATEGIES)}"
        )

    entry = STRATEGIES[strategy]
    factory_cls = entry["factory"]
    config_options = entry["config"]

    click.echo(f"\nStrategy: {entry['description']}")

    if default:
        config = {opt["name"]: opt["default"] for opt in config_options}
    elif strategy_given:
        config = _collect_config_from_positional(config_values, config_options)
    else:
        click.echo("Configure strategy:\n")
        config = _prompt_config(config_options)
        click.echo()

    factory = factory_cls(config)
    platform = factory.create_platform()
    generator = factory.create_generator()
    state = PlatformState()

    click.echo("Platform ready.")
