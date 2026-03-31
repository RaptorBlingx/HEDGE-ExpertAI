"""Mock API — FastAPI application entry point."""

from fastapi import FastAPI

from .routes import router

app = FastAPI(
    title="HEDGE-IoT Mock App Store API",
    version="0.1.0",
    description="Mock API mimicking the HEDGE-IoT App Store for development.",
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-api", "version": "0.1.0"}
