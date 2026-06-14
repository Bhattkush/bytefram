from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.routes.predictions import router as prediction_router
from backend.routes.profiles import router as profile_router
from backend.routes.recommend import router as recommend_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CropYield AI API — ByteFarm",
    description=(
        "Backend for crop yield prediction and smart recommendations.\n\n"
        "**Main endpoint:** `POST /recommend` — send GPS coordinates, "
        "get crop recommendations with yield, profit, and risk analysis."
    ),
    version="2.0.0",
)

origins = list(settings.allowed_origins) if settings.allowed_origins else ["*"]
allow_credentials = "*" not in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "code": "internal_error",
            "message": "An unexpected error occurred. Please try again.",
        },
    )


@app.on_event("startup")
def on_startup() -> None:
    # 1. Init SQLite database
    try:
        from backend.services.database import init_db
        init_db()
        logger.info("✅ SQLite database initialised at %s", settings.resolved_db_path)
    except Exception as exc:
        logger.error("❌ Database init failed: %s", exc)

    # 2. Preload ML model
    try:
        from backend.services.model_service import get_model_hub
        hub = get_model_hub()
        if hub.is_ready:
            logger.info("✅ ML model preloaded successfully")
        else:
            logger.warning("⚠️ ML model loaded but not ready: %s", hub.load_error)
    except Exception as exc:
        logger.error("❌ Failed to preload ML model: %s (server will still start)", exc)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(recommend_router)
app.include_router(prediction_router)
app.include_router(profile_router)
