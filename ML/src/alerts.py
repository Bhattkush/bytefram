"""
ML/src/alerts.py
================
Live Weather Alert Engine

Analyses live forecast weather data and generates:
  1. Short-term actionable alerts (next 3–5 days)
  2. Sowing / irrigation / harvest recommendations

The alerts module is intentionally stateless — it takes
a weather dict and returns a list of alert dicts.
"""
from __future__ import annotations

from typing import Any


# ── Alert severity levels ─────────────────────────────────────────────────────
INFO     = "info"
WARNING  = "warning"
CRITICAL = "critical"


def generate_live_alerts(
    weather: dict[str, Any],
    season: str,
    crops: list[str] | None = None,
    irrigated: bool = False,
) -> list[dict[str, str]]:
    """
    Looks at the current weather and generates plain-language alerts for the farmer.

    Each alert has:
      - A severity level (info / warning / critical)
      - A short title describing the situation
      - A specific action the farmer should take

    Alerts are generated for:
      - Extreme or unusual temperatures (heatwaves, frost risk)
      - Rainfall that's too high or too low for the season
      - Disease-friendly humidity conditions
      - Crop-specific warnings (e.g. Wheat struggling in warm Rabi weather)
      - Sowing window guidance (good time to plant, or hold off)
      - Irrigation guidance during heat

    If nothing stands out, the farmer gets an "all clear" message.
    """
    alerts: list[dict[str, str]] = []

    temp_avg  = weather.get("Temperature_Avg",  0.0) or 0.0
    temp_max  = weather.get("Temperature_Max",  0.0) or 0.0
    temp_min  = weather.get("Temperature_Min",  0.0) or 0.0
    humidity  = weather.get("Humidity",          0.0) or 0.0
    rainfall  = weather.get("Rainfall",          0.0) or 0.0

    crops = crops or []

    # Temperature alerts
    # 44°C+ is CRITICAL — almost no crop survives this without intervention
    # 40–43°C is a WARNING — delay sowing, keep plants hydrated
    # 37–39°C in Summer is normal — just remind them to watch moisture
    if temp_max >= 44:
        alerts.append({
            "severity": CRITICAL,
            "icon": "🔴",
            "title": f"Extreme heat expected ({temp_max:.0f}°C)",
            "action": "Avoid sowing. Provide shade nets if crops are already sown. Irrigate at dawn/dusk only.",
        })
    elif temp_max >= 40:
        alerts.append({
            "severity": WARNING,
            "icon": "🟠",
            "title": f"High temperature next few days ({temp_max:.0f}°C)",
            "action": "Consider delaying sowing by 2–3 days. Increase irrigation frequency.",
        })
    elif temp_max >= 37 and season == "Summer":
        alerts.append({
            "severity": INFO,
            "icon": "🟡",
            "title": f"Warm conditions ({temp_max:.0f}°C) — normal for Summer",
            "action": "Monitor soil moisture closely. Water in early morning.",
        })

    # Cold night alerts
    # Below 8°C during Rabi (winter crops like Wheat) can damage seedlings
    # Below 5°C anywhere is a frost risk — don't sow, protect existing plants
    if temp_min < 8 and season == "Rabi":
        alerts.append({
            "severity": WARNING,
            "icon": "🔵",
            "title": f"Cold nights expected ({temp_min:.0f}°C)",
            "action": "Risk of frost damage for seedlings. Use light mulching to retain soil warmth.",
        })
    elif temp_min < 5:
        alerts.append({
            "severity": CRITICAL,
            "icon": "🔴",
            "title": f"Frost risk — very cold nights ({temp_min:.0f}°C)",
            "action": "Do not sow. Protect existing crops with covers or smoky fires nearby.",
        })

    # Rainfall alerts for Kharif (monsoon) season
    # This is the most water-dependent season — drought here means crop failure
    # Below 20mm is very dangerous; 20–50mm still needs attention────────
    if rainfall < 20 and not irrigated and season == "Kharif":
        alerts.append({
            "severity": WARNING,
            "icon": "🟠",
            "title": "Very low rainfall expected for Kharif season",
            "action": "Consider drought-tolerant crops (Bajra, Jowar). Implement rainwater harvesting.",
        })
    elif rainfall < 50 and not irrigated and season == "Kharif":
        alerts.append({
            "severity": INFO,
            "icon": "🟡",
            "title": "Below-average rainfall expected",
            "action": "Prioritise crops with moderate water needs. Use drip irrigation if possible.",
        })

    if rainfall > 400:
        alerts.append({
            "severity": WARNING,
            "icon": "🌧",
            "title": f"Heavy rainfall season ({rainfall:.0f} mm expected)",
            "action": "Ensure proper field drainage. Avoid sowing in low-lying waterlogged areas.",
        })

    # Humidity alerts
    # High humidity (80%+) combined with warm temperatures is a recipe for
    # fungal diseases like blight and mildew — very common in Gujarat monsoons
    # Very dry air below 25% means crops lose moisture rapidly through their leaves────────
    if humidity > 80 and temp_avg > 28:
        alerts.append({
            "severity": WARNING,
            "icon": "💧",
            "title": f"High humidity ({humidity:.0f}%) — fungal disease risk",
            "action": "Increase spacing between plants. Apply preventive fungicide. Avoid overhead irrigation.",
        })
    elif humidity < 25 and not irrigated:
        alerts.append({
            "severity": INFO,
            "icon": "☀️",
            "title": f"Very dry air ({humidity:.0f}% humidity)",
            "action": "Crops will dry out quickly. Mulch the topsoil to retain moisture.",
        })

    # Crop-specific alerts
    # These only fire when the recommended crop list contains that crop
    # Keeps alerts relevant — no point warning about Wheat if the farmer is growing Bajra────
    crop_set = set(crops)

    if "Sugarcane" in crop_set and temp_max >= 42:
        alerts.append({
            "severity": WARNING,
            "icon": "🌿",
            "title": "Sugarcane: heat stress risk",
            "action": "Increase irrigation cycles. Apply potassium fertiliser to improve heat tolerance.",
        })

    if "Wheat" in crop_set and temp_avg > 25 and season == "Rabi":
        alerts.append({
            "severity": WARNING,
            "icon": "🌾",
            "title": "Wheat: temperature above optimal range",
            "action": "Wheat performs best below 25°C. Irrigate during grain filling stage. Consider early-maturing varieties.",
        })

    if ("Cotton(lint)" in crop_set or "Groundnut" in crop_set) and rainfall < 30:
        alerts.append({
            "severity": INFO,
            "icon": "🪴",
            "title": "Cotton/Groundnut: adequate water needed at germination",
            "action": "Ensure at least 1 pre-sowing irrigation. Mulch rows to retain soil moisture.",
        })

    # Sowing window advice
    # Tells the farmer if conditions are currently ideal for planting
    # Based on temperature + rainfall both being in the right range together────
    if season == "Kharif" and 30 <= temp_avg <= 35 and rainfall >= 50:
        alerts.append({
            "severity": INFO,
            "icon": "✅",
            "title": "Good sowing window for Kharif crops",
            "action": "Conditions are favourable. Begin sowing within the next 7–10 days.",
        })
    elif season == "Rabi" and 15 <= temp_avg <= 22:
        alerts.append({
            "severity": INFO,
            "icon": "✅",
            "title": "Optimal Rabi sowing conditions",
            "action": "Temperature is ideal for Rabi crops. Sow within the next 5–7 days.",
        })

    # Irrigation advice
    # During heatwaves, irrigated farmers should water more frequently
    # to prevent soil moisture from dropping below the critical threshold─────
    if irrigated and temp_max >= 38:
        alerts.append({
            "severity": INFO,
            "icon": "💧",
            "title": "Increase irrigation frequency during heat",
            "action": "Irrigate every 5–6 days instead of weekly. Prefer drip systems to avoid leaf scorch.",
        })

    # If nothing triggered above, the conditions look fine
    # Give the farmer a positive confirmation so they know the system checked
    if not alerts:
        alerts.append({
            "severity": INFO,
            "icon": "✅",
            "title": "Weather conditions look stable",
            "action": "No critical alerts for this period. Proceed with planned agricultural activities.",
        })

    # Sort: critical first, then warning, then info
    _severity_order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    alerts.sort(key=lambda a: _severity_order.get(a["severity"], 9))

    return alerts


def build_confidence_explanation(
    confidence: int,
    climate_years: int,
    avg_suitability: float,
    is_fallback: bool,
    rainfall: float,
    season: str,
) -> dict[str, Any]:
    """
    Turns the confidence score into something a farmer actually understands.

    Rather than just showing "Confidence: 83%", this breaks it down into
    the specific reasons that drove the score up or down:
      - How many years of climate data was available
      - How well the recommended crops match local conditions
      - Whether we found the exact district or had to use a fallback
      - Whether this season's rainfall is within the normal range

    Returns a dict with the score, a plain-English rating label,
    a colour indicator (green/yellow/red), and the list of factors.
    """
    factors: list[dict[str, str]] = []

    # Factor 1: Data quality (how many years of climate data)
    if climate_years >= 10:
        factors.append({"factor": "Climate data quality", "status": "✔", "detail": f"{climate_years}-year historical average — high reliability"})
    elif climate_years >= 5:
        factors.append({"factor": "Climate data quality", "status": "~", "detail": f"{climate_years}-year average — moderate reliability"})
    else:
        factors.append({"factor": "Climate data quality", "status": "✘", "detail": "Limited climate data — lower confidence"})

    # Factor 2: Suitability score
    if avg_suitability >= 0.7:
        factors.append({"factor": "Crop-climate match", "status": "✔", "detail": "Strong match between recommended crops and local conditions"})
    elif avg_suitability >= 0.4:
        factors.append({"factor": "Crop-climate match", "status": "~", "detail": "Moderate match — some crops are borderline suitable"})
    else:
        factors.append({"factor": "Crop-climate match", "status": "✘", "detail": "Weak match — conditions are challenging for most crops"})

    # Factor 3: Location accuracy
    if not is_fallback:
        factors.append({"factor": "Location accuracy", "status": "✔", "detail": "District found in Gujarat database — localised data used"})
    else:
        factors.append({"factor": "Location accuracy", "status": "✘", "detail": "District not found — using regional fallback data"})

    # Factor 4: Rainfall stability
    if season == "Kharif" and 100 <= rainfall <= 800:
        factors.append({"factor": "Rainfall variability", "status": "✔", "detail": f"Seasonal rainfall ({rainfall:.0f}mm) within normal range"})
    elif season == "Rabi" and rainfall < 200:
        factors.append({"factor": "Rainfall variability", "status": "✔", "detail": "Rabi season typically low-rainfall — consistent with expectations"})
    else:
        factors.append({"factor": "Rainfall variability", "status": "~", "detail": f"Rainfall ({rainfall:.0f}mm) may deviate from crop requirements"})

    # Determine rating label
    if confidence >= 75:
        rating = "High Confidence"
        color  = "green"
    elif confidence >= 50:
        rating = "Moderate Confidence"
        color  = "yellow"
    else:
        rating = "Low Confidence"
        color  = "red"

    return {
        "score": confidence,
        "rating": rating,
        "color": color,
        "factors": factors,
    }


def generate_risk_alerts(
    risk_detail: dict,
    soil: dict | None = None,
    ndvi_value: float | None = None,
    irrigated: bool = False,
) -> list[dict[str, str]]:
    """Generate agronomic risk alerts from the structured risk dict.

    Companion to generate_live_alerts() — that function handles weather;
    this one handles soil, NDVI, and crop risk signals.

    Produces plain-language, actionable alerts the farmer can act on:
      ⚠️ Soil fertility low → specific fertilizer advice
      ⚠️ High drought risk → water management advice
      ⚠️ Degraded land → soil restoration advice
    """
    alerts: list[dict[str, str]] = []

    drought_risk  = risk_detail.get("drought_risk",  "None")
    heat_risk     = risk_detail.get("heat_risk",     "None")
    soil_risk     = risk_detail.get("soil_risk",     "None")
    ndvi_risk     = risk_detail.get("ndvi_risk",     "None")
    overall       = risk_detail.get("overall",       "Low Risk")
    confidence    = risk_detail.get("yield_confidence", 1.0)

    # ── Drought / water risk ──────────────────────────────────────────────────
    if drought_risk == "High":
        action = (
            "Use drip irrigation and mulch topsoil to retain moisture."
            if irrigated else
            "Switch to drought-resistant crops (Bajra, Moong). Harvest rainwater."
        )
        alerts.append({
            "severity": CRITICAL,
            "icon": "🔴",
            "title": "High drought risk — water shortage expected",
            "action": action,
        })
    elif drought_risk == "Medium":
        alerts.append({
            "severity": WARNING,
            "icon": "🟠",
            "title": "Moderate water stress likely",
            "action": "Prefer crops with low water needs. Irrigate at sowing stage.",
        })

    # ── Soil fertility risk ───────────────────────────────────────────────────
    if soil_risk == "High":
        alerts.append({
            "severity": CRITICAL,
            "icon": "🔴",
            "title": "Soil fertility critical — multiple nutrient deficiencies",
            "action": "Apply DAP + urea before sowing. Add compost/FYM to improve organic matter.",
        })
    elif soil_risk == "Medium":
        p_low = soil and float(soil.get("P", 99)) < 20
        n_low = soil and float(soil.get("N", 99)) < 40
        if p_low:
            alerts.append({
                "severity": WARNING,
                "icon": "🟠",
                "title": "Low phosphorus (P) — main yield limiter",
                "action": "Apply DAP or SSP fertilizer at basal dose before sowing.",
            })
        elif n_low:
            alerts.append({
                "severity": WARNING,
                "icon": "🟠",
                "title": "Low nitrogen (N) — top-dress recommended",
                "action": "Apply urea in split doses — at sowing and 30 days after.",
            })
        else:
            alerts.append({
                "severity": WARNING,
                "icon": "🟠",
                "title": "Soil fertility below optimal",
                "action": "Apply balanced NPK fertilizer. Test soil before next season.",
            })

    # ── NDVI / land health risk ───────────────────────────────────────────────
    if ndvi_risk == "High":
        alerts.append({
            "severity": WARNING,
            "icon": "🏜️",
            "title": "Land degradation detected — poor vegetation cover",
            "action": "Add compost or FYM before sowing. Consider cover crop after harvest.",
        })

    # ── Heat stress risk ──────────────────────────────────────────────────────
    if heat_risk == "High":
        alerts.append({
            "severity": CRITICAL,
            "icon": "🔥",
            "title": "Severe heat stress risk",
            "action": "Sow heat-tolerant varieties. Irrigate at dawn and dusk. Avoid bare soil.",
        })
    elif heat_risk == "Medium":
        alerts.append({
            "severity": WARNING,
            "icon": "🌡️",
            "title": "Heat stress possible at peak season",
            "action": "Monitor crop canopy temperature. Increase irrigation frequency.",
        })

    # ── Yield confidence low ──────────────────────────────────────────────────
    if confidence < 0.50:
        alerts.append({
            "severity": WARNING,
            "icon": "⚠️",
            "title": f"Low yield confidence ({confidence:.0%})",
            "action": "Conditions are challenging. Consider crop insurance or smaller plot trial.",
        })

    # ── All clear ─────────────────────────────────────────────────────────────
    if not alerts and overall == "Low Risk":
        alerts.append({
            "severity": INFO,
            "icon": "✅",
            "title": "Agronomic conditions look good",
            "action": "No critical soil or environmental risks detected. Proceed with sowing plan.",
        })

    # Sort: critical first, then warning, then info
    _severity_order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    alerts.sort(key=lambda a: _severity_order.get(a["severity"], 9))

    return alerts
