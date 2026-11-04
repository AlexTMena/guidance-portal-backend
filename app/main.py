from fastapi import FastAPI

app = FastAPI(title="Guidance Portal API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
