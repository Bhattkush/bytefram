"""
Smart Recommendation Route — The Main API Endpoint
=====================================================
POST /recommend
  Input:  {lat, lon, land_size, season?, soil?, irrigated?, profit_mode?}
  Output: Full crop recommendation with yield, profit, risk, reasons

GET /health/model
  Output: Model health status
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.schemas import (
    AlertItem,
    ConfidenceExplanation,
    ConfidenceFactor,
    ErrorResponse,
    ExplanationDetail,
    ModelHealthResponse,
    RecommendationItem,
    RecommendSummary,
    RiskDetail,
    SmartRecommendRequest,
    SmartRecommendResponse,
)
from backend.services.location_service import resolve_district_from_coords
from backend.services.model_service import (
    get_model_health,
    recommend_for_location,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Smart Recommendations"])


# ── Helper builders ───────────────────────────────────────────────────────────

def _build_recommendations(raw_crops: list[dict[str, Any]]) -> list[RecommendationItem]:
    """Convert raw pipeline dicts into typed RecommendationItem objects."""
    items: list[RecommendationItem] = []
    for c in raw_crops:
        # Build typed RiskDetail if present
        risk_obj: RiskDetail | None = None
        rd = c.get("risk_detail")
        if isinstance(rd, dict):
            try:
                risk_obj = RiskDetail(
                    overall=rd.get("overall", "Low Risk"),
                    risk_score=float(rd.get("risk_score", 0.0)),
                    drought_risk=rd.get("drought_risk", "None"),
                    heat_risk=rd.get("heat_risk", "None"),
                    frost_risk=rd.get("frost_risk", "None"),
                    flood_risk=rd.get("flood_risk", "None"),
                    soil_risk=rd.get("soil_risk", "None"),
                    ndvi_risk=rd.get("ndvi_risk", "None"),
                    off_season_risk=rd.get("off_season_risk", "None"),
                    yield_confidence=float(rd.get("yield_confidence", 1.0)),
                    confidence_level=rd.get("confidence_level", "High"),
                )
            except Exception:
                pass

        # Build typed ExplanationDetail if present
        expl_obj: ExplanationDetail | None = None
        ex = c.get("explanation")
        if isinstance(ex, dict):
            try:
                expl_obj = ExplanationDetail(
                    headline=ex.get("headline", ""),
                    farmer_tip=ex.get("farmer_tip", ""),
                    factors=ex.get("factors", []),
                    key_limiting_factor=ex.get("key_limiting_factor", "none"),
                    confidence_level=ex.get("confidence_level", "Medium"),
                    soil_score=int(ex.get("soil_score", 50)),
                    ndvi_impact=ex.get("ndvi_impact", "neutral"),
                )
            except Exception:
                pass

        crop_name = c.get("crop_name", "Unknown")
        suitability_score = float(c.get("suitability_score", 0.0))

        # Resolve backward-compat risk_confidence string
        risk_confidence: str = c.get("risk_confidence", "")
        if not risk_confidence and isinstance(rd, dict):
            risk_confidence = rd.get("overall", "Low Risk")
        if not risk_confidence:
            risk_confidence = "Low Risk"

        try:
            items.append(RecommendationItem(
                crop=crop_name,
                crop_name=crop_name,
                category=c.get("category", "Other"),
                suitability=suitability_score,
                suitability_score=suitability_score,
                yield_per_hectare=float(c.get("yield_per_hectare", 0.0)),
                total_yield_tonnes=float(c.get("total_yield_tonnes", 0.0)),
                display_yield=c.get("display_yield", ""),
                production_level=c.get("production_level", ""),
                market_price_per_tonne=c.get("market_price_per_tonne"),
                estimated_profit_inr=c.get("estimated_profit_inr"),
                display_profit=c.get("display_profit"),
                profit_confidence=c.get("profit_confidence"),
                composite_score=c.get("composite_score"),
                risk=risk_obj,
                risk_confidence=risk_confidence,
                explanation=expl_obj,
                reason=c.get("reason", ""),
            ))
        except Exception as exc:
            logger.warning("Skipping malformed crop entry (%s): %s", crop_name, exc)

    return items


def _build_confidence_explanation(raw: dict[str, Any] | None) -> ConfidenceExplanation | None:
    if not isinstance(raw, dict):
        return None
    try:
        factors = [
            ConfidenceFactor(
                factor=f.get("factor", ""),
                status=f.get("status", "~"),
                detail=f.get("detail", ""),
            )
            for f in raw.get("factors", [])
        ]
        return ConfidenceExplanation(
            score=int(raw.get("score", 0)),
            rating=raw.get("rating", ""),
            color=raw.get("color", "yellow"),
            factors=factors,
        )
    except Exception:
        return None


def _build_summary(raw: dict[str, Any] | None) -> RecommendSummary | None:
    if not isinstance(raw, dict):
        return None
    try:
        return RecommendSummary(
            best_crop=raw.get("best_crop", ""),
            expected_yield=raw.get("expected_yield", ""),
            suitability=raw.get("suitability", "0%"),
            overall_risk=raw.get("overall_risk", "Unknown"),
            display_profit=raw.get("display_profit", ""),
        )
    except Exception:
        return None


def _build_alerts(raw: list | None) -> list[AlertItem]:
    if not isinstance(raw, list):
        return []
    items: list[AlertItem] = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        try:
            items.append(AlertItem(
                severity=a.get("severity", "info"),
                icon=a.get("icon", "ℹ️"),
                title=a.get("title", ""),
                action=a.get("action", ""),
            ))
        except Exception:
            pass
    return items


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/recommend",
    response_model=SmartRecommendResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
    summary="Get crop recommendations from GPS coordinates",
    description=(
        "Send your location (lat/lon) and the system automatically:\n"
        "1. Finds your nearest Gujarat district\n"
        "2. Fetches seasonal climate data\n"
        "3. Runs ML model for all feasible crops\n"
        "4. Returns ranked recommendations with yield, profit, and risk"
    ),
)
def smart_recommend(request: SmartRecommendRequest) -> SmartRecommendResponse | ErrorResponse:
    """Main recommendation endpoint — auto-fetch everything from location."""

    # 1. Validate coordinates make sense
    location = resolve_district_from_coords(request.lat, request.lon)
    if location["is_outside_gujarat"]:
        logger.warning("Request from outside Gujarat: %s", location["warning"])

    # 2. Build soil dict from optional input
    soil: dict[str, float] | None = None
    if request.soil:
        soil_data = request.soil.model_dump(exclude_none=True)
        if soil_data:
            soil = soil_data

    # 3. Run full pipeline
    try:
        result = recommend_for_location(
            lat=request.lat,
            lon=request.lon,
            land_size=request.land_size,
            season=request.season,
            soil=soil,
            irrigated=request.irrigated,
            profit_mode=request.profit_mode,
            top_n=request.top_n,
        )

        # Check for error response from ML pipeline
        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Prediction failed"),
            )

        # Add location context
        if location.get("warning"):
            result["location_warning"] = location["warning"]

        # 4. Build typed response — map raw dicts to Pydantic models
        raw_crops: list[dict[str, Any]] = result.get("top_recommended_crops", [])

        return SmartRecommendResponse(
            status=result.get("status", "ok"),
            # ── Location & context ──────────────────────────────────────────
            location=result.get("location"),
            district=result.get("district"),
            season=result.get("season"),
            land_area_hectares=result.get("land_area_hectares"),
            irrigated=result.get("irrigated"),
            mode=result.get("mode"),
            input_coordinates=result.get("input_coordinates"),
            location_warning=result.get("location_warning"),
            # ── At-a-glance ─────────────────────────────────────────────────
            summary=_build_summary(result.get("summary")),
            one_line_decision=result.get("one_line_decision"),
            # ── Confidence ──────────────────────────────────────────────────
            confidence=result.get("confidence"),
            confidence_explanation=_build_confidence_explanation(
                result.get("confidence_explanation")
            ),
            # ── Planning layer ───────────────────────────────────────────────
            insight=result.get("insight"),
            advice=result.get("advice"),
            comparison=result.get("comparison"),
            # ── Recommendations (typed) ──────────────────────────────────────
            recommendations=_build_recommendations(raw_crops),
            top_recommended_crops=raw_crops,        # backward-compat raw
            avoid_crops=result.get("avoid_crops", []),
            crops_evaluated=result.get("crops_evaluated", 0),
            crops_filtered_out=result.get("crops_filtered_out", 0),
            # ── Alerts ──────────────────────────────────────────────────────
            alerts=_build_alerts(result.get("alerts")),
            risk_alerts=_build_alerts(result.get("risk_alerts")),
            # ── Weather ─────────────────────────────────────────────────────
            weather_summary=result.get("weather_summary"),
            weather_source=result.get("weather_source"),
            live_conditions=result.get("live_conditions"),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in /recommend")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to generate recommendations. Please try again. ({type(exc).__name__})",
        ) from exc


@router.get(
    "/health/model",
    response_model=ModelHealthResponse,
    summary="Check ML model health",
)
def model_health() -> ModelHealthResponse:
    """Check if the ML model is loaded and ready for predictions."""
    info = get_model_health()
    return ModelHealthResponse(**info)


@router.get(
    "/location/resolve",
    summary="Resolve GPS coordinates to Gujarat district",
    description="Test endpoint to see which district your coordinates resolve to.",
)
def resolve_location(lat: float, lon: float) -> dict[str, Any]:
    """Resolve GPS coordinates to nearest Gujarat district."""
    return resolve_district_from_coords(lat, lon)
