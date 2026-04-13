from fastapi import APIRouter

from app.api.general import router as general_router


router = APIRouter()
router.include_router(general_router)
