# Architecture

## Overview

MatchmakingLab is a CLI-driven platform for prototyping and analysing different matchmaking approaches. The codebase is organised into five areas under `src/matchmakinglab/`:

- `core/` — shared data models, runtime state, and the read-only `SimSnapshot`
- `matchmakers/` — matchmaking approaches (strategy pattern)
- `platform/` — platform orchestration, match simulation, and the `SimHarness` facade
- `ui/` — the Textual TUI (app, event feed, stat panels)
- `cli.py` — the CLI entrypoint, wiring boot modes and headless runs together

```
cli.py ──> factory ──> Platform ◄── MatchmakingStrategy
           │              │
           └─► Generator  SimHarness (owns Platform + PlatformState + Simulator)
                            │
                            └─► SimSnapshot ──► Textual TUI (ui/) / headless logging
```

## CLI Entrypoint: `cli.py`

The application is run through the `matchmakinglab` command (registered as the `matchmakinglab.cli:cli` console script in `pyproject.toml`). It uses [Click](https://click.palletsprojects.com/) and offers a choice of boot modes:

- **Interactive guided setup**, which prompts for strategy selection and configuration.
- **Promptless boot** via `--strategy <name> <config...>` (sub-config given positionally) or `--default` (defaults).
- **Headless mode** via `--headless --ticks N`, which drives the `SimHarness` without the TUI and logs per-tick stats to stdout.
- **Seeding** via `--seed N`, plumbed through to the harness.

After setup, the CLI builds a `SimHarness` from the factory-produced platform and generator, then either runs the textual TUI (`ui/app.py`) or the headless loop.

## Simulation boundary: `platform/sim_harness.py`

The `SimHarness` is the single point of contact between the simulation and the display layer. It **owns** the full runtime composition — `RequestGenerator`, `Platform`, `Simulator`, and `PlatformState` — so the UI never reaches into sim internals. It exposes:

- `step() -> SimSnapshot` — advance one tick (generate → enqueue → `platform.tick` → simulate) and return a read-only snapshot.
- `SimSnapshot` (`core/snapshot.py`) — a plain dataclass with derived facts only (queue/active/finished counts, tick, wall-clock sim seconds, request rate, and a list of feed event lines).

Because the display only depends on this stable snapshot surface, `Platform`, `Simulator` and `RequestGenerator` can be refactored freely beneath the boundary.

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
  1. runs the strategy's `run_algorithm` to form matches and leave the rest queued (mutating the shared queue in place),
  2. updates player features from finished matches,
  3. increments the wait time of still-queued requests.

The `Simulator` advances the clock of each active match and moves finished ones into the finished list, producing a `FinishedMatch` (currently a placeholder win/lose assignment). Both `Platform` and `Simulator` remain strategy-agnostic; all approach-specific logic lives in the strategy.

## UI: `ui/`

The display is a [Textual](https://github.com/Textualize/textual) application (`ui/app.py`) matching the mockup in `docs/ui.md`:

- a header showing the strategy config summary, version and seed;
- a scrolling **event feed** (`ui/widgets.py` → `EventFeed`, a `RichLog`) of generated/queued/matched/finished events;
- a **Platform / State** panel (queue, active matches, tick, wall-clock sim time);
- an **Analytics** panel (placeholders);
- a status bar showing run state, speed multiplier and keybindings.

A tick timer (interval `BASE_TICK_SECONDS / speed`) drives `harness.step()`; the resulting `SimSnapshot` updates reactive widget attributes which repaint the panels. Keybindings: `Space` pause/resume, `j`/`k` double/halve the speed multiplier (min `×1`), `q` quit.

## State & Models: `core/`

- `models.py` — the shared data models: `Player`, `MatchRequest`, `ActiveMatch`, and `FinishedMatch`, plus feature keys (e.g. latency, region) and the `Region` enum.
- `state.py` — `PlatformState`, a runtime container holding the player database, the matchmaking queue, and active/finished matches. It is shared between the platform and the harness.
- `snapshot.py` — `SimSnapshot`, the read-only view of one sim step handed to the display layer.

## Testing

- Headless sim-loop tests (`tests/unit_tests/matchmaking_tests/harness_test.py`) drive `SimHarness` and assert invariants without Textual.
- UI integration tests (`tests/integration_tests/ui_integration_test.py`) boot the Textual app via `App.run_test()` to verify the tick loop, reactive panels, and keybindings end-to-end in a headless terminal.

## General Design Notes

- Each approach expects its own set of player features (e.g. skill level, queue time) and request features (e.g. latency/ping). Keeping the platform generalisable means ensuring the data a generator produces carries the features the selected strategy expects.
- Configuration is intended to be approachable: matchmaking is selectable both via command-line arguments (`--strategy`) and via interactive prompts at startup, so the application can be used without consulting help text or man pages.
- The sim/display split (SimHarness + SimSnapshot) keeps the simulation testable and the TUI swappable; headless mode exercises the same sim path.
