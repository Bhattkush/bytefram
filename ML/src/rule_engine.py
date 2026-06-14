"""
Rule Engine V3 — Agronomic Decision Layer
==========================================
Domain-knowledge layer that filters and scores crops using REAL farming
constraints. This is NOT a math layer — it encodes agricultural reality.

Pipeline:
  1. Pre-filter  → remove crops that CANNOT grow (hard constraints)
  2. ML predict  → yield prediction (handled by inference.py)
  3. Suitability → multi-factor agronomy score
  4. Reason      → human-readable explanation

Hard constraints (any one removes crop):
  - Season mismatch (unless Whole Year or off_season_irrigated)
  - Temperature outside survivable range
  - Insufficient water (even considering irrigation relaxation)
  - Sowing window missed

Soft penalties (reduce suitability score):
  - Off-season with irrigation (-20%)
  - Borderline temperature (-10-15%)
  - Soil mismatch (-5-15%)
  - Late sowing (-10%)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import MODELS_DIR

logger = logging.getLogger(__name__)

# ── Load crop requirements ────────────────────────────────────────────────────

_REQUIREMENTS_CACHE: dict[str, Any] | None = None


def _load_requirements() -> dict[str, Any]:
    global _REQUIREMENTS_CACHE
    if _REQUIREMENTS_CACHE is not None:
        return _REQUIREMENTS_CACHE

    path = MODELS_DIR / "crop_requirements.json"
    if path.exists():
        _REQUIREMENTS_CACHE = json.loads(path.read_text(encoding="utf-8"))
    else:
        _REQUIREMENTS_CACHE = {}
    return _REQUIREMENTS_CACHE


def _is_whole_year(req: dict[str, Any]) -> bool:
    """Check if crop is a whole-year crop (Banana, Sugarcane, etc.)."""
    return "Whole Year" in req.get("seasons", [])


# ── Pre-filter: remove impossible crops ───────────────────────────────────────

def pre_filter_crops(
    crops: list[str],
    weather: dict[str, Any],
    soil: dict[str, float] | None = None,
    irrigated: bool = False,
    season: str | None = None,
    region: str | None = None,
    relax: bool = False,
) -> tuple[list[str], dict[str, float]]:
    """Remove crops that are physically impossible given conditions.

    Returns:
      - filtered list of crop names that COULD potentially grow
      - dict of crop_name → penalty (0.0 = no penalty, 0.2 = 20% off-season penalty)

    Hard rules (crop removed entirely):
      1. Season mismatch AND not Whole Year AND (not irrigated or not off_season_irrigated)
      2. Temperature way outside range (>5°C buffer)
      3. Water-intensive crop with no water (rainfed + low rainfall)
      4. Sowing window completely missed (>2 months late)
    """
    requirements = _load_requirements()
    avg_temp = float(weather.get("Temperature_Avg", 25))
    max_temp = float(weather.get("Temperature_Max", 40))
    rainfall = float(weather.get("Rainfall", 500))
    current_month = datetime.now().month

    surviving: list[str] = []
    penalties: dict[str, float] = {}

    for crop in crops:
        req = requirements.get(crop)
        if req is None:
            # Unknown crop — give it a pass (let ML decide)
            surviving.append(crop)
            penalties[crop] = 0.0
            continue

        penalty = 0.0

        # ── 1. Season hard filter (HIGHEST PRIORITY) ──────────────────────
        if season:
            valid_seasons = req.get("seasons", [])
            is_whole_year = _is_whole_year(req)

            if is_whole_year:
                # Whole Year crops allowed in any season
                # BUT apply strict climate checks (don't blindly allow)
                if max_temp > 45:
                    # Extreme heat stress — even Banana/Sugarcane struggle
                    penalty += 0.15
                if not irrigated and rainfall < req.get("min_rainfall_mm", 0) * 0.3:
                    # Whole Year crops STILL need water — remove if rainfed + very dry
                    continue
            elif season not in valid_seasons:
                # Off-season crop — can we allow it with irrigation?
                allows_offseason = req.get("off_season_irrigated", False)
                if irrigated and allows_offseason:
                    # Allow but apply 20% penalty (off-season = higher risk)
                    penalty += 0.20
                elif relax:
                    # Soft penalty instead of removal for minimum crop guarantee
                    penalty += 0.40
                else:
                    # Hard remove — wrong season, no exception
                    continue

        min_t = req.get("min_temp", 0)
        max_t = req.get("max_temp", 50)
        buffer = 10 if relax else 5
        if avg_temp < min_t - buffer or avg_temp > max_t + buffer:
            # Way outside survivable range
            continue

        # Borderline temperature penalty (within buffer zone)
        opt_low, opt_high = req.get("optimal_temp", [20, 35])
        if avg_temp < min_t or avg_temp > max_t:
            penalty += 0.15  # Outside tolerance but within buffer
        elif avg_temp < opt_low - 3 or avg_temp > opt_high + 3:
            penalty += 0.10  # Far from optimal

        # ── 3. Water hard filter (Effective Water) ────────────────────────
        min_rain = req.get("min_rainfall_mm", 0)
        is_drought_ok = req.get("drought_tolerant", False)
        
        if irrigated:
            irrigation_support = min(500, min_rain * 0.8)
        else:
            # Rainfed relies on residual soil moisture
            moisture_factor = 0.4 if is_drought_ok else 0.2
            irrigation_support = min_rain * moisture_factor

        effective_water = rainfall + irrigation_support
        
        threshold = min_rain * (0.3 if is_drought_ok else 0.4)
        if relax:
            threshold = min_rain * 0.15  # Extreme relaxation
            if min_rain > 0 and effective_water < threshold:
                continue
            elif min_rain > 0 and effective_water < min_rain * 0.3:
                penalty += 0.30
        else:
            if min_rain > 0 and effective_water < threshold:
                continue  # Hard remove: too dry even with soil moisture

        # ── 4. Sowing window check ────────────────────────────────────────
        sowing_months = req.get("sowing_months", [])
        if sowing_months and not _is_whole_year(req):
            if current_month not in sowing_months:
                # Check if within ±1 month buffer (late sowing grace)
                buffered = set()
                for m in sowing_months:
                    buffered.add(m)
                    buffered.add((m % 12) + 1)        # next month
                    buffered.add(((m - 2) % 12) + 1)  # prev month

                if current_month in buffered:
                    penalty += 0.10  # Late/early sowing penalty
                elif relax:
                    penalty += 0.30  # Very late, but allowed due to relaxed constraints
                else:
                    # Completely missed sowing window
                    continue

        surviving.append(crop)
        penalties[crop] = round(penalty, 3)

    return surviving, penalties


# ── Suitability scoring (0.0 → 1.0) ──────────────────────────────────────────

def compute_suitability(
    crop: str,
    weather: dict[str, Any],
    soil: dict[str, float] | None = None,
    irrigated: bool = False,
    penalty: float = 0.0,
    region: str | None = None,
) -> float:
    """Compute a 0.0–1.0 suitability score for a crop given conditions.

    Multi-factor scoring (real agronomy weights):
      30% climate match (temperature fit)
      25% water match (rainfall + irrigation consideration)
      20% soil match (NPK + pH + organic carbon)
      15% calendar fit (sowing timing proximity)
      10% base adaptability

    Then subtract any penalties from pre-filter (off-season, borderline, etc.)
    """
    requirements = _load_requirements()
    req = requirements.get(crop)
    if req is None:
        return max(0.1, 0.7 - penalty)  # neutral default for unknown crops

    avg_temp = float(weather.get("Temperature_Avg", 25))
    rainfall = float(weather.get("Rainfall", 500))

    # ── Temperature score (30%) ─────────────────────────────────────────
    opt_low, opt_high = req.get("optimal_temp", [20, 35])
    min_t = req.get("min_temp", 10)
    max_t = req.get("max_temp", 45)

    if opt_low <= avg_temp <= opt_high:
        temp_score = 1.0
    elif min_t <= avg_temp <= max_t:
        if avg_temp < opt_low:
            temp_score = 0.5 + 0.5 * (avg_temp - min_t) / max(opt_low - min_t, 1)
        else:
            temp_score = 0.5 + 0.5 * (max_t - avg_temp) / max(max_t - opt_high, 1)
    else:
        # Outside survivable range but within buffer (pre-filter allowed it)
        temp_score = 0.15

    # ── Rainfall / Water score (25%) ────────────────────────────────────
    min_rain = req.get("min_rainfall_mm", 200)
    max_rain = req.get("max_rainfall_mm", 2000)
    is_drought_tolerant = req.get("drought_tolerant", False)
    
    if irrigated:
        irrigation_support = min(500, min_rain * 0.8)
    else:
        moisture_factor = 0.4 if is_drought_tolerant else 0.2
        irrigation_support = min_rain * moisture_factor

    effective_water = rainfall + irrigation_support

    if min_rain <= effective_water <= max_rain:
        rain_score = 1.0
    elif effective_water < min_rain:
        ratio = effective_water / max(min_rain, 1)
        rain_score = max(0.05, ratio)
        if is_drought_tolerant:
            rain_score = min(1.0, rain_score + 0.35)
    else:
        # Excess rainfall
        excess = effective_water / max(max_rain, 1)
        rain_score = max(0.25, 1.0 - (excess - 1.0) * 0.5)

    # ── Soil score (20%) — NPK + pH + Organic Carbon ───────────────────
    soil_score = 0.7  # default if no soil data
    if soil:
        sub_scores = []

        # pH check
        if "pH" in soil:
            ph = float(soil["pH"])
            min_ph = req.get("min_ph", 4.0)
            max_ph = req.get("max_ph", 9.0)
            if min_ph <= ph <= max_ph:
                sub_scores.append(1.0)
            else:
                deviation = min(abs(ph - min_ph), abs(ph - max_ph))
                sub_scores.append(max(0.2, 1.0 - deviation * 0.3))

        # NPK match against soil_preference
        soil_pref = req.get("soil_preference", {})
        for nutrient in ["N", "P", "K"]:
            if nutrient in soil and nutrient in soil_pref:
                val = float(soil[nutrient])
                ideal_range = soil_pref[nutrient]
                low, high = ideal_range[0], ideal_range[1]
                if low <= val <= high:
                    sub_scores.append(1.0)
                elif val < low:
                    sub_scores.append(max(0.3, val / max(low, 1)))
                else:
                    excess = val / max(high, 1)
                    sub_scores.append(max(0.4, 1.0 - (excess - 1.0) * 0.3))

        # Organic Carbon
        if "Organic_Carbon" in soil:
            oc = float(soil["Organic_Carbon"])
            if oc >= 0.5:
                sub_scores.append(min(1.0, 0.5 + oc))
            else:
                sub_scores.append(max(0.3, oc * 2))

        if sub_scores:
            soil_score = sum(sub_scores) / len(sub_scores)

    # ── Calendar fit score (15%) ────────────────────────────────────────
    sowing_months = req.get("sowing_months", [])
    current_month = datetime.now().month

    if not sowing_months or _is_whole_year(req):
        calendar_score = 0.8  # Whole year or no data
    elif current_month in sowing_months:
        calendar_score = 1.0  # Perfect timing
    else:
        buffered = set()
        for m in sowing_months:
            buffered.add((m % 12) + 1)
            buffered.add(((m - 2) % 12) + 1)
        
        if current_month in buffered:
            calendar_score = 0.7  # Nearby month
        else:
            calendar_score = 0.4  # Outside planting window entirely

    # ── Base adaptability (10%) ─────────────────────────────────────────
    base_score = 0.7
    if req.get("drought_tolerant", False):
        base_score += 0.1  # Drought tolerance = more adaptable
    if req.get("water_intensive", False) and not irrigated:
        base_score -= 0.2  # Water-intensive without irrigation = fragile

    # ── Region Feature Bias ───────────────────────────────────────────────
    if region == "coastal":
        rain_score = min(1.0, rain_score + 0.15)
        base_score = min(1.0, base_score + 0.10)
    elif region == "arid":
        if is_drought_tolerant:
            base_score = min(1.0, base_score + 0.15)

    base_score = max(0.1, min(1.0, base_score))

    # ── Weighted composite (Non-Linear Scaling) ───────────────────────────
    # Exponentiation increases sensitivity (good stays good, weak drops faster)
    temp_scaled = temp_score ** 1.8
    rain_scaled = rain_score ** 1.7
    soil_scaled = soil_score ** 1.3
    
    score = (
        temp_scaled * 0.30 +
        rain_scaled * 0.25 +
        soil_scaled * 0.20 +
        calendar_score * 0.15 +
        base_score * 0.10
    )

    # Apply penalties from pre-filter
    score = score * (1.0 - penalty)
    
    # Apply drought stress cap for arid conditions
    stress = effective_water / max(min_rain, 1)
    stress = min(stress, 1.0)
    score *= (0.5 + 0.5 * stress)
    
    # ── Explicit Meaningful Crop Diversity Mapping ───────────────────────
    if region == "coastal":
        if crop == "Rice": score += 0.15
        elif crop == "Sugarcane": score += 0.12
        elif crop == "Banana": score += 0.10
        elif crop == "Bajra": score -= 0.10
    elif region == "arid":
        if crop == "Bajra": score += 0.15
        elif crop == "Castor seed": score += 0.12

    # Clip safely between 0 and 1
    return round(max(0.0, min(1.0, score)), 3)


# ── Reason generator ─────────────────────────────────────────────────────────

def generate_reason(
    crop: str,
    weather: dict[str, Any],
    soil: dict[str, float] | None = None,
    suitability: float = 0.0,
    irrigated: bool = False,
    penalty: float = 0.0,
) -> str:
    """Generate a human-readable reason why this crop was recommended."""
    requirements = _load_requirements()
    req = requirements.get(crop)
    if req is None:
        return "Data-driven ML prediction based on historical yields."

    reasons: list[str] = []
    avg_temp = float(weather.get("Temperature_Avg", 25))
    rainfall = float(weather.get("Rainfall", 500))

    # Lead with the crop's unique description
    description = req.get("description", "")
    if description:
        reasons.append(description)

    # Temperature fit
    opt_low, opt_high = req.get("optimal_temp", [20, 35])
    if opt_low <= avg_temp <= opt_high:
        reasons.append(f"ideal temperature ({avg_temp:.0f}°C)")
    elif avg_temp < opt_low:
        reasons.append(f"slightly cool ({avg_temp:.0f}°C) but within tolerance")
    else:
        reasons.append(f"warm conditions ({avg_temp:.0f}°C) but tolerant")

    # Rainfall fit
    min_rain = req.get("min_rainfall_mm", 200)
    max_rain = req.get("max_rainfall_mm", 2000)

    if rainfall < 400:
        if req.get("drought_tolerant", False):
            reasons.append(f"handles low rainfall well ({rainfall:.0f}mm)")
        elif not irrigated:
            reasons.append(f"requires irrigation — only {rainfall:.0f}mm available vs {min_rain:.0f}mm needed")
        else:
            reasons.append(f"irrigation compensates low rainfall ({rainfall:.0f}mm)")
    elif min_rain <= rainfall <= max_rain:
        reasons.append(f"rainfall matches crop needs ({rainfall:.0f}mm)")
    elif rainfall > max_rain:
        reasons.append(f"high rainfall ({rainfall:.0f}mm) — ensure drainage")

    # Off-season warning
    if penalty >= 0.20:
        reasons.append("⚠ off-season crop — higher risk, needs careful management")
    elif penalty >= 0.10:
        reasons.append("slightly late sowing — monitor closely")

    # Irrigation
    if irrigated and req.get("water_intensive", False):
        reasons.append("irrigation essential for this crop's water needs")

    # Soil pH
    if soil and "pH" in soil:
        min_ph = req.get("min_ph", 4.0)
        max_ph = req.get("max_ph", 9.0)
        ph = float(soil["pH"])
        if min_ph <= ph <= max_ph:
            reasons.append(f"soil pH ({ph:.1f}) within range")
        else:
            reasons.append(f"soil pH ({ph:.1f}) slightly outside ideal ({min_ph}–{max_ph})")

    if not reasons:
        reasons.append("Suitable for current conditions")

    return ". ".join(r.capitalize() if i == 0 else r for i, r in enumerate(reasons))


# ── Risk assessment — structured dict output ────────────────────────────────

def calculate_risk(
    weather: dict[str, Any],
    crop: str | None = None,
    irrigated: bool = False,
    penalty: float = 0.0,
    soil: dict[str, float] | None = None,
    ndvi_value: float | None = None,
) -> dict[str, Any]:
    """Compute structured risk assessment for a crop given conditions.

    Returns a dict (not a plain string) so callers get granular breakdown.
    Backward-compatible: risk["overall"] is the old string label.

    Risk score formula (explicit + documented):
        risk_score = 0.35 × drought_risk
                   + 0.25 × heat_risk
                   + 0.20 × soil_risk
                   + 0.20 × ndvi_risk
                   + off_season adjustment
    """
    requirements = _load_requirements()
    max_t    = float(weather.get("Temperature_Max", 30))
    min_t    = float(weather.get("Temperature_Min", 15))
    rainfall = float(weather.get("Rainfall", 500))

    def _label(val: float) -> str:
        if val >= 0.55:  return "High"
        elif val >= 0.25: return "Medium"
        elif val > 0.05:  return "Low"
        return "None"

    # ── Drought risk (0.0 → 1.0) ──────────────────────────────────────────
    drought_risk_val = 0.0
    if rainfall < 100 and not irrigated:
        drought_risk_val = 0.85
    elif rainfall < 300 and not irrigated:
        drought_risk_val = 0.45
    elif rainfall < 500 and not irrigated:
        drought_risk_val = 0.15
    # Drought-tolerant crop reduces drought risk
    if crop:
        req = requirements.get(crop, {})
        if req.get("drought_tolerant", False) and rainfall < 300:
            drought_risk_val = max(0.0, drought_risk_val - 0.25)
        # Water-intensive crop without water → higher drought risk
        if req.get("water_intensive", False) and not irrigated:
            if rainfall < req.get("min_rainfall_mm", 0):
                drought_risk_val = min(1.0, drought_risk_val + 0.20)

    # ── Heat risk (0.0 → 1.0) ─────────────────────────────────────────────
    heat_risk_val = 0.0
    if max_t > 47:
        heat_risk_val = 0.90
    elif max_t > 44:
        heat_risk_val = 0.55
    elif max_t > 40:
        heat_risk_val = 0.25
    elif max_t > 38:
        heat_risk_val = 0.10

    # ── Frost risk (0.0 → 1.0) ────────────────────────────────────────────
    frost_risk_val = 0.0
    if min_t < 3:
        frost_risk_val = 0.70
    elif min_t < 8:
        frost_risk_val = 0.25

    # ── Flood risk (0.0 → 1.0) ────────────────────────────────────────────
    flood_risk_val = 0.0
    if rainfall > 2500:
        flood_risk_val = 0.60
    elif rainfall > 2000:
        flood_risk_val = 0.25

    # ── Soil risk — based on nutrient deficiencies ────────────────────────
    soil_risk_val = 0.0
    if soil:
        n_val  = float(soil.get("N",  65))
        p_val  = float(soil.get("P",  35))
        k_val  = float(soil.get("K",  40))
        oc_val = float(soil.get("Organic_Carbon", 0.70))
        # Count severe deficiencies (thresholds from ICAR guidelines)
        deficiencies = sum([
            n_val < 40,      # low available nitrogen
            p_val < 20,      # low phosphorus (most impactful per model: 42.7%)
            k_val < 25,      # low potassium
            oc_val < 0.40,   # very low organic carbon
        ])
        soil_risk_val = min(1.0, deficiencies * 0.20)

    # ── NDVI risk — land degradation signal (model rank #11, 1.46%) ───────
    ndvi_risk_val = 0.0
    if ndvi_value is not None:
        if ndvi_value < 0.25:
            ndvi_risk_val = 0.60   # bare/degraded land
        elif ndvi_value < 0.35:
            ndvi_risk_val = 0.35
        elif ndvi_value < 0.45:
            ndvi_risk_val = 0.15

    # ── Off-season risk (from penalty) ────────────────────────────────────
    offseason_risk_val = min(1.0, penalty)

    # ── Composite risk score (weighted formula) ────────────────────────────
    # Weights set to match agronomic importance + model signal strength
    risk_score = (
        0.35 * drought_risk_val +
        0.25 * heat_risk_val    +
        0.20 * soil_risk_val    +
        0.20 * ndvi_risk_val
    )
    # Off-season adds a flat penalty on top
    risk_score = min(1.0, risk_score + offseason_risk_val * 0.15)
    risk_score = round(risk_score, 3)

    # ── Yield confidence: inverse of composite risk + soil quality bonus ──
    base_conf = 1.0 - risk_score
    if soil:
        oc_val = float(soil.get("Organic_Carbon", 0.70))
        base_conf = min(1.0, base_conf + oc_val * 0.05)  # fertile soil boosts confidence
    yield_confidence = round(max(0.10, min(0.99, base_conf)), 2)
    confidence_level = (
        "High"   if yield_confidence >= 0.75 else
        "Medium" if yield_confidence >= 0.50 else
        "Low"
    )

    # ── Overall label (backward-compatible string) ─────────────────────────
    if risk_score >= 0.55:
        overall = "High Risk"
    elif risk_score >= 0.25:
        overall = "Medium Risk"
    else:
        overall = "Low Risk"

    return {
        "overall":          overall,           # backward-compat string label
        "drought_risk":     _label(drought_risk_val),
        "heat_risk":        _label(heat_risk_val),
        "frost_risk":       _label(frost_risk_val),
        "flood_risk":       _label(flood_risk_val),
        "off_season_risk":  _label(offseason_risk_val),
        "soil_risk":        _label(soil_risk_val),
        "ndvi_risk":        _label(ndvi_risk_val),
        "yield_confidence": yield_confidence,  # 0.0–1.0
        "confidence_level": confidence_level,  # "Low" / "Medium" / "High"
        "risk_score":       risk_score,         # 0.0–1.0 composite
    }


# ── Explanation layer — model-importance-aligned ─────────────────────────────

def generate_explanation(
    crop: str,
    weather: dict[str, Any],
    soil: dict[str, float] | None = None,
    suitability: float = 0.0,
    irrigated: bool = False,
    penalty: float = 0.0,
    ndvi_value: float | None = None,
    ndvi_label: str | None = None,
) -> dict[str, Any]:
    """Generate a structured, model-feature-importance-aligned explanation.

    Factor order mirrors XGBoost feature importances:
      1. Phosphorus (P)      42.7% — most impactful soil nutrient
      2. Heat_Stress_Days    11.2% — thermal stress signal
      3. Nitrogen (N)         5.9% — secondary nutrient
      4. Rainfall / water      —   — agronomic necessity
      5. NDVI_Peak            1.5% — mentioned accurately, not overemphasized

    Returns a dict so the frontend / API can render it richly.
    """
    requirements = _load_requirements()
    req         = requirements.get(crop, {})
    avg_temp    = float(weather.get("Temperature_Avg", 25))
    max_temp    = float(weather.get("Temperature_Max", 35))
    rainfall    = float(weather.get("Rainfall", 500))
    min_rain    = req.get("min_rainfall_mm", 300)

    factors: list[str] = []
    soil_score  = 50  # neutral default when no soil data
    p_val       = 35.0
    n_val       = 65.0

    # ── Factor 1: Soil nutrients (P=42.7%, N=5.9% of model) ──────────────
    if soil:
        n_val  = float(soil.get("N",  65))
        p_val  = float(soil.get("P",  35))
        k_val  = float(soil.get("K",  40))
        oc_val = float(soil.get("Organic_Carbon", 0.70))

        # Weighted soil score (0–100) — P weighted most (mirrors model)
        soil_score = int(
            min(100, n_val  / 80  * 100) * 0.30 +
            min(100, p_val  / 50  * 100) * 0.45 +   # P is dominant feature
            min(100, k_val  / 60  * 100) * 0.15 +
            min(100, oc_val / 1.0 * 100) * 0.10
        )

        if p_val < 20:
            factors.append(
                f"⚠️ Very low phosphorus (P: {p_val:.0f} kg/ha) — major yield limiter"
            )
        elif p_val >= 40:
            factors.append(
                f"✅ Good phosphorus (P: {p_val:.0f} kg/ha) — primary yield driver"
            )
        else:
            factors.append(
                f"🌱 Moderate phosphorus (P: {p_val:.0f} kg/ha)"
            )

        if n_val < 40:
            factors.append(
                f"⚠️ Low nitrogen (N: {n_val:.0f} kg/ha) — top-dress fertilizer advised"
            )
        elif n_val >= 60:
            factors.append(
                f"✅ Adequate nitrogen (N: {n_val:.0f} kg/ha)"
            )
    else:
        factors.append("🌱 Soil fertility — using district averages (provide soil data for precision)")

    # ── Factor 2: Heat stress (11.2% of model) ───────────────────────────
    if max_temp > 42:
        factors.append(
            f"🔥 High heat stress (Tmax {max_temp:.0f}°C) — choose heat-tolerant variety"
        )
    elif max_temp > 38:
        factors.append(
            f"🌡️ Moderate heat ({max_temp:.0f}°C) — monitor crop stress"
        )
    else:
        opt_low, opt_high = req.get("optimal_temp", [20, 35])
        if opt_low <= avg_temp <= opt_high:
            factors.append(f"✅ Ideal temperature ({avg_temp:.0f}°C) for {crop}")
        else:
            factors.append(
                f"🌡️ Temperature ({avg_temp:.0f}°C) within tolerance for {crop}"
            )

    # ── Factor 3: Water availability (agronomic necessity) ───────────────
    if rainfall < 200 and not irrigated:
        if req.get("drought_tolerant"):
            factors.append(
                f"💧 Very low rainfall ({rainfall:.0f}mm) — drought-resistant variety selected"
            )
        else:
            factors.append(
                f"⚠️ Very low rainfall ({rainfall:.0f}mm) vs {min_rain:.0f}mm needed"
            )
    elif rainfall < 400 and not irrigated:
        if req.get("drought_tolerant"):
            factors.append(
                f"💧 Low rainfall ({rainfall:.0f}mm) handled by drought tolerance"
            )
        else:
            factors.append(
                f"💧 Low rainfall ({rainfall:.0f}mm) — supplemental irrigation recommended"
            )
    elif irrigated:
        factors.append("💦 Irrigation available — water needs met")
    else:
        factors.append(f"🌧️ Adequate rainfall ({rainfall:.0f}mm)")

    # ── Factor 4: NDVI — vegetation health (rank #11, 1.46%) ────────────
    # Mentioned only when clearly impactful to avoid overstatement
    ndvi_impact = "neutral"
    if ndvi_value is not None:
        if ndvi_value >= 0.55:
            ndvi_impact = "positive"
            factors.append(
                f"🌿 Healthy vegetation (NDVI {ndvi_value:.2f}) — good land condition"
            )
        elif ndvi_value < 0.30:
            ndvi_impact = "negative"
            factors.append(
                f"🏜️ Low vegetation index (NDVI {ndvi_value:.2f}) — degraded land conditions"
            )
        # In the 0.30–0.55 range: don't mention — impact is minor at this level

    # ── Factor 5: Sowing calendar ─────────────────────────────────────────
    current_month = datetime.now().month
    sowing_months = req.get("sowing_months", [])
    if sowing_months and not _is_whole_year(req):
        if current_month in sowing_months:
            factors.append("📅 Perfect sowing window")
        elif penalty >= 0.10:
            factors.append("📅 Slightly outside sowing window — monitor closely")

    if penalty >= 0.20:
        factors.append("⚠️ Off-season crop — higher management attention required")

    # ── Key limiting factor (model-importance-aligned) ────────────────────
    # P is the dominant model feature → check soil first
    if soil and p_val < 20:
        key_limiting = "soil_phosphorus"
    elif max_temp > 42:
        key_limiting = "heat_stress"
    elif rainfall < 200 and not irrigated and not req.get("drought_tolerant"):
        key_limiting = "water"
    elif soil and n_val < 40:
        key_limiting = "soil_nitrogen"
    elif ndvi_value is not None and ndvi_value < 0.25:
        key_limiting = "land_degradation"
    elif penalty >= 0.20:
        key_limiting = "off_season"
    else:
        key_limiting = "none"

    # ── Headline (human-readable, context-driven) ─────────────────────────
    if key_limiting == "water" and req.get("drought_tolerant"):
        headline = (
            f"Recommended {crop} — drought-resistant variety suits "
            f"low-rainfall conditions ({rainfall:.0f}mm)"
        )
    elif key_limiting == "water":
        headline = (
            f"Recommended {crop} — note water deficit "
            f"({rainfall:.0f}mm available vs {min_rain:.0f}mm needed)"
        )
    elif key_limiting == "heat_stress":
        headline = (
            f"Recommended {crop} — heat management required "
            f"({max_temp:.0f}°C peak)"
        )
    elif key_limiting == "soil_phosphorus":
        headline = (
            f"Recommended {crop} — apply phosphorus fertilizer "
            f"(P: {p_val:.0f} kg/ha is below optimum)"
        )
    elif key_limiting == "soil_nitrogen":
        headline = (
            f"Recommended {crop} — nitrogen top-dressing advised "
            f"(N: {n_val:.0f} kg/ha)"
        )
    elif suitability >= 0.75:
        headline = (
            f"Recommended {crop} — strong match across soil, climate, and season"
        )
    elif suitability >= 0.50:
        headline = f"Recommended {crop} — good overall suitability for current conditions"
    else:
        headline = f"Recommended {crop} — viable option given current constraints"

    confidence_level = (
        "High"   if suitability >= 0.75 else
        "Medium" if suitability >= 0.50 else
        "Low"
    )

    # ── Farmer tip: plain-English one-liner for real users ─────────────────────
    # Converts technical risk language into what a farmer actually understands.
    # No jargon, no indices, no feature names.
    if key_limiting == "water" and req.get("drought_tolerant"):
        farmer_tip = (
            f"Water will be scarce this season — {crop} handles dry spells well. "
            f"Still, sow early and mulch the soil."
        )
    elif key_limiting == "water":
        farmer_tip = (
            f"Water shortage risk — {crop} needs irrigation or rain. "
            f"Without it, expect lower yields."
        )
    elif key_limiting == "heat_stress":
        farmer_tip = (
            f"Temperatures will be high — sow {crop} in the cooler part of the season "
            f"and irrigate during peak afternoon heat."
        )
    elif key_limiting == "soil_phosphorus":
        farmer_tip = (
            f"Your soil is low on phosphorus — apply DAP fertilizer before sowing {crop} "
            f"to get the best yield."
        )
    elif key_limiting == "soil_nitrogen":
        farmer_tip = (
            f"Your soil needs more nitrogen — apply urea or compost before sowing {crop}."
        )
    elif key_limiting == "land_degradation":
        farmer_tip = (
            f"Land condition is weak — add organic matter (compost/FYM) before sowing. "
            f"{crop} is a good choice to start soil recovery."
        )
    elif suitability >= 0.75:
        farmer_tip = f"Good news — your land and weather are well-suited for {crop} this season."
    elif suitability >= 0.50:
        farmer_tip = f"{crop} should grow reasonably well. Follow standard practices and monitor weekly."
    else:
        farmer_tip = f"{crop} is possible but conditions are not ideal. Use it as a backup option."

    return {
        "headline":            headline,
        "farmer_tip":          farmer_tip,          # plain English for real users
        "factors":             factors,
        "soil_score":          soil_score,          # 0–100 weighted nutrient score
        "ndvi_impact":         ndvi_impact,          # "positive" / "neutral" / "negative"
        "key_limiting_factor": key_limiting,         # dominant constraint
        "confidence_level":    confidence_level,     # "High" / "Medium" / "Low"
    }
