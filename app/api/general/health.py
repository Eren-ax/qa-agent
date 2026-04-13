from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


class HealthResponse(BaseModel):
    status: str = "healthy"


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()
