from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PredictionBaseInput(BaseModel):
    district: str = Field(..., description="District name")
    season: str = Field(..., examples=["Kharif", "Rabi", "Summer"])
    year: int = Field(..., ge=2000, le=2100)
    crop: str | None = None
    temperature_avg: float
    temperature_min: float
    temperature_max: float
    rainfall: float = Field(..., ge=0)
    humidity: float = Field(..., ge=0, le=100)
    n: float | None = None
    p: float | None = None
    k: float | None = None
    ph: float | None = None
    organic_carbon: float | None = None
    ndvi_peak: float | None = None


class YieldPredictionRequest(PredictionBaseInput):
    crop: str
    user_id: str | None = None


class YieldPredictionResponse(BaseModel):
    crop: str
    district: str
    season: str
    predicted_yield_ton_per_hectare: float


class CropRecommendationRequest(PredictionBaseInput):
    top_k: int = Field(default=3, ge=1, le=10)


class CropRecommendationItem(BaseModel):
    crop: str
    confidence: float


class CropRecommendationResponse(BaseModel):
    district: str
    season: str
    recommendations: list[CropRecommendationItem]


class DiseaseRiskRequest(PredictionBaseInput):
    crop: str
    user_id: str | None = None


class DiseaseRiskResponse(BaseModel):
    crop: str
    district: str
    risk_probability: float
    risk_level: str


class WeatherAlertRequest(BaseModel):
    latitude: float
    longitude: float
    district: str | None = None


class WeatherAlert(BaseModel):
    type: str
    message: str
    severity: str


class WeatherAlertResponse(BaseModel):
    latitude: float
    longitude: float
    current: dict[str, Any]
    alerts: list[WeatherAlert]


class UserProfile(BaseModel):
    user_id: str
    name: str
    phone_or_email: str
    language: str = Field(default="English")
    location: str | None = None


class FarmerProfile(BaseModel):
    farmer_id: str
    user_id: str
    land_area: float
    soil_type: str | None = None
    preferred_crops: str | None = None


class ProfileUpsertRequest(BaseModel):
    user: UserProfile
    farmer: FarmerProfile


class ProfileResponse(BaseModel):
    user: UserProfile
    farmer: FarmerProfile


class PredictionHistoryItem(BaseModel):
    prediction_id: int
    user_id: str
    model_type: str
    crop: str | None = None
    district: str
    season: str
    predicted_value: float
    created_at: datetime


# ── Smart Recommendation (auto-fetch pipeline) ──────────────────────────────

class SoilInput(BaseModel):
    """Optional soil data — if not provided, district defaults are used."""
    N: float | None = Field(default=None, description="Nitrogen (kg/ha)")
    P: float | None = Field(default=None, description="Phosphorus (kg/ha)")
    K: float | None = Field(default=None, description="Potassium (kg/ha)")
    pH: float | None = Field(default=None, description="Soil pH (0-14)")
    Organic_Carbon: float | None = Field(default=None, description="Organic Carbon %")


class SmartRecommendRequest(BaseModel):
    """Minimal input for smart recommendation.

    Only lat/lon is truly required — everything else has sensible defaults.
    The backend auto-fetches weather, resolves location, and runs the full pipeline.
    """
    lat: float = Field(..., ge=-90, le=90, description="Latitude (GPS)")
    lon: float = Field(..., ge=-180, le=180, description="Longitude (GPS)")
    land_size: float = Field(default=1.0, ge=0, description="Land area in hectares")
    season: str | None = Field(default=None, description="Season override (Kharif/Rabi/Summer). Auto-detected if not provided.")
    soil: SoilInput | None = Field(default=None, description="Optional soil data")
    irrigated: bool = Field(default=False, description="Does the farmer have irrigation?")
    profit_mode: bool = Field(default=False, description="Rank by profit instead of safety?")
    top_n: int = Field(default=3, ge=1, le=10, description="Number of crops to recommend")
    user_id: str | None = Field(default=None, description="Optional user ID for history tracking")


# ── Crop recommendation — rich detail (per-crop in response) ─────────────────

class RiskDetail(BaseModel):
    """Structured breakdown of risk factors per crop."""
    overall: str                    # "Low Risk" | "Medium Risk" | "High Risk"
    risk_score: float               # 0.0–1.0 composite
    drought_risk: str               # "None" | "Low" | "Medium" | "High"
    heat_risk: str
    frost_risk: str
    flood_risk: str
    soil_risk: str
    ndvi_risk: str
    off_season_risk: str
    yield_confidence: float         # 0.0–1.0
    confidence_level: str           # "Low" | "Medium" | "High"


class ExplanationDetail(BaseModel):
    """Model-importance-aligned explanation for a crop recommendation."""
    headline: str                   # one-sentence technical summary
    farmer_tip: str                 # plain-English for farmers (no jargon)
    factors: list[str]              # ordered factors (P first, then heat, water…)
    key_limiting_factor: str        # dominant constraint code
    confidence_level: str           # "Low" | "Medium" | "High"
    soil_score: int                 # 0–100 weighted nutrient score
    ndvi_impact: str                # "positive" | "neutral" | "negative"


class RecommendationItem(BaseModel):
    """Full per-crop recommendation — exposes everything the pipeline produces."""
    crop: str                       # clean alias (mirrors crop_name)
    crop_name: str
    category: str
    suitability: float              # clean alias (mirrors suitability_score)
    suitability_score: float
    yield_per_hectare: float
    total_yield_tonnes: float
    display_yield: str
    production_level: str
    market_price_per_tonne: float | None = None
    estimated_profit_inr: float | None = None
    display_profit: str | None = None
    profit_confidence: str | None = None    # "High" | "Medium" | "Low" (from price volatility)
    composite_score: float | None = None
    risk: RiskDetail | None = None  # structured risk breakdown
    risk_confidence: str            # backward-compat string label
    explanation: ExplanationDetail | None = None  # structured explanation
    reason: str                     # backward-compat plain-text reason


# ── Summary block ─────────────────────────────────────────────────────────────

class RecommendSummary(BaseModel):
    """At-a-glance summary — frontend can render a hero card from this alone."""
    best_crop: str
    expected_yield: str
    suitability: str                # e.g. "72%"
    overall_risk: str               # e.g. "Medium Risk"
    display_profit: str             # e.g. "₹18,400"


# ── Alert blocks ─────────────────────────────────────────────────────────────

class AlertItem(BaseModel):
    severity: str                   # "info" | "warning" | "critical"
    icon: str
    title: str
    action: str


# ── Confidence explanation ────────────────────────────────────────────────────

class ConfidenceFactor(BaseModel):
    factor: str
    status: str                     # "✔" | "~" | "✘"
    detail: str


class ConfidenceExplanation(BaseModel):
    score: int
    rating: str                     # "High Confidence" | "Moderate Confidence" | "Low Confidence"
    color: str                      # "green" | "yellow" | "red"
    factors: list[ConfidenceFactor]


# ── Smart Recommendation Response (full) ──────────────────────────────────────

class SmartRecommendResponse(BaseModel):
    """Complete response from POST /recommend.

    Structured for both frontend integration and farmer readability.
    Frontend consumers should use:
      - summary          → hero card
      - one_line_decision → banner / SMS / voice
      - recommendations  → detailed crop cards
      - alerts + risk_alerts → alert banners
      - confidence_explanation → trust indicator
    """
    status: str = "ok"

    # ── Location & context ─────────────────────────────────────────────────
    location: str | None = None
    district: str | None = None
    season: str | None = None
    land_area_hectares: float | None = None
    irrigated: bool | None = None
    mode: str | None = None         # "🛡 Safe Mode" | "💰 High Profit"
    input_coordinates: dict[str, float] | None = None
    location_warning: str | None = None

    # ── At-a-glance (frontend hero card) ─────────────────────────────────
    summary: RecommendSummary | None = None
    one_line_decision: str | None = None     # 🌱 Best crop: X — <farmer_tip>

    # ── Confidence (score + breakdown) ───────────────────────────────────
    confidence: int | None = None            # 0–100
    confidence_explanation: ConfidenceExplanation | None = None

    # ── Planning layer ─────────────────────────────────────────────────────
    insight: str | None = None               # district-level insight
    advice: str | None = None               # one-line farming advice
    comparison: dict[str, Any] | None = None  # safe vs profit crop comparison

    # ── Recommendations (rich per-crop data) ──────────────────────────────
    recommendations: list[RecommendationItem] = []
    top_recommended_crops: list[dict[str, Any]] = []  # backward-compat raw
    avoid_crops: list[dict[str, Any]] = []
    crops_evaluated: int = 0
    crops_filtered_out: int = 0

    # ── Alert layer ────────────────────────────────────────────────────────
    alerts: list[AlertItem] = []            # weather alerts
    risk_alerts: list[AlertItem] = []       # agronomic / soil / NDVI alerts

    # ── Weather ────────────────────────────────────────────────────────────
    weather_summary: dict[str, Any] | None = None
    weather_source: str | None = None
    live_conditions: str | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    code: str = "unknown_error"
    message: str


class ModelHealthResponse(BaseModel):
    loaded: bool = False
    ready: bool = False
    load_error: str | None = None
    models_dir: str | None = None
    features: list[str] = []
    defaults_count: int = 0
    encoder_classes: list[str] = []

