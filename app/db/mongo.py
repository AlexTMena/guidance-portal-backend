import os

from fastapi import HTTPException, Request, status
from pymongo import AsyncMongoClient

from app.core.config import APP_ENV, DATABASE_NAME


async def connect_mongodb(app) -> AsyncMongoClient | None:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        if APP_ENV == "production":
            raise RuntimeError("MONGODB_URI is required in production")
        app.state.mongo_client = None
        app.state.database = None
        return None
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000)
    await client.admin.command("ping")
    app.state.mongo_client = client
    app.state.database = client[DATABASE_NAME]
    return client


def get_database(request: Request):
    return getattr(request.app.state, "database", None)


async def require_database(request: Request):
    database = get_database(request)
    if database is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is unavailable")
    return database
