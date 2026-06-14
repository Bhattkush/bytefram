from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import (
    CropRecommendationRequest,
    CropRecommendationResponse,
    DiseaseRiskRequest,
    DiseaseRiskResponse,
    WeatherAlertRequest,
    WeatherAlertResponse,
    YieldPredictionRequest,
    YieldPredictionResponse,
)
from backend.services.model_service import disease_risk, predict_yield, predict_yield_safe, recommend_crops
from backend.services.weather_service import WeatherServiceError, fetch_weather_and_alerts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Predictions"])


def _payload_from_model_input(data: dict) -> dict:
    payload = {
        "district": data["district"],
        "season": data["season"],
        "year": data["year"],
        "crop": data.get("crop"),
        "temperature_avg": data["temperature_avg"],
        "temperature_min": data["temperature_min"],
        "temperature_max": data["temperature_max"],
        "rainfall": data["rainfall"],
        "humidity": data["humidity"],
        "n": data.get("n"),
        "p": data.get("p"),
        "k": data.get("k"),
        "ph": data.get("ph"),
        "organic_carbon": data.get("organic_carbon"),
        "ndvi_peak": data.get("ndvi_peak"),
    }
    return payload


@router.post("/predict-yield", response_model=YieldPredictionResponse)
def predict_yield_endpoint(request: YieldPredictionRequest) -> YieldPredictionResponse:
    body = request.model_dump()
    result = predict_yield_safe(_payload_from_model_input(body))

    if result.get("status") == "error":
        raise HTTPException(
            status_code=500,
            detail=result.get("message", "Unable to predict yield. Please try again."),
        )

    return YieldPredictionResponse(
        crop=request.crop,
        district=request.district,
        season=request.season,
        predicted_yield_ton_per_hectare=round(float(result["yield"]), 4),
    )


@router.post("/crop-recommend", response_model=CropRecommendationResponse)
def crop_recommend_endpoint(request: CropRecommendationRequest) -> CropRecommendationResponse:
    try:
        body = request.model_dump()
        result = recommend_crops(_payload_from_model_input(body), top_k=request.top_k)

        # recommend_crops now returns a full dict from FarmerDecisionSystem
        # Extract top crops and format for the API response
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "Recommendation failed"))

        top_crops = result.get("top_recommended_crops", [])
        recommendations = []
        for crop_data in top_crops:
            recommendations.append({
                "crop": crop_data.get("crop_name", "Unknown"),
                "confidence": crop_data.get("suitability_score", 0.0),
            })

        return CropRecommendationResponse(
            district=request.district,
            season=request.season,
            recommendations=recommendations,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Crop recommendation failed")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to generate recommendations. ({type(exc).__name__})",
        ) from exc


@router.post("/disease-risk", response_model=DiseaseRiskResponse)
def disease_risk_endpoint(request: DiseaseRiskRequest) -> DiseaseRiskResponse:
    try:
        body = request.model_dump()
        result = disease_risk(_payload_from_model_input(body))
        return DiseaseRiskResponse(
            crop=request.crop,
            district=request.district,
            risk_probability=result["risk_probability"],
            risk_level=result["risk_level"],
        )
    except Exception as exc:
        logger.exception("Disease risk calculation failed")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to calculate disease risk. ({type(exc).__name__})",
        ) from exc


@router.post("/weather-alert", response_model=WeatherAlertResponse)
def weather_alert_endpoint(request: WeatherAlertRequest) -> WeatherAlertResponse:
    try:
        payload = fetch_weather_and_alerts(
            latitude=request.latitude,
            longitude=request.longitude,
            district=request.district,
        )
        return WeatherAlertResponse(**payload)
    except WeatherServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Weather alert fetch failed")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch weather alerts. ({type(exc).__name__})",
        ) from exc


@router.get("/weather/climate")
def climate_data_endpoint(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
) -> dict:
    """Return seasonal climate normals from Open-Meteo (free, no API key needed).

    Used by the app when OPENWEATHER_API_KEY is not configured.
    """
    try:
        from backend.services.model_service import _find_nearest_district
        from ML.src.suggestion_engine import FarmerDecisionSystem
        import math

        district = _find_nearest_district(lat, lon)

        system = FarmerDecisionSystem()
        season = system._detect_season()
        climate = system._get_climate(district, season)

        current_month = __import__("datetime").datetime.now().month
        season_name = (
            "Kharif" if 6 <= current_month <= 10
            else "Rabi" if current_month >= 11 or current_month <= 2
            else "Summer"
        )

        return {
            "district": district,
            "season": season_name,
            "source": "Open-Meteo (seasonal normals)",
            "current": {
                "temperature": round(climate.get("Temperature_Avg", 28.0), 1),
                "temperature_min": round(climate.get("Temperature_Min", 20.0), 1),
                "temperature_max": round(climate.get("Temperature_Max", 36.0), 1),
                "humidity": round(climate.get("Humidity", 65.0), 1),
                "rainfall": round(climate.get("Rainfall", 0.0), 1),
                "description": f"Seasonal normals for {district.title()} ({season_name})",
            },
            "alerts": _climate_alerts(climate),
        }
    except Exception as exc:
        logger.exception("Climate data fetch failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _climate_alerts(climate: dict) -> list[dict]:
    alerts = []
    temp_max = climate.get("Temperature_Max", 30)
    rainfall = climate.get("Rainfall", 0)
    humidity = climate.get("Humidity", 60)

    if temp_max >= 40:
        alerts.append({"severity": "critical", "title": "Extreme Heat", "action": "Increase irrigation frequency during peak hours."})
    elif temp_max >= 35:
        alerts.append({"severity": "warning", "title": "High Temperature", "action": "Monitor crops for heat stress."})

    if rainfall > 200:
        alerts.append({"severity": "warning", "title": "High Rainfall Season", "action": "Ensure field drainage is in place."})
    elif rainfall < 50:
        alerts.append({"severity": "warning", "title": "Low Rainfall Expected", "action": "Plan for supplemental irrigation."})

    if humidity > 80:
        alerts.append({"severity": "warning", "title": "High Humidity", "action": "Watch for fungal disease outbreaks."})

    return alerts
