# Architecture

## Large Scale


## Matchmaking Engine: '/matchmakers'
### Strategy pattern for different matchmaking approaches
- The matchmaking engine is implemented using a strategy design pattern for different matchmaking approaches.
- This was chosen to accommodate and modularise the different approaches while maintaining a single generalisable platform.

### Idea: Template-method for base algorithm: 'run_algorithm'
- wait for the implementation of a few other approaches to determine whether this is ideal.

## General Notes to Find a Home
Each approach expects it's own set of player features (skill levels, queue time) and request features (ping, to work on) so one of the challenges with making the backend generalisable was ensuring that the data generated produced features that the selected approach expects.

Either-way, because of the tight-coupling between the data generators and the matchmaking approaches, the strategy pattern allows me to modularise each pattern with a single platform, and then configure 

For usability experience I wanted to make the matchmaking approach configurable not just via command line arguments but also potentially at run-time via prompts at startup. This just allows use of the application without needing to look at any help prompts or man pages.
