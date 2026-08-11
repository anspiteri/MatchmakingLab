# Matchmaking Lab
This project seeks to create a platform for prototyping, analysing & learning different matchmaking approaches for competitive online games.

## Background
Match-making services are a core component of match-based competitive video games (League of Legends, Call of Duty, Fortnite, to name a few). At a basic level, these services seek to match queuing players based on features such as skill level, geographical region, latency / ping to servers, and queue time with the goal of optimising engagement and match satisfaction. There has been rich history of approaches and developments to this kind of optimisation problem. To access some of the research that went into this project, see [references](./references/bibliography.md).

I decided to build this project to grow my applied algorithmic skills in the context of backend web systems; this domain requires both in-depth algorithmic thinking, and  production-minded software engineering. Having a background and a lot of time in games like Fortnite and many first-person shooters, this is also a really interesting and fun project area for me.

<br>

## Project Constraints (requires-update)
To focus my time on my desired growth areas I've decided to use the following constraints:
- Mocking of player / client requests using python scripts
- No auth or account management (all api requests are treated as valid)
- Simulated / random match results instead of real matches

Furthermore, the best feedback you can obtain for algorithms affecting real world players is real world feedback. Being a simulated platform, I acknowledge that we cannot obtain that. Therefore, feedback from this platform should be interpreted accordingly.

<br>

## Project Structure
```
MatchmakingLab/
├── docs/
|   ├── architecture.md
|   ├── matchmaking-implementations.md
|   └── project-diary.md
├── references/
|   ├── papers/
|   └── bibliography.md
├── scripts/
|   └── run.py
├── src/
|   └── matchmakinglab/
|       ├── matchmakers/
|       |   ├── bradley_terry/
|       |   |   ├── __init__.py
|       |   |   ├── generator.py
|       |   |   └── strategy.py
|       |   ├── __init__.py
|       |   ├── base_generator.py
|       |   └── base_strategy.py
|       ├── simulator/
|       |   └── __init__.py
|       ├── __init__.py
|       ├── api.py
|       ├── models.py
|       ├── platform.py
|       └── state.py
├── tests/
├── .gitignore
├── LICENSE
├── README.md
└── pyproject.toml
```

<br>

## Architecture (requires-update)
Once architecture is completed, provide a summary of the high-level architecture of the project.

For more details on each module, see [architecture](./docs/architecture.md).

<br>

## Development (requires-update)
### Setting up & using a python environment
For first time use, set up a python environment using:
`python3 -m venv .venv`

Afterwards, use the following to activate the environment when working on the project:
`source .venv/bin/activate`

### Building & running
For building the project into a runnable program use:
`pip install -e ".[dev]"`

To spin up the server, use run.py in `scripts/`:
`python scripts/run.py`
