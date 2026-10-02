<h1 align="center">Matchmaking Lab</h1>

<p align="center">A platform for prototyping, analysing &amp; exploring different matchmaking approaches for competitive online games.</p>

<br>

## Status

**Version:** 1.0.0

This is a working prototype rather than a finished product. Version 1.0 marks the first end-to-end vertical slice: a complete, runnable matchmaking loop — players are generated, queued, matched on their own running estimate of skill, their matches are simulated against a hidden true skill, the estimates are updated from the results, and the quality of those estimates is measured and displayed live. One approach is implemented, Bradley-Terry.

The 1.0 label is a statement about the loop being complete, not about the interface being finished. Expect the structure to keep changing, and treat the numbers in [docs/](./docs) as the record of what was measured rather than as a specification. Known limitations are written down rather than left to be discovered: the [rating drift](./docs/rating-drift.md) behind the leaderboard's estimated-skill column is the main one.

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
|   ├── ui/                   Textual TUI (app, event feed, stat panels, leaderboard)
|   └── cli.py                CLI entrypoint
├── tests/                    unit + integration (headless Textual) tests
└── pyproject.toml            package metadata, dependencies and CLI script
```

<br>

## Architecture
The project uses a **strategy design pattern** to modularise different matchmaking approaches behind a single, generalisable platform.

A `MatchmakingStrategy` defines how players are matched (setup_features, running the matching algorithm, and updating features on finished matches), while a tightly-coupled `RequestGenerator` produces the input data a given approach expects. The `MatchmakerFactory` builds these tightly-coupled objects together so they are always configured consistently. Currently implemented approaches live under `matchmakers/bradley_terry/`.

A `SimHarness` (see `platform/sim_harness.py`) owns the full runtime composition — generator, platform, simulator and `PlatformState` — and exposes a single `step()` that returns a read-only `SimSnapshot`. The display layer only ever sees these snapshots, never the sim internals, so the simulation can be refactored freely beneath that boundary. That display layer is a [Textual](https://github.com/Textualize/textual) TUI in `matchmakinglab/ui/` driven by a tick timer, plus a headless mode that logs tick stats to stdout without the TUI. Four panels sit in two columns: the event feed on the left, and population state, analytics and a top-100 player leaderboard on the right. The leaderboard ranks by estimated rating and shows each player's hidden true skill beside it, which is display-only — nothing in the matching or rating path reads it. The estimated column is trustworthy for *ordering* but not for magnitude: the rating scale spreads wider than the truth it tracks as a run goes on, and the `Rating / true spread` readout in the analytics panel reports the gap. This is a known, measured limitation rather than a defect — see [rating-drift.md](./docs/rating-drift.md) for the numbers and why 1.0 ships with it.

Configuration is driven from the CLI entrypoint (`cli.py`), which offers an interactive guided setup on startup as well as promptless flag-based booting. It covers two kinds of configuration: a strategy's own sub-configuration (which is positional and enum-only, and generated from each strategy's declaration), and the simulation setup shared by every strategy (`--players`, `--requests`), which is declared once and drives both the flags and the guided-setup questions.

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

- **Export** — write the same per-tick data to a file. The format comes from the extension, `.csv` or `.jsonl`:
  `matchmakinglab --default --headless --ticks 500 --export run.csv`

- **Seed** — pass a seed through to the harness for reproducible runs:
  `matchmakinglab --default --seed 42`

- **Population size** — how many simulated players the run can ever contain (default 500):
  `matchmakinglab --default --players 150`

- **Requests per tick** — how much work arrives each tick, as an inclusive `MIN:MAX`
  range (default `10:50`). A fixed rate is the degenerate case:
  `matchmakinglab --default --requests 10:10`

  `MIN` may be `0`, which lets some ticks arrive nobody:
  `matchmakinglab --default --requests 0:50` gives a world with lulls in it,
  rather than the metronome a range starting high produces.

  Both of these are also asked for in the interactive guided setup, where a flag
  you passed skips its own question. Note that the widest batch must fit in the
  population, so `--players 8 --requests 1:50` is refused at startup rather than
  failing on the first tick.

To see the full help, including each strategy's sub-configuration order, use:
`matchmakinglab --help`

<br>

## License
This project is licensed under the [GNU General Public License v3.0](./LICENSE).

Chosen for its copyleft terms: derived or modified versions must be made available under the same license, keeping the project and its downstream forks open. This is in keeping with the goal of sharing matchmaking research and implementations as an open platform.
