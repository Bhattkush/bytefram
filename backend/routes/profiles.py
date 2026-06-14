from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.schemas import (
    PredictionHistoryItem,
    ProfileResponse,
    ProfileUpsertRequest,
)
from backend.services.database import (
    get_prediction_history,
    get_profile,
    upsert_farmer_profile,
    upsert_user,
)

router = APIRouter(prefix="", tags=["Profiles"])


@router.post("/profile", response_model=ProfileResponse)
def upsert_profile(request: ProfileUpsertRequest) -> ProfileResponse:
    upsert_user(
        user_id=request.user.user_id,
        name=request.user.name,
        phone_or_email=request.user.phone_or_email,
        language=request.user.language,
        location=request.user.location,
    )
    upsert_farmer_profile(
        farmer_id=request.farmer.farmer_id,
        user_id=request.farmer.user_id,
        land_area=request.farmer.land_area,
        soil_type=request.farmer.soil_type,
        preferred_crops=request.farmer.preferred_crops,
    )
    data = get_profile(request.user.user_id)
    if not data:
        raise HTTPException(status_code=500, detail="Profile could not be loaded after upsert.")
    return ProfileResponse(user=data["user"], farmer=data["farmer"])


@router.get("/profile/{user_id}", response_model=ProfileResponse)
def get_profile_endpoint(user_id: str) -> ProfileResponse:
    data = get_profile(user_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"No profile found for user_id '{user_id}'.")
    return ProfileResponse(user=data["user"], farmer=data["farmer"])


@router.get("/predictions/history/{user_id}", response_model=list[PredictionHistoryItem])
def prediction_history_endpoint(user_id: str, limit: int = 20) -> list[PredictionHistoryItem]:
    history = get_prediction_history(user_id=user_id, limit=limit)
    items: list[PredictionHistoryItem] = []
    for row in history:
        items.append(
            PredictionHistoryItem(
                prediction_id=row["prediction_id"],
                user_id=row["user_id"],
                model_type=row["model_type"],
                crop=row["crop"],
                district=row["district"],
                season=row["season"],
                predicted_value=row["predicted_value"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        )
    return items

