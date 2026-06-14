from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from backend.config import settings
from ML.src.inference import SmartFarmingModelHub
from ML.src.suggestion_engine import FarmerDecisionSystem

logger = logging.getLogger(__name__)


# ── Singletons ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_model_hub() -> SmartFarmingModelHub:
    """Singleton for the raw ML model hub (yield predictions)."""
    hub = SmartFarmingModelHub(models_dir=settings.resolved_model_dir)
    hub.load()
    return hub


@lru_cache(maxsize=1)
def get_decision_system() -> FarmerDecisionSystem:
    """Singleton for the full decision pipeline (recommendations)."""
    system = FarmerDecisionSystem()
    return system


# ── Yield Prediction (single crop) ────────────────────────────────────────────

def predict_yield(payload: dict[str, Any]) -> float:
    """Predict yield for a single crop. May raise on bad input."""
    return get_model_hub().predict_yield(payload)


def predict_yield_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Predict yield — NEVER raises. Returns dict with status."""
    return get_model_hub().predict_yield_safe(payload)


# ── Crop Recommendation (multi-crop ranking) ──────────────────────────────────

def recommend_crops(payload: dict[str, Any], top_k: int = 3) -> dict[str, Any]:
    """Full recommendation pipeline through FarmerDecisionSystem.

    Takes raw weather/location payload and returns ranked crop suggestions.
    """
    system = get_decision_system()

    # Map the flat API payload to FarmerDecisionSystem.recommend() args
    city = payload.get("District", payload.get("district", "Ahmedabad"))
    district = payload.get("District", payload.get("district"))
    season_hint = payload.get("Season", payload.get("season"))

    soil_keys = ["N", "P", "K", "pH", "Organic_Carbon"]
    soil = {}
    for key in soil_keys:
        val = payload.get(key) or payload.get(key.lower())
        if val is not None:
            try:
                soil[key] = float(val)
            except (TypeError, ValueError):
                pass

    result = system.recommend_safe(
        city=city,
        district=district,
        soil=soil or None,
        top_n=top_k,
        land_area_hectares=float(payload.get("land_area_hectares", 1.0)),
        irrigated=bool(payload.get("irrigated", False)),
        profit_mode=bool(payload.get("profit_mode", False)),
    )

    return result


# ── Recommend for Location (lat/lon auto-fetch) ──────────────────────────────

def recommend_for_location(
    lat: float,
    lon: float,
    land_size: float = 1.0,
    season: str | None = None,
    soil: dict[str, float] | None = None,
    irrigated: bool = False,
    profit_mode: bool = False,
    top_n: int = 3,
) -> dict[str, Any]:
    """Full pipeline: lat/lon → district → climate → ML → ranked crops.

    This is the main entry point for the /recommend API endpoint.
    """
    from ML.src.climate_client import resolve_coordinates

    # 1. Resolve lat/lon to nearest Gujarat district
    _lat, _lon, district, is_fallback = resolve_coordinates(
        city="", district=None
    )
    # Actually use the provided coordinates to find the nearest district
    district = _find_nearest_district(lat, lon)

    system = get_decision_system()

    result = system.recommend_safe(
        city=district,
        district=district,
        soil=soil,
        top_n=top_n,
        land_area_hectares=land_size,
        irrigated=irrigated,
        profit_mode=profit_mode,
    )

    # Attach the original coordinates to the response
    if isinstance(result, dict):
        result["input_coordinates"] = {"lat": lat, "lon": lon}

    return result


def _find_nearest_district(lat: float, lon: float) -> str:
    """Find the nearest Gujarat district to the given coordinates using Haversine."""
    import math
    from ML.src.constants import DISTRICT_COORDINATES

    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    nearest = "ahmedabad"
    min_dist = float("inf")

    for district, (d_lat, d_lon) in DISTRICT_COORDINATES.items():
        dist = haversine(lat, lon, d_lat, d_lon)
        if dist < min_dist:
            min_dist = dist
            nearest = district

    # Warn if too far from any Gujarat district (>200km)
    if min_dist > 200:
        logger.warning(
            "Coordinates (%.4f, %.4f) are %.0f km from nearest Gujarat district '%s'. "
            "Results may not be accurate.",
            lat, lon, min_dist, nearest,
        )

    return nearest


# ── Disease Risk (simplified — uses rule engine heuristics) ───────────────────

def disease_risk(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute disease risk using rule engine (no separate disease model).

    Since there's no trained disease model, we use suitability + weather
    heuristics from the rule engine.
    """
    try:
        from ML.src.rule_engine import calculate_risk

        crop = payload.get("Crop", payload.get("crop", "Groundnut"))
        weather = {
            "Temperature_Avg": float(payload.get("Temperature_Avg", payload.get("temperature_avg", 25))),
            "Temperature_Min": float(payload.get("Temperature_Min", payload.get("temperature_min", 15))),
            "Temperature_Max": float(payload.get("Temperature_Max", payload.get("temperature_max", 35))),
            "Rainfall": float(payload.get("Rainfall", payload.get("rainfall", 500))),
            "Humidity": float(payload.get("Humidity", payload.get("humidity", 60))),
        }
        irrigated = bool(payload.get("irrigated", False))

        risk_level = calculate_risk(weather=weather, crop=crop, irrigated=irrigated)

        # Map risk level to probability range
        prob_map = {"Low Risk": 0.15, "Medium Risk": 0.45, "High Risk": 0.80}
        risk_prob = prob_map.get(risk_level, 0.5)

        return {
            "risk_probability": risk_prob,
            "risk_level": risk_level.replace(" Risk", ""),
        }
    except Exception as exc:
        logger.exception("Disease risk calculation failed")
        return {
            "risk_probability": 0.5,
            "risk_level": "Unknown",
        }


# ── Model Health ──────────────────────────────────────────────────────────────

def get_model_health() -> dict[str, Any]:
    """Return model status for health-check endpoints."""
    try:
        hub = get_model_hub()
        return hub.get_model_info()
    except Exception as exc:
        return {
            "loaded": False,
            "ready": False,
            "load_error": str(exc),
        }
