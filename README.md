# Matchmaking Service
A conceptual model of an online service for matching players in competitive games.
Built with the purpose of exploring an intersection of two passions: video games & backend systems. The focus of this project is matchmaking algorithms, and modelling the general flow of a competitive match making system with an API, in-memory state, 

For simplicity I've decided to use the following constraints:
- Mocking of player / client requests using python scripts
- No auth or account management
- Simulated / random match results instead of real matches

For more reading check out:
- [Project References](docs/references.md)
- [Roadmap](docs/roadmap.md)

<br>

## Project Structure
```
learning_matchmaking-service/
├── scripts/
|   ├── demo.py
|   └── run.py
├── src/
|   └── matchmaking_service/
|       ├── __init__.py
|       ├── api.py
|       ├── service.py
|       ├── models.py
|       └── state.py
├── tests/
├── .gitignore
├── LICENSE
├── README.md
└── pyproject.toml
```

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

To spin up the server, use run.py in `scripts/`:
`python scripts/run.py`

<br>

## Core Dependencies
This project utilises the following dependencies:
- fastapi for the web backend framework
- uvicorn for running the application server
- setuptools as the backend build system
