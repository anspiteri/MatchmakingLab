from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Benchmarker running"}


@app.post("/matchmaking_queue")
async def join_matchmaking_queue():
    return {"message": "Added to match queue"}
