# Project Diary
## Backlog
### Important
0.1 Requisites
* finish BT test module ✅
* implement update player features to close loop ✅
* Working vertical slice
	- simulator
	- executable application
	- display
	- accompanying minimal test suites
* verify module / acceptance testing
	- possibly also create some intuition tests
* polished readme, docs and visual demo / gifs

Future
* (**)implement second BT optimisation model

### Not as Important
* double-check completeness of bt match model math component in test suite (21/08/2026)
* double-check and possibly document the bt model match tests, ensuring the tests are flexible to changing weights (21/08/2026)
* assess whether it's worth changing the bt greedy approach to employ a queue-policy that halts matching after a certain time  (24/08/2026)
* think about adjusting the BT skill-rating system to be log-likelihood based (26/08/2026)

## Log
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
