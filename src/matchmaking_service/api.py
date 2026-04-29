from fastapi import FastAPI
from matchmaking_service.state import GameState
from matchmaking_service.service import GameService

app = FastAPI()
state = GameState()
service = GameService(state)

@app.get('/')
async def root():
    return {"message": "Backend service running."}

@app.post('/tick')
async def tick():
    service.tick()
