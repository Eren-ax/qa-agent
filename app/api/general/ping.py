from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


class PongResponse(BaseModel):
    status: str = "pong"


@router.get("/ping", response_model=PongResponse)
def ping():
    return PongResponse()
