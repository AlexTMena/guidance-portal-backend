import os

from fastapi import FastAPI

app_env = os.getenv("APP_ENV", "production").lower()
docs_enabled = app_env == "development"

app = FastAPI(
    title="Guidance Portal API",
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
