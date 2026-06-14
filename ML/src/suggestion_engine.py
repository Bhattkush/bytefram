"""
Farmer Decision System — Suggestion Engine V3
==============================================
Production-grade agricultural decision pipeline.

Architecture:
  weather + soil + season + irrigation
          ↓
    rule-based filtering (STRICT)
          ↓
    ML yield prediction
          ↓
    multi-factor suitability scoring
          ↓
    risk-adjusted profit calculation
          ↓
    final ranking (composite score)

Key V3 changes:
  - Season-crop map auto-derived from crop_requirements.json (single source of truth)
  - Penalty system (off-season, borderline temp, late sowing)
  - Irrigation relaxes rules instead of adding fake rainfall
  - Profit adjusted for price volatility + storage loss
  - Whole Year crops allowed with strict climate checks
  - Off-season irrigated exceptions (Rice/Maize in summer)
"""
from __future__ import annotations

import logging
import json
import joblib
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import Any

from .constants import MODELS_DIR
from .inference import SmartFarmingModelHub
from .climate_client import fetch_seasonal_climate, ClimateClientError
from .weather_client import blend_with_historical, WeatherClientError as LiveWeatherError
from .soil_loader import SoilDataLoader
from .ndvi_loader import get_ndvi, get_ndvi_label
from .rule_engine import (
    _load_requirements,
    pre_filter_crops,
    compute_suitability,
    generate_reason,
    generate_explanation,
    calculate_risk,
)
from .utils import (
    get_season_from_date,
    get_valid_crops_for_location,
    classify_production_level,
)
from .alerts import generate_live_alerts, build_confidence_explanation, generate_risk_alerts


# ── Auto-derive season→crop mapping from crop_requirements.json ──────────────

def _build_season_crop_map() -> dict[str, set[str]]:
    """Build season→crop mapping from crop_requirements.json (single source of truth).

    Whole Year crops are included in ALL seasons.
    This replaces the old hardcoded SEASON_CROP_MAP.
    """
    requirements = _load_requirements()
    season_map: dict[str, set[str]] = {
        "Kharif": set(),
        "Rabi": set(),
        "Summer": set(),
    }

    for crop, req in requirements.items():
        seasons = req.get("seasons", [])
        for s in seasons:
            if s == "Whole Year":
                # Whole Year crops go into ALL seasons
                for key in season_map:
                    season_map[key].add(crop)
            elif s in season_map:
                season_map[s].add(crop)

    return season_map


# Crop category labels for display and diversity logic
CROP_CATEGORY: dict[str, str] = {
    "Bajra": "Cereal", "Jowar": "Cereal", "Maize": "Cereal",
    "Rice": "Cereal", "Wheat": "Cereal", "Ragi": "Cereal",
    "Small millets": "Cereal", "Other Cereals": "Cereal",
    "Gram": "Pulse", "Arhar/Tur": "Pulse", "Urad": "Pulse",
    "Moong(Green Gram)": "Pulse", "Moth": "Pulse",
    "Other Kharif pulses": "Pulse", "Other  Rabi pulses": "Pulse",
    "Groundnut": "Oilseed", "Castor seed": "Oilseed",
    "Sesamum": "Oilseed", "Soyabean": "Oilseed",
    "Rapeseed &Mustard": "Oilseed", "other oilseeds": "Oilseed",
    "Guar seed": "Oilseed",
    "Cotton(lint)": "Cash Crop", "Sugarcane": "Cash Crop", "Tobacco": "Cash Crop",
    "Banana": "Fruit", "Onion": "Vegetable", "Potato": "Vegetable",
    "Garlic": "Vegetable", "Dry chillies": "Spice",
}

REGION_TYPES: dict[str, str] = {
    "kutch": "arid",
    "banaskantha": "arid",
    "ahmedabad": "semi_arid",
    "rajkot": "semi_arid",
    "surendranagar": "semi_arid",
    "surat": "coastal",
    "navsari": "coastal",
    "valsad": "coastal",
    "bharuch": "coastal",
    "porbandar": "coastal",
    "jamnagar": "coastal"
}


class FarmerDecisionSystem:
    def __init__(self) -> None:
        self._hub = SmartFarmingModelHub()
        self._crop_encoder = None
        self._district_bias: dict[str, dict[str, float]] = {}
        self._district_soil: dict[str, dict[str, float]] = {}  # kept for fallback
        self._market_prices: dict[str, dict] = {}
        # SoilDataLoader reads the real 33-district soil CSV at startup
        self._soil_loader = SoilDataLoader()

    def _load(self) -> None:
        try:
            self._hub.load()
        except Exception as exc:
            logger.exception("Failed to load ML model hub")
            raise RuntimeError(f"ML model failed to load: {exc}") from exc

        try:
            encoder_path = MODELS_DIR / "crop_encoder.pkl"
            if encoder_path.exists():
                self._crop_encoder = joblib.load(encoder_path)

            # Load district × crop yield bias (built from training data)
            bias_path = MODELS_DIR / "district_crop_bias.json"
            if bias_path.exists() and not self._district_bias:
                self._district_bias = json.loads(bias_path.read_text(encoding="utf-8"))

            # Load district-level soil defaults
            soil_path = MODELS_DIR / "district_soil_defaults.json"
            if soil_path.exists() and not self._district_soil:
                self._district_soil = json.loads(soil_path.read_text(encoding="utf-8"))

            # Load market prices
            prices_path = MODELS_DIR / "crop_market_prices.json"
            if prices_path.exists() and not self._market_prices:
                self._market_prices = json.loads(prices_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Non-critical load error (continuing): %s", exc)

    def _get_district_bias(self, district: str, crop: str) -> float:
        """Get yield bias multiplier for district × crop. 1.0 = state average.
        Clamped to 0.8–1.2 to prevent overfitting to historical outliers.
        """
        raw = self._district_bias.get(district, {}).get(crop, 1.0)
        return max(0.8, min(1.2, raw))

    def _get_district_soil(self, district: str) -> dict[str, float]:
        """
        Returns soil values for a district.

        Priority:
          1. SoilDataLoader (real CSV — 33 Gujarat districts)
          2. district_soil_defaults.json (limited fallback JSON)
          3. Empty dict (model uses its trained defaults)
        """
        # Try the real CSV loader first (covers all 33 districts)
        soil = self._soil_loader.get_soil(district)
        if soil:
            return soil
        # Fall back to the JSON file if the loader has no data
        return self._district_soil.get(district, {})

    def _all_known_crops(self) -> list[str]:
        if self._crop_encoder is None:
            return []
        return list(self._crop_encoder.classes_)

    def _filter_crops(self, season: str, district: str | None) -> list[str]:
        """Filter crops by season (from requirements) + district history."""
        all_crops = self._all_known_crops()
        season_map = _build_season_crop_map()
        season_valid = season_map.get(season, set())

        # Also include crops that allow off-season irrigated growing
        # (they'll be penalized later in pre_filter_crops)
        requirements = _load_requirements()
        offseason_crops = set()
        for crop_name, req in requirements.items():
            if req.get("off_season_irrigated", False):
                offseason_crops.add(crop_name)

        # Combine: season-valid + off-season-irrigated candidates
        candidate_set = season_valid | offseason_crops

        if district:
            location_valid = set(get_valid_crops_for_location(district))
            if location_valid:
                valid = [c for c in all_crops if c in candidate_set and c in location_valid]
                if valid:
                    return valid

        # Fall back to season + offseason filter
        return [c for c in all_crops if c in candidate_set]

    def recommend(
        self,
        city: str,
        district: str | None = None,
        soil: dict[str, float] | None = None,
        top_n: int = 3,
        land_area_hectares: float = 1.0,
        irrigated: bool = False,
        profit_mode: bool = False,
    ) -> dict[str, Any]:
        self._load()

        # ── Step 1: Detect season ─────────────────────────────────────────
        season = get_season_from_date()

        # ── Step 2: Fetch seasonal climate normals ────────────────────────
        try:
            climate = fetch_seasonal_climate(
                city=city, season=season, district=district
            )
        except ClimateClientError as exc:
            return {"error": str(exc)}

        resolved_district = climate.pop("_district", district or "Not specified")
        climate_source = climate.pop("_source", "api")
        is_fallback = climate.pop("_fallback", False)

        # ── Step 2b: Blend with Live OpenWeather data ─────────────────────
        # Fetches today's actual conditions and blends 30% live + 70% historical.
        # Temperature + humidity are blended; seasonal rainfall is kept historical
        # because a single day's rain cannot represent a 90–180 day season.
        live_blended = False
        live_weather_desc = ""
        try:
            climate = blend_with_historical(climate, city=city, blend_weight=0.30)
            live_blended = climate.get("_live_blended", False)
            live_weather_desc = climate.get("_live_description", "")
            # Strip internal metadata keys so they don't confuse the ML model
            for _k in ("_live_blended", "_live_weight", "_live_description",
                       "_live_wind_speed", "_live_city", "_live_current",
                       "_live_error"):
                climate.pop(_k, None)
        except Exception as _exc:
            logger.warning("Live weather blend failed (%s) — using historical only", _exc)

        # Warn if location could not be resolved
        location_warning = None
        if is_fallback:
            location_warning = (
                f"'{city}' not found in Gujarat district database. "
                f"Using Ahmedabad as fallback. Use --district to specify."
            )

        region_type = REGION_TYPES.get(resolved_district.lower())

        # ── Step 3: Filter crops by season + district ─────────────────────
        season_crops = self._filter_crops(season, resolved_district)

        # ── Step 4: Rule Engine pre-filter (STRICT — remove impossible) ───
        feasible_crops, penalties = pre_filter_crops(
            crops=season_crops,
            weather=climate,
            soil=soil,
            irrigated=irrigated,
            season=season,
            region=region_type,
        )

        # ── Minimum Crop Guarantee ─────────────────────────────────────────
        if len(feasible_crops) < 3:
            # Relax constraints for borderline crops (converts hard removing to heavy penalty)
            feasible_crops, penalties = pre_filter_crops(
                crops=season_crops,
                weather=climate,
                soil=soil,
                irrigated=irrigated,
                season=season,
                region=region_type,
                relax=True,
            )

        crops_removed = len(season_crops) - len(feasible_crops)

        # ── Step 5: Build base payload for ML model ───────────────────────
        # Soil: auto-filled from district training averages; user values override
        effective_soil = self._get_district_soil(resolved_district)
        # Remove non-numeric keys that would confuse the model
        effective_soil = {k: v for k, v in effective_soil.items()
                          if k not in ("Soil_Score", "Soil_Variability")}
        if soil:
            effective_soil.update(soil)  # User overrides take priority

        # NDVI: look up by district + current season
        # The model was trained with real varying NDVI values (range 0.40–0.91)
        # so providing the correct district+season value improves yield predictions
        ndvi_value = get_ndvi(resolved_district, season)
        ndvi_label  = get_ndvi_label(ndvi_value)

        base_payload: dict[str, Any] = {**climate}
        base_payload["NDVI_Peak"] = ndvi_value
        base_payload.update(effective_soil)

        # ── Step 6: Predict yield + compute suitability for each crop ─────
        results: list[dict[str, Any]] = []
        for crop in feasible_crops:
            payload = {**base_payload, "crop": crop}
            try:
                yield_per_hectare = self._hub.predict_yield(payload)
            except Exception:
                continue

            # Get penalty for this crop (off-season, borderline, etc.)
            crop_penalty = penalties.get(crop, 0.0)

            # District bias — used in SCORING only, yield stays pure from ML
            district_bias = self._get_district_bias(resolved_district, crop)

            # Suitability score from rule engine (V3: multi-factor + penalty)
            suitability = compute_suitability(
                crop=crop,
                weather=climate,
                soil=effective_soil or None,
                irrigated=irrigated,
                penalty=crop_penalty,
                region=region_type,
            )

            # Scale yield to farmer's actual land area
            total_yield_tonnes = yield_per_hectare * land_area_hectares
            total_yield_kg = total_yield_tonnes * 1000

            # Pick the friendliest unit
            if total_yield_tonnes >= 1.0:
                display_yield = f"{total_yield_tonnes:.2f} tonnes"
            else:
                display_yield = f"{total_yield_kg:.1f} kg"

            production = classify_production_level(crop, yield_per_hectare)

            # Risk per crop — now returns structured dict (backward-compatible)
            risk = calculate_risk(
                weather=climate,
                crop=crop,
                irrigated=irrigated,
                penalty=crop_penalty,
                soil=effective_soil or None,
                ndvi_value=ndvi_value,
            )
            risk_label = risk["overall"]  # backward-compat string

            # Human-readable reason + district context
            reason = generate_reason(
                crop=crop,
                weather=climate,
                soil=soil,
                suitability=suitability,
                irrigated=irrigated,
                penalty=crop_penalty,
            )
            # Append district history context if bias is notable
            bias_pct = round((district_bias - 1.0) * 100)
            if bias_pct >= 6:
                reason += f". historically {bias_pct}% higher yield in {resolved_district.title()}"
            elif bias_pct <= -10:
                reason += f". historically {abs(bias_pct)}% lower yield in {resolved_district.title()}"

            # Structured explanation aligned with model feature importances
            explanation = generate_explanation(
                crop=crop,
                weather=climate,
                soil=effective_soil or None,
                suitability=suitability,
                irrigated=irrigated,
                penalty=crop_penalty,
                ndvi_value=ndvi_value,
                ndvi_label=ndvi_label,
            )

            results.append({
                "crop_name":         crop,
                "category":          CROP_CATEGORY.get(crop, "Other"),
                "yield_per_hectare": round(yield_per_hectare, 4),
                "total_yield_tonnes": round(total_yield_tonnes, 4),
                "total_yield_kg":    round(total_yield_kg, 2),
                "display_yield":     display_yield,
                "production_level":  production,
                "suitability_score": suitability,
                "risk_confidence":   risk_label,   # backward-compat string
                "risk_detail":       risk,          # full structured risk dict
                "penalty":           crop_penalty,
                "reason":            reason,
                "explanation":       explanation,  # model-aligned structured explanation
            })

        # ── Step 7: Compute profit & composite score ──────────────────────
        for r in results:
            price_data = self._market_prices.get(r["crop_name"], {})
            price_per_tonne = price_data.get("price_per_tonne", 0)
            volatility = price_data.get("price_volatility", 0.10)
            storage_loss = price_data.get("storage_loss_pct", 5) / 100

            volatility_penalty = 1.0 - volatility
            storage_penalty = 1.0 - storage_loss

            # Risk-adjusted profit
            effective_price = price_per_tonne * volatility_penalty * storage_penalty
            profit = r["total_yield_tonnes"] * effective_price

            r["market_price_per_tonne"] = price_per_tonne
            r["effective_price_per_tonne"] = round(effective_price, 0)
            r["estimated_profit_inr"] = round(profit, 0)
            r["price_volatility"] = volatility

            # Profit confidence — derived from market price volatility
            # Low volatility = predictable returns = High confidence
            if volatility < 0.15:
                r["profit_confidence"] = "High"
            elif volatility < 0.30:
                r["profit_confidence"] = "Medium"
            else:
                r["profit_confidence"] = "Low"

            # Friendly display
            if profit >= 10000:
                r["display_profit"] = f"₹{profit/100000:.2f} L"
            else:
                r["display_profit"] = f"₹{profit:,.0f}"

        if results:
            max_yield = max(r["yield_per_hectare"] for r in results) or 1.0
            max_profit = max(r["estimated_profit_inr"] for r in results) or 1.0

            # Risk penalty map for composite scoring
            risk_penalty_map = {
                "Low Risk": 0.0,
                "Medium Risk": 0.15,
                "High Risk": 0.35,
            }

            for r in results:
                # Use production level for yield score (crop-specific normalization)
                level_map = {"High": 1.0, "Medium": 0.7, "Low": 0.4}
                norm_yield = level_map.get(r["production_level"], 0.5)

                norm_profit = r["estimated_profit_inr"] / max_profit
                suit = r["suitability_score"]
                d_bias = self._get_district_bias(resolved_district, r["crop_name"])
                norm_bias = min(d_bias / 2.0, 1.0)
                risk_pen = risk_penalty_map.get(r["risk_confidence"], 0.0)

                if profit_mode:
                    # Profit mode: 60% suitability + 40% profit
                    base_comp = suit * 0.60 + norm_profit * 0.40
                else:
                    # Safe mode: 35% suitability + 30% yield + 20% district + 15% risk
                    base_comp = suit * 0.35 + norm_yield * 0.30 + norm_bias * 0.20 + (1.0 - risk_pen) * 0.15
                
                # Apply extreme volatility penalty
                if r["price_volatility"] >= 0.4:
                    base_comp *= 0.8

                r["composite_score"] = round(base_comp, 4)
                r["district_bias"] = round(d_bias, 3)

        # ── Step 8: Crop Diversity & Wildcard Selection ────────────────────
        # Apply slight penalty to common generic crops to encourage location-specialized crops
        generic_crops = {"Bajra", "Moong(Green Gram)", "Sesamum", "Wheat", "Jowar", "Groundnut"}
        for r in results:
            if r["crop_name"] in generic_crops:
                r["composite_score"] *= 0.95
                
        results.sort(key=lambda x: x["composite_score"], reverse=True)
        
        top_results = []
        if top_n >= 3 and len(results) >= 3:
            # Pick 2 highest composite score safe crops
            safe_crops = [r for r in results if r["risk_confidence"] in ("Low Risk", "Medium Risk")]
            for top_safe in safe_crops[:2]:
                top_results.append(top_safe)
                
            # If we don't have 2 safe crops, fill from regular results
            while len(top_results) < 2:
                for r in results:
                    if r not in top_results:
                        top_results.append(r)
                        break
                        
            # Pick 1 wildcard (highest profit crop not already picked)
            profit_sorted = sorted(results, key=lambda x: x["estimated_profit_inr"], reverse=True)
            for wild in profit_sorted:
                if wild not in top_results:
                    top_results.append(wild)
                    break
        else:
            top_results = results[:top_n]
            
        # Ensure exact length
        top_results = top_results[:top_n]

        # ── Step 9: Build "avoid" section (filtered crops + why) ───────────
        crop_reqs = _load_requirements()
        avoid_list: list[dict[str, str]] = []
        rainfall_now = float(climate.get("Rainfall", 0))
        avg_temp_now  = float(climate.get("Temperature_Avg", 25))
        filtered_set = set(feasible_crops)
        for crop in season_crops:
            if crop not in filtered_set:
                req = crop_reqs.get(crop, {})
                valid_seasons = req.get("seasons", [])
                min_rain = req.get("min_rainfall_mm", 0)
                max_t = req.get("max_temp", 50)
                min_t = req.get("min_temp", 0)
                is_water_intensive = req.get("water_intensive", False)
                is_drought_ok = req.get("drought_tolerant", False)

                if season and valid_seasons and season not in valid_seasons and "Whole Year" not in valid_seasons:
                    avoid_reason = (
                        f"Wrong season — {crop} grows in {', '.join(valid_seasons)}, "
                        f"not {season}"
                    )
                elif is_water_intensive and not irrigated and rainfall_now < min_rain * 0.5:
                    avoid_reason = (
                        f"Requires heavy water ({min_rain}mm+) — only {rainfall_now:.0f}mm "
                        f"available and no irrigation"
                    )
                elif min_rain > 0 and rainfall_now < min_rain * 0.4 and not is_drought_ok:
                    avoid_reason = (
                        f"Needs {min_rain}mm+ rainfall — current {rainfall_now:.0f}mm is "
                        f"too low for this crop to survive"
                    )
                elif avg_temp_now > max_t + 3:
                    avoid_reason = (
                        f"Temperature too high ({avg_temp_now:.0f}°C) — {crop} max "
                        f"tolerance is {max_t}°C"
                    )
                elif avg_temp_now < min_t - 3:
                    avoid_reason = (
                        f"Temperature too low ({avg_temp_now:.0f}°C) — {crop} needs "
                        f"at least {min_t}°C"
                    )
                else:
                    avoid_reason = "Not suitable for current soil, water, or climate conditions"

                avoid_list.append({"crop": crop, "avoid_reason": avoid_reason})

        # ── Step 10: Confidence score + explanation ──────────────────────
        rainfall = climate.get("Rainfall", 0)   # needed here + step 11
        climate_years = climate.get("Climate_Years", 0)
        avg_suit = sum(r["suitability_score"] for r in top_results) / max(len(top_results), 1)
        confidence = min(100, int(
            (min(climate_years, 10) / 10) * 40 +  # data quality (40%)
            avg_suit * 40 +                        # suitability (40%)
            (0 if is_fallback else 20)             # location accuracy (20%)
        ))
        confidence_explanation = build_confidence_explanation(
            confidence=confidence,
            climate_years=climate_years,
            avg_suitability=avg_suit,
            is_fallback=is_fallback,
            rainfall=rainfall,
            season=season,
        )

        # ── Step 10b: Live alerts ─────────────────────────────────────────
        top_crop_names = [r["crop_name"] for r in top_results]
        live_alerts = generate_live_alerts(
            weather=climate,
            season=season,
            crops=top_crop_names,
            irrigated=irrigated,
        )

        # ── Step 11: District summary insight ────────────────────────────
        if rainfall < 100 and not irrigated:
            insight = f"{resolved_district.title()} is a low-rainfall area. Drought-tolerant crops recommended."
        elif rainfall < 500 and not irrigated:
            insight = f"{resolved_district.title()} has moderate rainfall. Mixed cropping possible."
        elif irrigated:
            insight = f"With irrigation in {resolved_district.title()}, wider crop selection available."
        else:
            insight = f"{resolved_district.title()} has good rainfall. Most crops viable."

        # ── Step 12: One-line farming advice ──────────────────────────────
        if not irrigated and rainfall < 100:
            advice = "Rainfed conditions — prefer drought-resistant crops and early sowing."
        elif not irrigated and rainfall < 500:
            advice = "Moderate rainfall expected — consider mulching and water conservation."
        elif irrigated:
            advice = "Irrigation available — consider high-value crops with proper water scheduling."
        else:
            advice = "Good growing conditions — diversify crops for risk management."

        # ── Step 13: Quick Safe vs Profit Comparison ──────────────────
        comparison = {}
        if results:
            risk_penalty_map = {"Low Risk": 0.0, "Medium Risk": 0.15, "High Risk": 0.35}
            temp_safe = []
            temp_profit = []
            for r in results:
                if r["suitability_score"] >= 0.4 and r["risk_confidence"] != "High Risk":
                    norm_y = r["yield_per_hectare"] / max_yield
                    norm_p = r["estimated_profit_inr"] / max_profit
                    s = r["suitability_score"]
                    n_b = min(r["district_bias"] / 2.0, 1.0)
                    risk_p = risk_penalty_map.get(r["risk_confidence"], 0.0)

                    s_safe = s * 0.35 + norm_y * 0.30 + n_b * 0.20 + (1.0 - risk_p) * 0.15
                    s_profit = norm_p * 0.45 + s * 0.35 + n_b * 0.20
                    temp_safe.append((s_safe, r["crop_name"]))
                    temp_profit.append((s_profit, r["crop_name"]))

            if temp_safe and temp_profit:
                temp_safe.sort(reverse=True)
                temp_profit.sort(reverse=True)
                top_safe = temp_safe[0][1]
                top_profit = temp_profit[0][1]
                if top_safe != top_profit:
                    comparison = {
                        "safe": top_safe,
                        "profit": top_profit
                    }

        # ── Summary block — fast-access for frontend ──────────────────────────
        # Designed so the UI can render a summary card without iterating results.
        best = top_results[0] if top_results else None
        summary: dict[str, Any] = {}
        if best:
            summary = {
                "best_crop":      best["crop_name"],
                "expected_yield": best["display_yield"],
                "suitability":    f"{int(best['suitability_score'] * 100)}%",
                "overall_risk":   best["risk_confidence"],
                "display_profit": best.get("display_profit", ""),
            }

        # ── One-line decision ─────────────────────────────────────────────────
        # Single actionable line — works in SMS, voice, banner, demo slide.
        if best:
            tip = best.get("explanation", {}).get("farmer_tip", "")
            if tip:
                one_line_decision = f"🌱 Best crop: {best['crop_name']} — {tip}"
            else:
                suit_pct = int(best["suitability_score"] * 100)
                one_line_decision = (
                    f"🌱 Best crop: {best['crop_name']} — "
                    f"{suit_pct}% suitability, {best['risk_confidence'].lower()}"
                )
        else:
            one_line_decision = "No suitable crops identified for current conditions."

        # ── Agronomic risk alerts (soil, NDVI, water) ─────────────────────────
        risk_alerts: list[dict] = []
        if best and "risk_detail" in best:
            risk_alerts = generate_risk_alerts(
                risk_detail=best["risk_detail"],
                soil=effective_soil or None,
                ndvi_value=ndvi_value,
                irrigated=irrigated,
            )

        return {
            "status": "ok",
            "location": city,
            "district": resolved_district,
            "season": season,
            "land_area_hectares": land_area_hectares,
            "irrigated": irrigated,
            "mode": "💰 High Profit" if profit_mode else "🛡 Safe Mode",
            # ── At-a-glance summary (frontend card) ──────────────────────────
            "summary": summary,
            "one_line_decision": one_line_decision,
            # ── Confidence (score + explanation) ─────────────────────────────
            "confidence": confidence,
            "confidence_explanation": confidence_explanation,
            # ── Planning Layer ────────────────────────────────────────────────
            "insight": insight,
            "advice": advice,
            "comparison": comparison,
            "recommendations": top_results,          # alias for frontend
            "top_recommended_crops": top_results,    # backward compat
            "avoid_crops": avoid_list[:5],
            # ── Alert Layer (weather + agronomic) ─────────────────────────────
            "alerts": live_alerts,
            "risk_alerts": risk_alerts,
            # ── Meta ──────────────────────────────────────────────────────────
            "location_warning": location_warning,
            "weather_source": (
                "Live OpenWeather (30%) + Seasonal Normals 10yr avg (70%)"
                if live_blended else
                "Seasonal Climate Normals (10-year avg)"
            ),
            "live_conditions": live_weather_desc or None,
            "weather_summary": {
                "Temperature_Avg": climate.get("Temperature_Avg"),
                "Temperature_Min": climate.get("Temperature_Min"),
                "Temperature_Max": climate.get("Temperature_Max"),
                "Humidity": climate.get("Humidity"),
                "Seasonal_Rainfall_mm": climate.get("Seasonal_Rainfall_mm",
                                                     climate.get("Rainfall")),
                "Climate_Period": climate.get("Climate_Period", "Historical"),
            },
            "crops_evaluated": len(results),
            "crops_filtered_out": crops_removed,
        }

    def recommend_safe(
        self,
        city: str,
        district: str | None = None,
        soil: dict[str, float] | None = None,
        top_n: int = 3,
        land_area_hectares: float = 1.0,
        irrigated: bool = False,
        profit_mode: bool = False,
    ) -> dict[str, Any]:
        """Same as recommend() but NEVER raises.

        Always returns a dict with 'status' key:
          - "ok"    → full recommendation payload
          - "error" → {"status": "error", "message": "..."}
        """
        try:
            result = self.recommend(
                city=city,
                district=district,
                soil=soil,
                top_n=top_n,
                land_area_hectares=land_area_hectares,
                irrigated=irrigated,
                profit_mode=profit_mode,
            )
            # recommend() may return {"error": "..."} for climate failures
            if "error" in result and "status" not in result:
                return {
                    "status": "error",
                    "message": result["error"],
                }
            return result
        except Exception as exc:
            logger.exception("recommend_safe caught unhandled error")
            return {
                "status": "error",
                "message": f"Unable to generate recommendations. Please try again. ({type(exc).__name__})",
            }
