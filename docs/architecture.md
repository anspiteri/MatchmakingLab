# Architecture

## Overview

MatchmakingLab is a CLI-driven platform for prototyping and analysing different matchmaking approaches. The codebase is organised into four areas under `src/matchmakinglab/`:

- `core/` — shared data models and runtime state
- `matchmakers/` — matchmaking approaches (strategy pattern)
- `platform/` — platform orchestration and match simulation
- `app.py` — the CLI entrypoint

```
app.py ──> factory ──> Platform ◄── MatchmakingStrategy
           │              │
           └─► Generator  PlatformState (models)
```

## CLI Entrypoint: `app.py`

The application is run through the `matchmakinglab` command (registered as the `matchmakinglab.app:cli` console script in `pyproject.toml`). It uses [Click](https://click.palletsprojects.com/) and offers a choice of boot modes:

- **Interactive guided setup**, which prompts for strategy selection and configuration.
- **Promptless boot** via `--strategy <name> <config...>` (sub-config given positionally) or `--default` (defaults).

Strategies are registered in a `STRATEGIES` registry keyed by a kebab-case name; each entry provides its factory, a description, and its config options (name, enum type, default, help). Adding a new strategy means adding an entry to this registry — the CLI, help text, and sub-config documentation are generated from it.

When a strategy is booted, the CLI builds a config dict (from prompts, positional values, or defaults) and hands it to the strategy's factory.

## Matchmaking Engine: `matchmakers/`

### Strategy pattern
Different matchmaking approaches are implemented using a **strategy design pattern**: each approach lives in its own package under `matchmakers/` (currently `bradley_terry/`) and implements the abstract `MatchmakingStrategy` base class. This modularises the approaches while keeping a single generalisable `Platform`.

A strategy defines the full matchmaking lifecycle (see `base_strategy.py`):

- `setup_player_features()` — initialise player state (e.g. a base skill rating) when a player first joins.
- `run_algorithm(queue_snapshot)` — given the queued requests, return the matches to form and the players still waiting.
- `update_player_features(finished_match)` — update player state from completed match results, closing the feedback loop.

### Request generators
Each approach also expects specific input data (player features and request features). A coupled `RequestGenerator` (see `base_generator.py`) is responsible for producing that data. Generators are tightly coupled to their approach because the data must match what the strategy consumes.

### Strategy <-> Generator coupling: the factory
Because generators and strategies are tightly coupled, a `MatchmakerFactory` (see `factory.py`) builds them together so they are always configured consistently. Each strategy provides a factory — currently `BradleyTerryFactory` — which constructs a `Platform` configured with the strategy and the matching generator.

## Platform: `platform/`

The `Platform` is the single generalisable harness that runs a strategy against a game state. It:

- assigns players to the matchmaking queue (`add_to_matchmaking_queue`), initialising their feature set via the strategy on first join;
- advances the simulation one step each `tick`, which:
  1. runs the strategy's `run_algorithm` to form matches and leave the rest queued,
  2. simulates active matches (not yet implemented — `_simulate_matches` returns `None`),
  3. updates player features from finished matches,
  4. increments the wait time of still-queued requests.

The `Platform` is strategy-agnostic; all approach-specific logic lives in the strategy.

## State & Models: `core/`

- `models.py` — the shared data models: `Player`, `MatchRequest`, `ActiveMatch`, and `FinishedMatch`, plus feature keys (e.g. latency, region) and the `Region` enum.
- `state.py` — `PlatformState`, a runtime container holding the player database, the matchmaking queue, and active/finished matches. It is shared between the platform and the CLI during initialisation.

## General Design Notes

- Each approach expects its own set of player features (e.g. skill level, queue time) and request features (e.g. latency/ping). Keeping the platform generalisable means ensuring the data a generator produces carries the features the selected strategy expects.
- Configuration is intended to be approachable: matchmaking is selectable both via command-line arguments (`--strategy`) and via interactive prompts at startup, so the application can be used without consulting help text or man pages.
