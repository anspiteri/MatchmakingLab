from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.status import HTTP_202_ACCEPTED

from matchmakinglab.platform import Platform
from matchmakinglab.state import PlatformState


class MatchReqDetails(BaseModel):
    username: str
    req_features: dict[str, Any]


app = FastAPI()
platform = Platform()
state = PlatformState()


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Benchmarker running"}


@app.put("/matchmaking_queue", status_code=HTTP_202_ACCEPTED)
async def join_matchmaking_queue(req_details: MatchReqDetails) -> dict[str, str]:

    platform.add_to_matchmaking_queue(
        req_details.username,
        req_details.req_features,
        state,
    )

    return {"message": "queue_success"}
