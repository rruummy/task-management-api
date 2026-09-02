from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.comments import router as comments_router
from app.api.v1.tasks import router as tasks_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(tasks_router)
api_router.include_router(comments_router)