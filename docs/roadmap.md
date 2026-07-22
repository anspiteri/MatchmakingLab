# Roadmap
## Initial Vertical Slice
- Tick endpoint -> Creates MatchRequest -> Adds to GameState queue -> Choose a default / basic matchmaking algorithm -> Simulate matches -> Store results & update display

## Ideas
- Swappable matchmaking algorithms / approaches via Strategy design pattern
- Logging for comparing the above approaches
- Load balancing via multiple containers

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

## Persistence
- For load-balancing and multiple containers, there needs to be persistence across containers, so a database solution like redis might be the right choice

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
