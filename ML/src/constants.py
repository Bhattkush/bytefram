from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = PROJECT_ROOT / "ML"
DATA_DIR = ML_ROOT / "data"
MODELS_DIR = ML_ROOT / "models"
CLIMATE_CACHE_DIR = DATA_DIR / "climate_cache"

BASE_REQUIRED_COLUMNS = [
    "District",
    "Year",
    "Season",
    "Crop",
    "Temperature_Avg",
    "Temperature_Min",
    "Temperature_Max",
    "Rainfall",
    "Humidity",
    "Yield",
]

SOIL_FEATURE_COLUMNS = ["N", "P", "K", "pH", "Organic_Carbon"]
ENGINEERED_COLUMNS = [
    "GDD",
    "Seasonal_Rainfall",
    "Temp_Range",
    "Humidity_Rain_Interaction",
    "NDVI_Peak",
]

SEASON_DAYS = {
    "Kharif": 120,
    "Rabi": 130,
    "Summer": 100,
}

# Month ranges for each season (start_month, end_month inclusive)
# Used by climate_client to fetch correct historical period
SEASON_MONTHS = {
    "Kharif": (6, 10),    # June – October  (monsoon)
    "Rabi":   (11, 2),    # November – February (winter)
    "Summer": (3, 5),     # March – May (hot)
}

DEFAULT_SOIL_VALUES = {
    "N": 70.0,
    "P": 40.0,
    "K": 45.0,
    "pH": 6.7,
    "Organic_Carbon": 0.75,
}

# Gujarat district centroids (lat, lon) for Open-Meteo API
# Covers all 33 districts of Gujarat
DISTRICT_COORDINATES: dict[str, tuple[float, float]] = {
    "ahmedabad":        (23.02, 72.57),
    "amreli":           (21.60, 71.22),
    "anand":            (22.56, 72.95),
    "aravalli":         (23.40, 73.30),
    "banaskantha":      (24.17, 72.43),
    "bharuch":          (21.70, 72.97),
    "bhavnagar":        (21.77, 72.15),
    "botad":            (22.17, 71.67),
    "chhota udaipur":   (22.30, 74.02),
    "dahod":            (22.83, 74.25),
    "dang":             (20.75, 73.68),
    "devbhoomi dwarka": (22.20, 69.65),
    "gandhinagar":      (23.22, 72.68),
    "gir somnath":      (20.90, 70.50),
    "jamnagar":         (22.47, 70.07),
    "junagadh":         (21.52, 70.47),
    "kheda":            (22.75, 72.68),
    "kutch":            (23.73, 69.86),
    "mahisagar":        (23.12, 73.63),
    "mehsana":          (23.60, 72.40),
    "morbi":            (22.82, 70.83),
    "narmada":          (21.87, 73.50),
    "navsari":          (20.95, 72.92),
    "panchmahal":       (22.75, 73.60),
    "patan":            (23.85, 72.13),
    "porbandar":        (21.64, 69.60),
    "rajkot":           (22.30, 70.78),
    "sabarkantha":      (23.63, 73.00),
    "surat":            (21.17, 72.83),
    "surendranagar":    (22.73, 71.68),
    "tapi":             (21.10, 73.40),
    "vadodara":         (22.30, 73.19),
    "valsad":           (20.63, 72.93),
}

# City → district mapping for common Gujarat cities
# When user passes city name, we resolve to nearest district
CITY_TO_DISTRICT: dict[str, str] = {
    "ahmedabad":    "ahmedabad",
    "surat":        "surat",
    "vadodara":     "vadodara",
    "rajkot":       "rajkot",
    "bhavnagar":    "bhavnagar",
    "jamnagar":     "jamnagar",
    "junagadh":     "junagadh",
    "gandhinagar":  "gandhinagar",
    "anand":        "anand",
    "bharuch":      "bharuch",
    "mehsana":      "mehsana",
    "navsari":      "navsari",
    "porbandar":    "porbandar",
    "morbi":        "morbi",
    "patan":        "patan",
    "dahod":        "dahod",
    "kutch":        "kutch",
    "bhuj":         "kutch",
    "amreli":       "amreli",
    "botad":        "botad",
    "kheda":        "kheda",
    "nadiad":       "kheda",
    "godhra":       "panchmahal",
    "palanpur":     "banaskantha",
    "himmatnagar":  "sabarkantha",
    "modasa":       "aravalli",
    "lunawada":     "mahisagar",
    "veraval":      "gir somnath",
    "vapi":         "valsad",
    "bardoli":      "surat",
    "vyara":        "tapi",
    "rajpipla":     "narmada",
    "chhota udaipur": "chhota udaipur",
    "dwarka":       "devbhoomi dwarka",
    "surendranagar": "surendranagar",
    "wadhwan":      "surendranagar",
}
