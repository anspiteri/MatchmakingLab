# Project Diary
## Backlog
### Important
0.1 Requisites
* finish BT test module ✅
* implement update player features to close loop ✅
* Working vertical slice
	- simulator
	- executable application ✅
		- allow population size and request number to be easily configurable
	- display
		- add player population size to display ✅
		- add basic player info (region, ping, skill-rating, to event feed) ✅
		- add leaderboard tracking
	- accompanying minimal test suites
	- headless mode with logging to files or stdout
	- Request Generator
		- add new player state transitions to codebase ✅
		- change generator to operate over a range of requests instead of a fixed number
		- change feed display to differentiate NEW vs EXISTING requests ✅
* verify module / acceptance testing
	- possibly also create some intuition tests
* polished readme, docs and visual demo / gifs

Future
* refactor platform into sim-harness, have strategy & generator be configured as a part of sim harness or determine specific role of platform
* (**)implement second BT optimisation model

### Not as Important
* double-check completeness of bt match model math component in test suite (21/08/2026)
* double-check and possibly document the bt model match tests, ensuring the tests are flexible to changing weights (21/08/2026)
* assess whether it's worth changing the bt greedy approach to employ a queue-policy that halts matching after a certain time  (24/08/2026)
* think about adjusting the BT skill-rating system to be log-likelihood based (26/08/2026)

## Log
30/09/2026
Made matches actually depend on player skill, which turned out to be the precondition for measuring anything (branch `dev/match-simulation`, 4 commits):

- Gave every simulated player a hidden `true_skill` (uniform 40-160), drawn from the platform's rng at creation and never read by the strategy. The strategy keeps its own `skill_rating` starting at 100. This gives the lab a ground truth to score estimates against.
- Added a `MatchOutcomeModel` interface with two implementations: `TrueSkillOutcome` (honest — results follow real ability) and `RatingOutcome` (circular — results follow the matchmaker's estimate). Two implementations of one interface differing only in what they read make it cheap to ask what a matchmaker would do if it were right.
- Rewrote the simulator, which had been crediting whichever side happened to be listed first. Each tick now plays a round decided by the outcome model, and the match ends when a side reaches 3 points. Consequences worth noting: match length becomes an *output* (measured 4.05 average, bounded 3-5) rather than an independently chosen number, so it is finally worth reading; the duration thresholds are gone because the arithmetic already bounds the race; and with no draws possible there is no draw state for the rating update to handle.
- Halved `LEARNING_RATE` from 10 to 5, measured rather than guessed — see `docs/matchmaking-implementations.md` for the writeup and the numbers.

The measurement work turned up a result I did not expect. The rating update does learn: estimated ratings correlate with hidden truth at 0.843. But the rating *scale* inflates as the run goes on, because the update has no restoring force that catches up as ratings separate, and its step is proportional to the rating itself. The spread of estimates drifts past the spread of the population it is estimating, and where it stops is decided by the learning rate rather than by the real players. Halving the rate is a mitigation, not a fix — 1.5x over-dispersion remains at 2000 ticks. The real correction is to update `log(rating)` instead, which is left as known future work since it means re-deriving the update and the reported scale together.

Deliberately deferred:
- **Log-space ratings.** The structural fix for the above. Not blocking — the lab produces meaningful results while this is a documented distortion, but it should land before rating numbers are compared across approaches.
- **Per-round probability calibration.** `RatingOutcome` currently applies the Bradley-Terry function to a single round, but a round is not a whole match and the per-round probability is not the per-match probability a real player would expect. Guessing a mapping here would be worse than leaving it visibly naive.
- **A loose dispersion guard** — actually landed, in `bt_class_test.py`. Deliberately loose: a smoke alarm for the inflation becoming qualitatively worse, not a pin on today's numbers. Verified it fires on a real regression (learning rate 40 → 2.65x against a 2.5x bound) and passes with room to spare at the current configuration (0.93x).

A caution worth recording: my first attempt at that guard tested the wrong thing. I broke the update to a skill-independent step, expecting correlation with truth to collapse — it did not, because a constant step still accumulates win differential and win differential tracks ability. That variant really does learn. A test only means something once you have watched it fail; the frozen-update control (correlation 0.0) is the one that proves the assertion bites.

09/09/2026
Migrated the display layer from a planned Rich-based live display to a full Textual TUI, and landed the display part of the vertical slice:

- Dropped `rich` from dependencies; added `textual` (v8.x). Rich was declared but never imported anywhere, so this was a fresh build against Textual rather than a migration of existing Rich code.
- Introduced a sim/display boundary: `SimHarness` (owns generator + platform + simulator + state) exposes `step() -> SimSnapshot`. The UI only ever sees snapshots, so Platform/Simulator/RequestGenerator can keep evolving without touching the UI.
- Built the TUI (`matchmakinglab/ui/`) matching `docs/ui.md`: event feed, Platform/State panel, Analytics panel, status bar. Keybindings: Space pause, j/k speed (×2 multiplier), q quit. Wall-clock sim time.
- Added headless mode (`--headless --ticks N`) that drives the same sim path with per-tick logging to stdout — keeps the sim testable without the TUI.
- Fixed two pre-existing sim bugs that blocked the loop: `_match_players` reassigned a local instead of mutating the shared queue (so it never drained), and `run_algorithm` compared MatchRequests against Players when computing remaining (so nothing was ever tired as matched). Also bumped the generator to emit distinct players, and gave the simulator a match clock so matches actually finish.
- Tests: headless sim-invariant tests (unit) + Textual `run_test` UI integration tests. 55 passing; pyright clean; no new ruff violations.

21/08/2026
Spent some time researching and thinking about test approaches. I think for the initial bradley-terry matchmaking tests, I'll split testing into three layers:
1. Unit-testing the correctness of my maths components (bt_probability, latency_cost, etc...)
2. Unit-testing the correctness of my compositional functions (model_match -> which combines math components together)
3. Unit-testing the correctness of my matchmaking assumption (do queue players actually match in the way I expect, or should expect?)

12/08/2026
For the problem of generator and strategy coupling, could use a factory method to configure both components together, and ensure that they never are configured independently. May add some complexity, will have to see how much it actually is.
- Instead of the strategy being a direct parameter to the platform initialiser, create enumerators for different approaches.

For the problem of generalising the platform for different approaches, I've gone with the approach of dictionaries containing approach-specific data as function parameters. This allows for approaches to define their own data in dictionaries, and then perform both key setup during initialisation, and then validation during runtime.

## Ideas
### Project Goal
I've shifted this project to be a prototyping platform instead of a comparator / benchmarking platform because the gold standard for comparison would be live testing with real players. Instead, this project is better suited for analysing conceptual approaches to the matchmaking problem within a real world-like simulator.

[11/08/2026]
However, after beginning the Bradley Terry approach, there may still be room for benchmarking, as there are a number of different ways to optimise within each approach. To be able to see the tangible differences optimisations would make would be worthwhile.

### Deployment
For deployment I think I will have a CLI wrapper over the ASGI server instance. The whole application will be released on the gitub release.
The CLI will allow you to run the simulation with specifiers for matchmaking strategy, simulation size, and log output.

[11/08/2026]
Over the last week or so I've been piecing together the different components of the application.

The overall application will can be a Click CLI application
- Click coordinates the start-up of the ASGI server via uvicorn. Uvicorn coordinates the API via FASTAPI
- Click also coordinates the live display of the server, I've read about 'Rich' being a good option for this.

The build backend will most likely change from setup tools because I'm no longer adding C modules. Uv seems to be the standard.

For deployment, I'm considering hosting an instance of it online, to make toying with it very easy. A complete appimage also makes sense.

The README be both a good overview of the whole project, while also providing a launching point for exploring it
- Each section should have links to deeper diving related content
- Introduce the project with some small background
- It should have gifs of the running project to get a good idea of what the project looks like, and how it works without needing to run it.
- Overview of architecture, and core dependencies.
- Options for running the application
- Options for jumping into the code / development

### Initial Vertical Slice
- client: match request endpoint -> server: creates MatchRequest -> server: adds to state queue
- server: tick every second -> server: run default / basic matchmaking algorithm (runs matchmaking sequentially on one thread) -> server: simulate matches (on a separate thread) -> server: store results & update display

1. What is the best way to coordinate player_features and request_features between client & server.
	- An approach is to keep it general, a player_features dictionary, and a request_features dictionary-- allowing for each approach to work on whichever data it wants but introducing the problem of type errors with mismatched data and algorithm approaches. (can mitigate this with strict type-checking for each algorithm, and possibly graceful failure for non-critical features.)
	- The next question is player state, the player state depends on the results from match simulation and the way that each matchmaking approach stores and interprets player performance... so are we going to start the simulations from a blank slate or try to model an existing system? A blank slate makes it easier to compare and experiment with.
		- That means player features are not sent via the API but should be hosted on the server. New players start with blank features. Simulations update features. This will require a simulation engine. This means that username only is sent to the API.

2. What is the best way to run the TICK loop in the server? How does FASTAPI and Python approach concurrency and parallelism?
	- Experiment with tick timing within uvicorn's event loop. I'll aim for a mostly single threaded execution model:
		- Open HTTP requests for some ms -> run tick() -> open HTTP requests -> run tick()
		- Can experiment with multi-threaded optimisation for tasks within the tick() method depending on runtime.

3. How will data be generated? Data generation is dependent on the matchmaking strategy, as it configures both request features and player features.
	- Request features are validated in an EAFP (easier to ask for forgiveness than permission) approach.
	- Data generator then is coupled with each matchmaking strategy. The next step will be to think about how the app is going to run as a whole.
		- If data is coupled with approaches, meaning that the same dataset cannot be used to compare approaches, then this will affect what metrics I measure and display.
		- How will I compose the generators then? Alongside the matchmakers?

3. How will results be displayed on the client end? TUI.

### TUI
- Decision: using [Textual](https://github.com/Textualize/textual) for the live display (see `docs/ui.md` for the mockup and `src/matchmakinglab/ui/` for the implementation).
- For the TUI display, it could be really interesting to have a live window of the script executing against the API.
- I'm going to try generating fresh data for each run as different approaches operate on their own set of features.
	- It would be good to generate a log then to compare results from different approaches, as well as as a seed for recreating scenarios.
- Useful metrics could be:
	- A rolling display of the server log with API requests
	- A static display of the following stats:
		- queued players
		- running matches (have matches run for a range of ticks (say 30 - 100 depending for ticks that occur say 15 ticks/second))
		- leader-board with player and player features
	- Another static display with server performance statistics
		- TBD

### Datasets
#### Types of Data
- API requests for the demo -> {player_identifier, skill_rating, player_features{x_i | i in X_player_features}, request_features{y_i | i in Y_request_features}}
	- player features would include more detailed statistics on individual player skills & performance
	- request features would include details such as geographical region, latency, time of request, length of current play session
	- It would be a good idea to model based off an existing standard dataset so I can use existing data for training alongside my generated dataset
- For training models -> {}, this would require match statistics, so finding a standard synthetic dataset maybe the best approach.

#### Generating Data
- To generate data for the demo, can look into randomising based on enumerators for discrete fields, and probability based methods for related fields (skill_rating, player features) and fuzzing maybe for player_identifier or just incremental ids.
- I wonder if I could create a algorithm that generates players and server activity at run time?
