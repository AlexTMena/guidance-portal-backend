from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import DOCS_ENABLED
from app.db.mongo import connect_mongodb


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = await connect_mongodb(app)
    try:
        yield
    finally:
        if client is not None:
            await client.close()


app = FastAPI(
    title="e-Gabay API",
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
    lifespan=lifespan,
)
app.include_router(api_router)
