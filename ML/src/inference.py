from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .constants import MODELS_DIR

logger = logging.getLogger(__name__)


# ── Structured response helpers ──────────────────────────────────────────────

def _error_response(message: str, code: str = "prediction_error") -> dict[str, Any]:
    """Return a standardised error dict — callers should never see a raw exception."""
    return {"status": "error", "code": code, "message": message}


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    """Wrap any successful result so the caller always gets a status field."""
    return {"status": "ok", **data}


# ── Input validation ─────────────────────────────────────────────────────────

REQUIRED_WEATHER_FIELDS = {
    "Temperature_Avg", "Temperature_Min", "Temperature_Max",
    "Rainfall", "Humidity",
}

# Any feature the model expects — used for soft validation / warnings
ALL_MODEL_FEATURES = {
    "Temperature_Avg", "Temperature_Min", "Temperature_Max",
    "Rainfall", "Humidity",
    "N", "P", "K", "pH", "Organic_Carbon",
    "NDVI_Peak", "Temp_Range", "GDD",
    "Humidity_Rain_Interaction", "Crop",
}


def validate_payload(payload: dict[str, Any]) -> list[str]:
    """Validate an inference payload. Returns a list of warning strings.

    Does NOT raise — missing fields will be filled from defaults during
    feature-frame construction. Warnings are informational only.
    """
    warnings: list[str] = []

    if not isinstance(payload, dict):
        warnings.append("Payload is not a dictionary.")
        return warnings

    # Check for crop (required for yield prediction)
    if "crop" not in payload and "Crop" not in payload:
        warnings.append("No 'crop' specified — will use default crop for prediction.")

    # Check for at least some weather fields
    normalised_keys = {k.lower().replace(" ", "_") for k in payload}
    weather_present = sum(
        1 for f in REQUIRED_WEATHER_FIELDS
        if f.lower().replace(" ", "_") in normalised_keys or f in payload
    )
    if weather_present == 0:
        warnings.append("No weather data provided — prediction will use defaults (low accuracy).")
    elif weather_present < len(REQUIRED_WEATHER_FIELDS):
        warnings.append(f"Only {weather_present}/{len(REQUIRED_WEATHER_FIELDS)} weather fields provided.")

    # Check for obviously wrong values
    for field, lo, hi in [
        ("Temperature_Avg", -20, 60),
        ("Humidity", 0, 100),
        ("Rainfall", 0, 10000),
        ("pH", 0, 14),
    ]:
        val = payload.get(field) or payload.get(field.lower())
        if val is not None:
            try:
                val = float(val)
                if val < lo or val > hi:
                    warnings.append(f"'{field}' value {val} is outside expected range [{lo}, {hi}].")
            except (TypeError, ValueError):
                warnings.append(f"'{field}' value '{val}' is not a valid number.")

    return warnings


# ── Model Hub ────────────────────────────────────────────────────────────────

class SmartFarmingModelHub:
    """Central access point for all trained ML models.

    Design contract:
      - `.load()` is idempotent and safe to call multiple times
      - `.predict_yield()` may raise on truly broken input
      - `.predict_yield_safe()` NEVER raises — always returns a dict with status
    """

    def __init__(self, models_dir: Path | str | None = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else MODELS_DIR
        self._yield_model = None
        self._crop_encoder = None
        self._defaults: dict[str, Any] = {}
        self._feature_sets: dict[str, list[str]] = {}
        self._model_version: str | None = None
        self._trained_at: str | None = None
        self._loaded = False
        self._load_error: str | None = None

    # ── Loading ───────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load all model artifacts. Idempotent — safe to call repeatedly."""
        if self._loaded:
            return

        try:
            model_path = self.models_dir / "yield_model.pkl"
            if not model_path.exists():
                self._load_error = f"Model file not found: {model_path}"
                logger.error(self._load_error)
                return

            self._yield_model = joblib.load(model_path)

            encoder_path = self.models_dir / "crop_encoder.pkl"
            if encoder_path.exists():
                self._crop_encoder = joblib.load(encoder_path)

            metadata_path = self.models_dir / "model_metadata.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self._defaults = metadata.get("defaults", {})
                self._feature_sets = metadata.get("feature_sets", {})
                self._model_version = metadata.get("version", "1.0.0")
                self._trained_at = metadata.get("trained_at")

            # Ground truth: always read feature order directly from the trained model.
            if hasattr(self._yield_model, "feature_names_in_"):
                self._feature_sets["yield_model"] = list(self._yield_model.feature_names_in_)

            self._loaded = True
            self._load_error = None
            logger.info("SmartFarmingModelHub loaded successfully from %s", self.models_dir)

        except Exception as exc:
            self._load_error = f"Failed to load models: {exc}"
            logger.exception(self._load_error)

    @property
    def is_ready(self) -> bool:
        """True when the model is loaded and ready for predictions."""
        return self._loaded and self._yield_model is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def get_model_info(self) -> dict[str, Any]:
        """Return model health / metadata for monitoring endpoints."""
        return {
            "loaded": self._loaded,
            "ready": self.is_ready,
            "load_error": self._load_error,
            "models_dir": str(self.models_dir),
            "version": self._model_version,
            "trained_at": self._trained_at,
            "features": self._feature_sets.get("yield_model", []),
            "defaults_count": len(self._defaults),
            "encoder_classes": (
                list(self._crop_encoder.classes_) if self._crop_encoder else []
            ),
        }

    # ── Payload normalisation ─────────────────────────────────────────────

    def _coerce_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        aliases = {
            "district": "District",
            "season": "Season",
            "year": "Year",
            "crop": "Crop",
            "temperature_avg": "Temperature_Avg",
            "temperature_min": "Temperature_Min",
            "temperature_max": "Temperature_Max",
            "rainfall": "Rainfall",
            "humidity": "Humidity",
            "n": "N",
            "p": "P",
            "k": "K",
            "ph": "pH",
            "organic_carbon": "Organic_Carbon",
            "gdd": "GDD",
            "seasonal_rainfall": "Seasonal_Rainfall",
            "temp_range": "Temp_Range",
            "humidity_rain_interaction": "Humidity_Rain_Interaction",
            "ndvi_peak": "NDVI_Peak",
        }
        canonical = {}
        for key, value in payload.items():
            mapped = aliases.get(key, key)
            canonical[mapped] = value
        return canonical

    # ── Feature frame construction ────────────────────────────────────────

    def _build_feature_frame(self, payload: dict[str, Any], model_key: str) -> pd.DataFrame:
        self.load()
        normalized = self._coerce_payload(payload)
        # Keep as ordered list — XGBoost requires columns in exact training order
        expected: list[str] = [str(f) for f in self._feature_sets.get(model_key, [])]

        # Pre-compute all possible derived features from raw inputs
        def _safe_float(val: Any) -> float:
            """Coerce to float, returning 0.0 for non-scalar types (list, dict, etc.)."""
            if val is None:
                return 0.0
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0

        temp_max = _safe_float(normalized.get("Temperature_Max"))
        temp_min = _safe_float(normalized.get("Temperature_Min"))
        temp_avg = _safe_float(normalized.get("Temperature_Avg"))
        humidity  = _safe_float(normalized.get("Humidity"))
        rainfall  = _safe_float(normalized.get("Rainfall"))

        # Season days default (Summer=100, Kharif=120, Rabi=130)
        season_days = 110.0

        # Heat_Stress_Days: fraction of days where Tmax exceeds 35°C × season days
        heat_fraction = max(0.0, min(1.0, (temp_max - 35.0) / 10.0))
        heat_stress_days = round(heat_fraction * season_days, 1)

        # Dry_Days: season days minus estimated rainy days (rainfall / 5mm per rainy day)
        rainy_days = min(rainfall / 5.0, season_days)
        dry_days = round(max(0.0, season_days - rainy_days), 1)

        derived = {
            "Temp_Range":                 temp_max - temp_min,
            "Seasonal_Rainfall":          normalized.get("Seasonal_Rainfall", rainfall),
            "Humidity_Rain_Interaction":   humidity * rainfall / 100.0,
            "GDD":                         max(temp_avg - 10.0, 0.0) * 120,
            "NDVI_Peak":                   normalized.get("NDVI_Peak", 0.5),
            "Heat_Stress_Days":            heat_stress_days,
            "Dry_Days":                    dry_days,
        }

        # Build row with ONLY features the model was trained on
        row: dict[str, Any] = {}
        for feature in expected:
            if feature in normalized:
                row[feature] = normalized[feature]
            elif feature in derived:
                row[feature] = derived[feature]
            else:
                row[feature] = self._defaults.get(feature)

        # Cast numeric features to float
        numeric_candidates = {
            "Year", "Temperature_Avg", "Temperature_Min", "Temperature_Max",
            "Rainfall", "Humidity", "N", "P", "K", "pH", "Organic_Carbon",
            "GDD", "Seasonal_Rainfall", "Temp_Range", "Humidity_Rain_Interaction",
            "NDVI_Peak",
        }
        for feature in numeric_candidates:
            if feature in row and row[feature] is not None:
                try:
                    row[feature] = float(row[feature])
                except (TypeError, ValueError):
                    row[feature] = self._defaults.get(feature, 0.0)

        # Encode Crop string -> int via saved LabelEncoder
        if "Crop" in row and isinstance(row["Crop"], str):
            if self._crop_encoder is not None:
                try:
                    row["Crop"] = int(self._crop_encoder.transform([row["Crop"]])[0])
                except ValueError:
                    row["Crop"] = 0
            else:
                row["Crop"] = 0

        # ── Safety pass: replace any remaining None/NaN with 0.0 ──────────
        for feature in expected:
            val = row.get(feature)
            if val is None:
                logger.warning("Feature '%s' is None after all fallbacks — using 0.0", feature)
                row[feature] = 0.0

        frame = pd.DataFrame([row], columns=expected)

        # Catch any NaN that slipped through (e.g. float('nan') from bad data)
        if frame.isna().any().any():
            nan_cols = frame.columns[frame.isna().any()].tolist()
            logger.warning("NaN detected in features %s — filling with 0.0", nan_cols)
            frame = frame.fillna(0.0)

        return frame

    # ── Prediction methods ────────────────────────────────────────────────

    def predict_yield(self, payload: dict[str, Any]) -> float:
        """Predict yield — may raise on invalid input.

        Use `predict_yield_safe()` for a guaranteed-no-crash version.
        """
        frame = self._build_feature_frame(payload, model_key="yield_model")
        pred = float(self._yield_model.predict(frame)[0])
        return max(pred, 0.0)

    def predict_yield_safe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Predict yield — NEVER raises. Always returns a dict with 'status'.

        Success: {"status": "ok", "yield": 2.34, "warnings": [...]}
        Error:   {"status": "error", "code": "...", "message": "..."}
        """
        # 1. Check model readiness
        if not self.is_ready:
            self.load()  # Try once more
            if not self.is_ready:
                return _error_response(
                    message=self._load_error or "Model is not loaded. Please try again later.",
                    code="model_not_ready",
                )

        # 2. Validate input
        if not isinstance(payload, dict):
            return _error_response(
                message="Invalid input: expected a dictionary of features.",
                code="invalid_input",
            )

        if not payload:
            return _error_response(
                message="Empty input: please provide at least crop name and weather data.",
                code="empty_input",
            )

        warnings = validate_payload(payload)

        # 3. Predict
        try:
            predicted_yield = self.predict_yield(payload)
            return _success_response({
                "yield": round(predicted_yield, 4),
                "warnings": warnings,
                "model_version": self._model_version,
            })
        except Exception as exc:
            logger.exception("Prediction failed for payload: %s", payload)
            return _error_response(
                message=f"Unable to predict. Please try again. ({type(exc).__name__})",
                code="prediction_error",
            )
