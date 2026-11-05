from fastapi import APIRouter, Depends, HTTPException

from app.core.config import APP_ENV
from app.db.mongo import get_database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(database=Depends(get_database)) -> dict[str, str]:
    if database is None and APP_ENV == "production":
        raise HTTPException(status_code=503, detail="Database is unavailable")
    if database is not None:
        try:
            await database.command("ping")
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ok"}
