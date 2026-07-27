# Roadmap

## Project Goal
I've shifted this project to be a prototyping platform instead of a comparator / benchmarking platform because the gold standard for comparison would be live testing with real players. Instead, this project is better suited for learning how to turn ideas into code.

## Initial Vertical Slice
- client: match request endpoint -> server: creates MatchRequest -> server: adds to state queue
- server: tick every second -> server: run default / basic matchmaking algorithm (runs matchmaking sequentially on one thread) -> server: simulate matches (on a separate thread) -> server: store results & update display

1. What is the best way to coordinate player_features and request_features between client & server.
	- An approach is to keep it general, a player_features dictionary, and a request_features dictionary-- allowing for each approach to work on whichever data it wants but introducing the problem of type errors with mismatched data and algorithm approaches. (can mitigate this with strict type-checking for each algorithm, and possibly graceful failure for non-critical features.)
	- The next question is player state, the player state depends on the results from match simulation and the way that each matchmaking approach stores and interprets player performance... so are we going to start the simulations from a blank slate or try to model an existing system? A blank slate makes it easier to compare and experiment with.
		- That means player features are not sent via the API but should be hosted on the server. New players start with blank features. Simulations update features. This will require a simulation engine. This means that username only is sent to the API.

2. What is the best way to run the TICK loop in the server? How does FASTAPI and Python approach concurrency and parallelism?
3. What will the default matchmaking approach be? Implement it.
4. How will results be displayed on the client end? TUI.

## Ideas
- Swappable matchmaking algorithms / approaches via Strategy design pattern
- Logging for comparing the above approaches

## Demo
- For the demo, it could be really interesting to have a live display of the script executing against the API.
- This would especially be cool if I could source or generate a large dataset.
- Useful metrics could be:
	- A rolling display of the server log with API requests
	- A static display of the following stats:
		- queued players
		- running matches (have matches run for a range of ticks (say 30 - 100 depending for ticks that occur say 15 ticks/second))
		- leader-board with player and player features
	- Another static display with server performance statistics
		- TBD

## Datasets
### Types of Data
- API requests for the demo -> {player_identifier, skill_rating, player_features{x_i | i in X_player_features}, request_features{y_i | i in Y_request_features}}
	- player features would include more detailed statistics on individual player skills & performance
	- request features would include details such as geographical region, latency, time of request, length of current play session
	- It would be a good idea to model based off an existing standard dataset so I can use existing data for training alongside my generated dataset
- For training models -> {}, this would require match statistics, so finding a standard synthetic dataset maybe the best approach.

### Generating Data
- To generate data for the demo, can look into randomising based on enumerators for discrete fields, and probability based methods for related fields (skill_rating, player features) and fuzzing maybe for player_identifier or just incremental ids.
- I wonder if I could create a algorithm that generates players and server activity at run time?
