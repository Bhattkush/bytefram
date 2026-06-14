"""
ML/src/ndvi_loader.py
======================
Provides realistic per-district × per-season NDVI (Normalized Difference
Vegetation Index) values for Gujarat.

What is NDVI?
  A satellite-derived index from 0.0 to 1.0 measuring vegetation health:
    0.0 – 0.2  → bare soil, desert, water
    0.2 – 0.4  → sparse vegetation, scrubland (arid zones)
    0.4 – 0.6  → moderate agriculture (semi-arid, rainfed)
    0.6 – 0.8  → dense healthy vegetation (alluvial, irrigated, coastal)
    0.8 – 1.0  → thick forest

Why NDVI matters for crop prediction:
  Satellite NDVI at peak season reflects actual crop health on the ground.
  A district with NDVI = 0.7 in Kharif has dense active vegetation —
  the model can infer better soil-water conditions than pure soil data shows.

Data source (current):
  District-level NDVI averages estimated from regional vegetation patterns
  based on ISRO Bhuvan / MODIS NDVI product averages for Gujarat (2015–2024).
  Ground truth: Coastal > Alluvial plains > Semi-arid > Arid.

Season variation:
  Kharif (Jun–Oct): peak NDVI — monsoon rains drive maximum green cover
  Rabi  (Nov–Mar): 80% of Kharif — winter crops growing but drier
  Summer(Apr–Jun): 55% of Kharif — near-drought, minimal active vegetation

Future upgrade path:
  Replace the lookup table with a real-time Google Earth Engine /
  Sentinel-2 NDVI API call for live satellite values per district + date.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Per-district base NDVI (Kharif season = peak value)
# Grouped by agro-ecological zone and dominant land use
_DISTRICT_NDVI: dict[str, float] = {
    # Coastal & high-rainfall (forests, plantations, paddy)
    "dang":              0.74,
    "valsad":            0.72,
    "navsari":           0.70,
    "tapi":              0.68,
    "surat":             0.66,
    "narmada":           0.65,
    "bharuch":           0.62,

    # Alluvial plains (irrigated agriculture — sugarcane, tobacco, vegetables)
    "kheda":             0.62,
    "anand":             0.60,
    "vadodara":          0.58,
    "panchmahal":        0.55,
    "chhota udaipur":    0.53,
    "dahod":             0.52,
    "mahisagar":         0.52,

    # Semi-arid (groundnut belt, cotton, millet)
    "junagadh":          0.50,
    "gir somnath":       0.48,
    "amreli":            0.47,
    "bhavnagar":         0.46,
    "botad":             0.45,
    "rajkot":            0.45,
    "porbandar":         0.44,
    "sabarkantha":       0.44,
    "arvalli":           0.43,
    "aravalli":          0.43,

    # Semi-arid north (wheat, mustard, castor)
    "gandhinagar":       0.42,
    "ahmedabad":         0.42,
    "mehsana":           0.40,
    "patan":             0.38,
    "morbi":             0.38,
    "surendranagar":     0.36,
    "jamnagar":          0.36,

    # Arid / coastal sandy (millet, sesamum, sparse grazing)
    "banaskantha":       0.33,
    "devbhoomi dwarka":  0.32,
    "kutch":             0.26,
}

# Season multipliers — Kharif = baseline, others scaled down
_SEASON_MULTIPLIER: dict[str, float] = {
    "Kharif": 1.00,
    "Rabi":   0.80,
    "Summer": 0.55,
}

# Gujarat state average fallback
_STATE_AVERAGE_NDVI: float = 0.48


def get_ndvi(district: str, season: str = "Kharif") -> float:
    """
    Returns an estimated NDVI_Peak value for a given district and season.

    Args:
        district: District name (case-insensitive, spaces/hyphens handled)
        season:   "Kharif", "Rabi", or "Summer"

    Returns:
        float in range [0.20, 0.80] — rounded to 2 decimal places

    Always returns a value — never raises an exception.
    """
    # Normalise district name for lookup
    key = (
        str(district)
        .lower()
        .strip()
        .replace(" district", "")
        .replace("-", " ")
        .replace("_", " ")
    )

    # Look up base (Kharif peak) NDVI
    base_ndvi = None

    # Exact match
    if key in _DISTRICT_NDVI:
        base_ndvi = _DISTRICT_NDVI[key]
    else:
        # Partial match
        for stored in _DISTRICT_NDVI:
            if stored in key or key in stored:
                base_ndvi = _DISTRICT_NDVI[stored]
                break

    if base_ndvi is None:
        logger.warning("No NDVI entry for '%s' — using Gujarat state average %.2f", district, _STATE_AVERAGE_NDVI)
        base_ndvi = _STATE_AVERAGE_NDVI

    # Apply season multiplier
    multiplier = _SEASON_MULTIPLIER.get(season, 0.80)
    ndvi = round(base_ndvi * multiplier, 2)

    # Hard clamp to realistic range
    return max(0.15, min(0.82, ndvi))


def get_ndvi_label(ndvi: float) -> str:
    """Returns a human-readable vegetation health label for a given NDVI value."""
    if ndvi >= 0.65:
        return "Dense vegetation (high crop potential)"
    elif ndvi >= 0.50:
        return "Moderate vegetation (good agriculture)"
    elif ndvi >= 0.35:
        return "Sparse vegetation (semi-arid conditions)"
    else:
        return "Low vegetation (arid / stressed land)"


def get_seasonal_ndvi_details(
    district: str,
    season: str = "Kharif",
    rainfall: float | None = None,
    irrigated: bool = False,
) -> dict[str, Any]:
    """Return a rich NDVI detail dict with weather-aware adjustment.

    Enhancement over get_ndvi():
      - Adjusts NDVI down when actual rainfall << seasonal expectation
        (drought stress suppresses vegetation even in good districts)
      - Adjusts NDVI up slightly when irrigated
        (irrigation sustains canopy above rainfed baselines)

    This makes NDVI dynamic rather than a pure district×season lookup.

    Args:
        district:  District name (case-insensitive)
        season:    \"Kharif\", \"Rabi\", or \"Summer\"
        rainfall:  Actual or forecast seasonal rainfall in mm (optional)
        irrigated: Whether the farm is irrigated

    Returns:
        dict with keys: district, season, base_ndvi, seasonal_ndvi,
                        adjusted_ndvi, label, adjustment_reason
    """
    # Look up base (Kharif peak) NDVI using same logic as get_ndvi()
    key = (
        str(district)
        .lower()
        .strip()
        .replace(" district", "")
        .replace("-", " ")
        .replace("_", " ")
    )
    base_ndvi = None
    if key in _DISTRICT_NDVI:
        base_ndvi = _DISTRICT_NDVI[key]
    else:
        for stored in _DISTRICT_NDVI:
            if stored in key or key in stored:
                base_ndvi = _DISTRICT_NDVI[stored]
                break
    if base_ndvi is None:
        base_ndvi = _STATE_AVERAGE_NDVI

    # Apply season multiplier (same as get_ndvi)
    multiplier = _SEASON_MULTIPLIER.get(season, 0.80)
    seasonal_ndvi = round(base_ndvi * multiplier, 2)
    adjusted_ndvi = seasonal_ndvi
    adjustment_reason: str | None = None

    # Expected seasonal rainfall benchmarks for Gujarat
    _EXPECTED_RAIN: dict[str, float] = {
        "Kharif": 600.0,
        "Rabi":   220.0,
        "Summer":  80.0,
    }

    if rainfall is not None:
        expected = _EXPECTED_RAIN.get(season, 400.0)
        if rainfall < expected * 0.5:
            # Severe rainfall deficit → vegetation suppressed
            adjusted_ndvi = round(seasonal_ndvi * 0.82, 2)
            adjustment_reason = (
                f"Reduced 18% — rainfall ({rainfall:.0f}mm) is "
                f"less than half of expected ({expected:.0f}mm)"
            )
        elif rainfall < expected * 0.75:
            # Moderate deficit
            adjusted_ndvi = round(seasonal_ndvi * 0.92, 2)
            adjustment_reason = (
                f"Reduced 8% — below-average rainfall "
                f"({rainfall:.0f}mm vs {expected:.0f}mm expected)"
            )
        elif rainfall > expected * 1.5:
            # Above-average rain → slightly lusher vegetation
            adjusted_ndvi = round(min(0.82, seasonal_ndvi * 1.05), 2)
            adjustment_reason = (
                f"Boosted 5% — above-average rainfall "
                f"({rainfall:.0f}mm vs {expected:.0f}mm expected)"
            )

    if irrigated:
        pre_irr = adjusted_ndvi
        adjusted_ndvi = round(min(0.82, adjusted_ndvi * 1.08), 2)
        boost = round(adjusted_ndvi - pre_irr, 2)
        irr_note = f"Irrigation +{boost:.2f} NDVI bonus"
        adjustment_reason = (
            f"{adjustment_reason}; {irr_note}"
            if adjustment_reason else irr_note
        )

    # Hard clamp to realistic range
    adjusted_ndvi = max(0.15, min(0.82, adjusted_ndvi))

    return {
        "district":          district,
        "season":            season,
        "base_ndvi":         round(base_ndvi, 2),
        "seasonal_ndvi":     seasonal_ndvi,
        "adjusted_ndvi":     round(adjusted_ndvi, 2),
        "label":             get_ndvi_label(adjusted_ndvi),
        "adjustment_reason": adjustment_reason,
    }
