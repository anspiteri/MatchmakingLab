# Architecture

## Overview

MatchmakingLab is a CLI-driven platform for prototyping and analysing different matchmaking approaches. The codebase is organised into five areas under `src/matchmakinglab/`:

- `core/` — shared data models, runtime state, and the read-only `SimSnapshot`
- `matchmakers/` — matchmaking approaches (strategy pattern)
- `platform/` — platform orchestration, match simulation, and the `SimHarness` facade
- `ui/` — the Textual TUI (app, event feed, stat panels, leaderboard)
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

- **Interactive guided setup**, which prompts for strategy selection, its sub-config, and the simulation setup.
- **Promptless boot** via `--strategy <name> <config...>` (sub-config given positionally) or `--default` (defaults).
- **Headless mode** via `--headless --ticks N`, which drives the `SimHarness` without the TUI and logs per-tick stats to stdout.
- **Seeding** via `--seed N`, plumbed through to the harness.
- **Simulation setup** via `--players N` and `--requests MIN:MAX`, which are also asked for in the guided setup.

After setup, the CLI builds a `SimHarness` from the factory-produced platform and generator, then either runs the textual TUI (`ui/app.py`) or the headless loop.

### Two kinds of configuration
Strategy sub-config (which candidate-generation and optimisation method Bradley-Terry uses) is *positional* and enum-only, because it is inherently strategy-specific and the CLI generates its flags from each strategy's own declaration. Simulation setup (population size, arrival rate) is *flag-based* and is the same for every strategy, so it is declared once in `SIM_CONFIG` rather than inside a strategy's sub-config — adding a second approach would otherwise mean duplicating both options.

That list is the single source for the two setup options on **both** surfaces: the `--players` / `--requests` flags and the guided-setup questions are generated from it, so an option cannot appear on one and be missing from the other. Precedence is flag → prompt → default, and a flag suppresses its own question rather than asking a question it has already answered.

Both options are cross-validated at startup rather than per tick: the widest arrival batch must fit in the population, since the generator can only hand out as many distinct new players as its pool holds and asks for exactly that many on the first tick. Without this check a `--players 8 --requests 1:50` run would die on tick one with a bare `ValueError` from inside the generator.

## Simulation boundary: `platform/sim_harness.py`

The `SimHarness` is the single point of contact between the simulation and the display layer. It **owns** the full runtime composition — `RequestGenerator`, `Platform`, `Simulator`, and `PlatformState` — so the UI never reaches into sim internals. It exposes:

- `step() -> SimSnapshot` — advance one tick (generate → enqueue → `platform.tick` → simulate) and return a read-only snapshot.
- `set_paused(paused: bool)` — start or stop the run clock. The TUI calls this on pause and resume; a headless run never does.
- `SimSnapshot` (`core/snapshot.py`) — a plain dataclass with derived facts only (queue/active/finished counts, tick, wall-clock sim seconds, request rate, a list of feed event lines, and a ranked top-100 `leaderboard`).
- `last_snapshot` — the most recent `SimSnapshot`, kept so a caller holding the harness can read back the newest tick without taking a second one and perturbing the run.

### The two clocks

`sim_seconds` is real wall-clock run time: how long the simulation has actually been going. It deliberately does not depend on how fast it is being ticked, so a run left going overnight reads however long it was left for, and the speed multiplier only changes how many ticks fit inside that span. It excludes paused time, and the clock starts on the first `step()` so a freshly booted run reads `0.0` rather than its own startup cost.

Excluding pauses needs the app to say so — the harness cannot see the TUI's own pause, and a pause produces no steps, so measuring the gap between steps would bank the entire pause into the next tick. `set_paused` exists for that and is idempotent, because a caller reporting a state it is already in must not count the span twice.

`request_rate` is average arrivals per real second over the run so far: total requests divided by `sim_seconds`. It is a genuine throughput figure and moves with the speed multiplier, which is correct — at 8x the run really is putting more requests through each real second. Note what it is *not*: a property of the matchmaking. With a 10:50 arrival range it settles near 150/s at 1x, and the same run on a faster machine with the same tick interval reports the same number, because the rate is per real second rather than per tick.

### Leaderboard

`SimHarness._leaderboard()` turns the live player database into ranked rows, so the ranking is computed where the full population is in hand and reaches the display as data rather than as state the UI has to sort itself.

Ranking is by estimated rating descending, then wins descending, then username ascending. The last two keys exist because every player starts at exactly the base rating: without a total order, the flat opening of a run reshuffles every tick and differs between runs of the same seed, and the top rows become unreadable. Rows are capped at `LEADERBOARD_MAX_ROWS = 100` and selected with `heapq.nsmallest`, measured at 0.12ms for 500 players and 0.56ms at 5000 against a ~1.9ms tick.

Each row carries `est. skill` and `true skill` side by side. `TRUE_SKILL_KEY` is otherwise invisible to the simulation, and putting it in the snapshot is a display decision only: nothing in the matching or rating path reads it.

Because the display only depends on this stable snapshot surface, `Platform`, `Simulator` and `RequestGenerator` can be refactored freely beneath the boundary.

### Arrival rate
Each tick draws how many requests to generate, from an inclusive range (`request_range`, default 10–50) or from a fixed `requests_per_step` when one is given.

The range's minimum may be 0, so a tick can generate nothing. Nothing downstream divides by the arrival count, so an empty batch is an ordinary tick that costs the players it would have sent out to play and little else; `0:50` models arrivals in lulls, which a range starting high cannot express. The draw happens in the harness rather than in a generator, because arrival rate is a property of the simulated world rather than of any one matchmaker: every strategy gets it without its generator knowing, and `generate_requests(n, db)` stays honest about its "give me exactly n" contract.

Two measured caveats, both of which shaped the defaults:

- **A wider range varies load, not queue depth.** The greedy matcher drains whatever it is handed within the tick, so at 500 players the queue sits near empty at any arrival rate tried, up to 40–120. What the range actually changes is the per-player match count over a run, which is what the rating calibration responds to.
- **Dispersion responds to matches played, not ticks.** Holding the range at 10–50 and varying population and ticks, the estimated spread tracks √(matches per player) almost exactly — the ratio `spread / √matches` sits at 0.08–0.11 across every configuration measured. So a long run or a high arrival rate both push dispersion up, and 500 players at 4000 ticks reaches 1.64x where 150 players at 2000 reached 1.03x.

### Seeding
`--seed` is plumbed to the platform (hidden-skill draws), the simulator (match outcomes), the generator (who queues, with what latency and region), and a fourth stream for arrival counts. All three components take the seed independently, so each is reproducible on its own. Arrival counts draw from their **own** stream rather than the main seed, so introducing a request range does not shift the draws the platform and simulator already make — the player abilities and match outcomes of a run stay comparable as the arrival rate is varied.

This matters because every calibration number in `docs/matchmaking-implementations.md` is a seeded measurement. Before the generator was seeded, `--seed` varied between identical invocations while the tests all passed, because each test happened to hand the generator the same seed the harness was given. A generator built with its own seed keeps it, mirroring `Platform.use_rng`.

## Matchmaking Engine: `matchmakers/`

### Strategy pattern
Different matchmaking approaches are implemented using a **strategy design pattern**: each approach lives in its own package under `matchmakers/` (currently `bradley_terry/`) and implements the abstract `MatchmakingStrategy` base class. This modularises the approaches while keeping a single generalisable `Platform`.

A strategy defines the full matchmaking lifecycle (see `base_strategy.py`):

- `setup_player_features()` — initialise player state (e.g. a base skill rating) when a player first joins.
- `run_algorithm(queue_snapshot)` — given the queued requests, return the matches to form and the players still waiting.
- `update_player_features(finished_match)` — update player state from completed match results, closing the feedback loop.

Bradley-Terry's rating is a float and its update is multiplicative — a constant step on `log(rating)`, which conserves the product of a matched pair. Both are load-bearing for the reported rating scale; see [matchmaking implementations](./matchmaking-implementations.md).

### Request generators
Each approach also expects specific input data (player features and request features). A coupled `RequestGenerator` (see `base_generator.py`) is responsible for producing that data. Generators are tightly coupled to their approach because the data must match what the strategy consumes.

A generator draws who queues and with what latency and region, so it accepts a source of randomness via `use_rng`, called by the harness. As with `Platform.use_rng`, the no-op default means a generator that does not draw needs no change, and a generator built with its own seed keeps it. `BradleyTerryGenerator(player_count=N)` holds one account per pool entry, which makes population size a hard ceiling on how many distinct players can ever exist in a run — the factory takes it as an argument rather than owning it, since it is a property of the simulated world rather than of the approach.

### Strategy <-> Generator coupling: the factory
Because generators and strategies are tightly coupled, a `MatchmakerFactory` (see `factory.py`) builds them together so they are always configured consistently. Each strategy provides a factory — currently `BradleyTerryFactory` — which constructs a `Platform` configured with the strategy and the matching generator.

## Platform: `platform/`

The `Platform` is the single generalisable harness that runs a strategy against a game state. It:

- assigns players to the matchmaking queue (`add_to_matchmaking_queue`), initialising their feature set via the strategy on first join;
- advances the simulation one step each `tick`, which:
  1. runs the strategy's `run_algorithm` to form matches and leave the rest queued (mutating the shared queue in place),
  2. updates player features from finished matches,
  3. increments the wait time of still-queued requests.

The `Simulator` plays out each active match one round per tick and moves finished ones into the finished list. Each round is decided by a **match outcome model** (`platform/outcome.py`) — an injectable object that returns the probability a given team wins a round, given the teams and an rng:

- `TrueSkillOutcome` (the default) decides from each player's hidden `true_skill`. This is the honest model: results follow real ability, so a good matchmaker can be measured against it.
- `RatingOutcome` decides from `skill_rating`, i.e. from the matchmaker's own current estimate.

Two implementations of the same interface, differing only in what they read, make it cheap to ask what a matchmaker would do if it were right. The simulator also runs the race — each tick plays a round, awards the point, and finishes the match when a side reaches `POINTS_TO_WIN` (3). With one point per round some side always gets there first, so match length is bounded at 5 rounds by the arithmetic and needs no duration cap, and there is no draw to represent.

Both `Platform` and `Simulator` remain strategy-agnostic; all approach-specific logic lives in the strategy. The hidden truth and the outcome model are both simulation-side concerns, deliberately placed so the strategy cannot see either.

## UI: `ui/`

The display is a [Textual](https://github.com/Textualize/textual) application (`ui/app.py`) laid out in `docs/ui.md`:

- a header showing the strategy config summary, version and seed;
- a scrolling **event feed** (`ui/widgets.py` → `EventFeed`, a `RichLog`) of generated/queued/matched/finished events;
- a **Platform / State** panel (queue, active matches, tick, wall-clock sim time);
- an **Analytics** panel, in two halves: throughput (matches, avg wait, avg rounds, request rate) above, and match *quality* below — favourite win rate, rating accuracy, and estimated/true spread;
- a **Leaderboard** panel (`ui/widgets.py` → `LeaderboardPanel`, a `DataTable`): the top 100 players by estimated rating, as a scrolling table of rank, name, `est. skill`, `true skill`, W-L and region. `DataTable` is itself a `ScrollView`, so the panel needs no scroll wrapper — and it only builds the rows currently on screen, so a hundred rows do not cost a hundred repaints per tick;
- a status bar showing run state, speed multiplier and keybindings.

A tick timer (interval `BASE_TICK_SECONDS / speed`) drives `harness.step()`; the resulting `SimSnapshot` updates reactive widget attributes which repaint the panels. Keybindings: `Space` pause/resume, `j`/`k` double/halve the speed multiplier (min `×1`), `q` quit.

## State & Models: `core/`

- `models.py` — the shared data models: `Player`, `MatchRequest`, `ActiveMatch`, `FinishedMatch`, and `LeaderboardEntry`, plus feature keys (e.g. latency, region, and `TRUE_SKILL_KEY`) and the `Region` enum. `ActiveMatch` carries the running `score_A`/`score_B`; `Player` carries both the estimated `skill_rating` the strategy reads and the hidden `true_skill` it never sees. Neither the model nor the platform constrains a strategy's feature values to be integers — a strategy whose update needs fractional values should not have to round them away.
- `state.py` — `PlatformState`, a runtime container holding the player database, the matchmaking queue, and active/finished matches. It is shared between the platform and the harness.
- `snapshot.py` — `SimSnapshot`, the read-only view of one sim step handed to the display layer.

## Testing

- Headless sim-loop tests (`tests/unit_tests/matchmaking_tests/harness_test.py`) drive `SimHarness` and assert invariants without Textual, including the arrival-rate range, the seed plumbing described above, and the leaderboard's ordering, cap and tie-breaks. The ordering test recomputes the expected top slice straight from `PlatformState` rather than trusting the sort, so a sort by the wrong column or in the wrong direction fails even though the rows still look plausible.
- Rating-system tests (`tests/unit_tests/matchmaking_tests/bt_class_test.py`) cover the update arithmetic, that the population geometric mean stays at the base rating, and that the estimated spread stays within a loose bound of the truth's. The last two run real simulations, so they are the slower tests in the suite; each was verified to fail against a deliberately broken update.
- UI integration tests (`tests/integration_tests/ui_integration_test.py`) boot the Textual app via `App.run_test()` to verify the tick loop, reactive panels, keybindings, and the leaderboard panel — including that its table actually scrolls — end-to-end in a headless terminal.

## General Design Notes

- Each approach expects its own set of player features (e.g. skill level, queue time) and request features (e.g. latency/ping). Keeping the platform generalisable means ensuring the data a generator produces carries the features the selected strategy expects.
- Configuration is intended to be approachable: matchmaking is selectable both via command-line arguments (`--strategy`) and via interactive prompts at startup, so the application can be used without consulting help text or man pages.
- The sim/display split (SimHarness + SimSnapshot) keeps the simulation testable and the TUI swappable; headless mode exercises the same sim path.
