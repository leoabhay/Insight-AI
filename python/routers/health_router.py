"""routers/health_router.py"""
from fastapi import APIRouter
from database import get_db

router = APIRouter()

@router.get("/health", tags=["health"])
async def health():
    try:
        await get_db().command("ping")
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"
    return {"status": "ok", "db": db_status}