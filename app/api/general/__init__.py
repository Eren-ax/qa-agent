from fastapi import APIRouter

from app.api.general import health, ping


router = APIRouter()
router.include_router(health.router)
router.include_router(ping.router)
