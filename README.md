<h1 align="center">Matchmaking Lab</h1>

<p align="center">A platform for prototyping, analysing &amp; exploring different matchmaking approaches for competitive online games.</p>

<br>

## Status

**Version:** 0.1.0

This is an early-stage prototype. Version 0.1 signifies the project is still working towards a full vertical slice — an end-to-end, runnable example that demonstrates a complete matchmaking loop. Until that slice is delivered, expect the interface, behaviour and structure to change frequently and to be incomplete.

<br>

## Background
Matchmaking services are a core component of match-based competitive video games (League of Legends, Call of Duty, Fortnite, to name a few). At a basic level, these services seek to match queuing players based on features such as skill level, geographical region, latency / ping to servers, and queue time with the goal of optimising engagement and match satisfaction. There is an interesting history of approaches and developments to this kind of optimisation problem. To access some of the research that went into this project, see [references](./references/bibliography.md).

I decided to build this project to grow my applied algorithmic skills in the context of application design. This domain requires both in-depth algorithmic thinking and general engineering and architecting skills. This is also an interesting domain for me because of my personal experience playing Fortnite, Halo and other competitive games.

<br>

## Project Constraints
To focus my time on my desired growth areas I've decided to use the following constraints:
- Mocking of player / client requests using a "generator" scripted in python
- No auth or account management (all requests are treated as valid)
- Simulated / random match results instead of real matches
- Interactive TUI via [Click](https://click.palletsprojects.com/) and [Textual](https://github.com/Textualize/textual) instead of a production deployment

<br>

## Project Structure
```
MatchmakingLab/
├── docs/                     design decisions and working diary
├── references/
|   ├── papers/               research papers referenced by the project
|   └── bibliography.md
├── src/matchmakinglab/
|   ├── core/                 shared data models, runtime state and sim snapshots
|   ├── matchmakers/          matchmaking approaches (strategy pattern)
|   |   ├── bradley_terry/    the Bradley-Terry implementation
|   |   ├── base_strategy.py  abstract MatchmakingStrategy
|   |   ├── base_generator.py abstract RequestGenerator
|   |   └── factory.py        wires a strategy to its generator
|   ├── platform/             platform orchestration, match simulation and the SimHarness
|   ├── ui/                   Textual TUI (app, event feed, stat panels)
|   └── cli.py                CLI entrypoint
├── tests/                    unit + integration (headless Textual) tests
└── pyproject.toml            package metadata, dependencies and CLI script
```

<br>

## Architecture
The project uses a **strategy design pattern** to modularise different matchmaking approaches behind a single, generalisable platform.

A `MatchmakingStrategy` defines how players are matched (setup_features, running the matching algorithm, and updating features on finished matches), while a tightly-coupled `RequestGenerator` produces the input data a given approach expects. The `MatchmakerFactory` builds these tightly-coupled objects together so they are always configured consistently. Currently implemented approaches live under `matchmakers/bradley_terry/`.

A `SimHarness` (see `platform/sim_harness.py`) owns the full runtime composition — generator, platform, simulator and `PlatformState` — and exposes a single `step()` that returns a read-only `SimSnapshot`. The display layer only ever sees these snapshots, never the sim internals, so the simulation can be refactored freely beneath that boundary. That display layer is a [Textual](https://github.com/Textualize/textual) TUI in `matchmakinglab/ui/` driven by a tick timer, plus a headless mode that logs tick stats to stdout without the TUI.

Configuration is driven from the CLI entrypoint (`cli.py`), which offers an interactive guided setup on startup as well as promptless flag-based booting.

For more details on each module, see [architecture](./docs/architecture.md).

<br>

## Development
### Setting up & using a python environment
For first time use, set up a python environment using:
`python3 -m venv .venv`

Afterwards, use the following to activate the environment when working on the project:
`source .venv/bin/activate`

### Building & running
For building the project into a runnable program use:
`pip install -e ".[dev]"`

The entrypoint is the `matchmakinglab` command (registered as the `matchmakinglab.cli:cli` console script):

- **Interactive guided setup** — omitted options walk you through strategy selection and configuration:
  `matchmakinglab`

- **Boot a specific strategy with its sub-configuration** (positions after the strategy name, in order):
  `matchmakinglab --strategy bradley-terry naive greedy`

- **Boot with defaults, skipping all prompts**:
  `matchmakinglab --default`

- **Headless mode** — run the simulation without the TUI, logging per-tick stats to stdout:
  `matchmakinglab --default --headless --ticks 500`

- **Seed** — pass a seed through to the harness for reproducible runs:
  `matchmakinglab --default --seed 42`

To see the full help, including each strategy's sub-configuration order, use:
`matchmakinglab --help`

<br>

## License
This project is licensed under the [GNU General Public License v3.0](./LICENSE).

Chosen for its copyleft terms: derived or modified versions must be made available under the same license, keeping the project and its downstream forks open. This is in keeping with the goal of sharing matchmaking research and implementations as an open platform.
