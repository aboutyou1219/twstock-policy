from __future__ import annotations

from fastapi import FastAPI

from .routes import router

app = FastAPI(title="twstock-policy", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(router, prefix="/api")
