"""
Climate Client — Seasonal Climate Normals from Open-Meteo
==========================================================
Fetches 10-year historical weather data and computes seasonal averages
that match the training data's scale (seasonal rainfall in mm, avg temps).

Uses Open-Meteo Archive API — FREE, no API key required.
Results are cached locally to avoid repeated API calls.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from .constants import (
    CLIMATE_CACHE_DIR,
    DISTRICT_COORDINATES,
    CITY_TO_DISTRICT,
    SEASON_MONTHS,
)


class ClimateClientError(Exception):
    pass


# ── Cache helpers ─────────────────────────────────────────────────────────────

CACHE_EXPIRY_SECONDS = 6 * 3600  # 6 hours


def _cache_path(district: str, season: str) -> Path:
    CLIMATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CLIMATE_CACHE_DIR / f"{district}_{season}.json"


def _read_cache(district: str, season: str) -> dict | None:
    path = _cache_path(district, season)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_timestamp", 0) < CACHE_EXPIRY_SECONDS:
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _write_cache(district: str, season: str, data: dict) -> None:
    path = _cache_path(district, season)
    data["_timestamp"] = time.time()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Coordinate resolution ────────────────────────────────────────────────────

def resolve_coordinates(city: str, district: str | None = None) -> tuple[float, float, str, bool]:
    """Resolve city/district to (lat, lon, district_name, is_fallback).

    Priority:
      1. Explicit district arg → lookup in DISTRICT_COORDINATES
      2. City name → lookup in CITY_TO_DISTRICT → DISTRICT_COORDINATES
      3. Direct city name as district
      4. Fallback to Ahmedabad (with is_fallback=True)
    """
    key = (district or "").strip().lower()
    if key and key in DISTRICT_COORDINATES:
        lat, lon = DISTRICT_COORDINATES[key]
        return lat, lon, key, False

    city_key = city.strip().lower()
    mapped = CITY_TO_DISTRICT.get(city_key)
    if mapped and mapped in DISTRICT_COORDINATES:
        lat, lon = DISTRICT_COORDINATES[mapped]
        return lat, lon, mapped, False

    # Try direct city name as district
    if city_key in DISTRICT_COORDINATES:
        lat, lon = DISTRICT_COORDINATES[city_key]
        return lat, lon, city_key, False

    # Fallback — Ahmedabad (flag it so caller can warn)
    lat, lon = DISTRICT_COORDINATES["ahmedabad"]
    return lat, lon, "ahmedabad", True


# ── Season date range computation ────────────────────────────────────────────

def _season_date_range(season: str, years_back: int = 10) -> list[tuple[str, str]]:
    """Return list of (start_date, end_date) strings for the given season
    going back `years_back` years.

    Handles seasons that wrap around year boundary (e.g., Rabi: Nov–Feb).
    """
    start_month, end_month = SEASON_MONTHS.get(season, (6, 10))
    current_year = datetime.now().year
    ranges = []

    for offset in range(1, years_back + 1):
        year = current_year - offset
        if start_month <= end_month:
            # Same year: e.g., Kharif June–Oct, Summer Mar–May
            start = f"{year}-{start_month:02d}-01"
            # Last day of end month (approximate with 28)
            if end_month == 2:
                end = f"{year}-{end_month:02d}-28"
            elif end_month in (4, 6, 9, 11):
                end = f"{year}-{end_month:02d}-30"
            else:
                end = f"{year}-{end_month:02d}-31"
            ranges.append((start, end))
        else:
            # Wraps: e.g., Rabi Nov(year) – Feb(year+1)
            start = f"{year}-{start_month:02d}-01"
            next_year = year + 1
            if end_month == 2:
                end = f"{next_year}-{end_month:02d}-28"
            elif end_month in (4, 6, 9, 11):
                end = f"{next_year}-{end_month:02d}-30"
            else:
                end = f"{next_year}-{end_month:02d}-31"
            ranges.append((start, end))

    return ranges


# ── Open-Meteo API ───────────────────────────────────────────────────────────

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _fetch_one_period(
    lat: float, lon: float, start_date: str, end_date: str
) -> dict[str, list[float]]:
    """Fetch daily weather for one period from Open-Meteo Archive."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join([
            "temperature_2m_mean",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "relative_humidity_2m_mean",  # Open-Meteo may not have this — handle gracefully
        ]),
        "timezone": "Asia/Kolkata",
    }

    try:
        resp = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ClimateClientError(f"Open-Meteo API error: {exc}")

    data = resp.json()
    daily = data.get("daily", {})

    return {
        "temp_mean": [v for v in (daily.get("temperature_2m_mean") or []) if v is not None],
        "temp_max":  [v for v in (daily.get("temperature_2m_max") or []) if v is not None],
        "temp_min":  [v for v in (daily.get("temperature_2m_min") or []) if v is not None],
        "precip":    [v for v in (daily.get("precipitation_sum") or []) if v is not None],
        "humidity":  [v for v in (daily.get("relative_humidity_2m_mean") or []) if v is not None],
    }


def _safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ── Main entry point ─────────────────────────────────────────────────────────

def fetch_seasonal_climate(
    city: str,
    season: str,
    district: str | None = None,
    years_back: int = 10,
) -> dict[str, Any]:
    """Compute seasonal climate normals for a location.

    Returns a dict matching the model's expected feature names:
      Temperature_Avg, Temperature_Min, Temperature_Max,
      Rainfall, Humidity, Temp_Range, etc.

    The values represent the AVERAGE CONDITIONS during the crop growing season,
    computed over `years_back` years of historical data.
    """
    lat, lon, resolved_district, is_fallback = resolve_coordinates(city, district)

    # Check cache first
    cached = _read_cache(resolved_district, season)
    if cached:
        # Return cached data (strip internal timestamp)
        result = {k: v for k, v in cached.items() if not k.startswith("_")}
        result["_source"] = "cache"
        result["_district"] = resolved_district
        result["_fallback"] = is_fallback
        return result

    # Fetch historical data for multiple years
    all_temp_mean: list[float] = []
    all_temp_max:  list[float] = []
    all_temp_min:  list[float] = []
    all_precip:    list[float] = []
    all_humidity:  list[float] = []

    # Seasonal total rainfall per year (to average properly)
    yearly_rainfall: list[float] = []

    date_ranges = _season_date_range(season, years_back)

    for start_date, end_date in date_ranges:
        try:
            daily = _fetch_one_period(lat, lon, start_date, end_date)
        except ClimateClientError:
            continue  # Skip failed years

        all_temp_mean.extend(daily["temp_mean"])
        all_temp_max.extend(daily["temp_max"])
        all_temp_min.extend(daily["temp_min"])
        all_humidity.extend(daily["humidity"])

        # Seasonal rainfall = SUM of daily precipitation for one season-year
        if daily["precip"]:
            yearly_rainfall.append(sum(daily["precip"]))
        all_precip.extend(daily["precip"])

    if not all_temp_mean:
        raise ClimateClientError(
            f"Could not fetch any climate data for {city}/{resolved_district} ({season})"
        )

    # Compute normals
    avg_temp = round(_safe_mean(all_temp_mean), 2)
    min_temp = round(min(all_temp_min) if all_temp_min else 0.0, 2)
    max_temp = round(max(all_temp_max) if all_temp_max else 0.0, 2)
    avg_humidity = round(_safe_mean(all_humidity), 2) if all_humidity else 50.0
    seasonal_rainfall = round(_safe_mean(yearly_rainfall), 2) if yearly_rainfall else 0.0
    temp_range = round(max_temp - min_temp, 2)

    result = {
        "Temperature_Avg": avg_temp,
        "Temperature_Min": min_temp,
        "Temperature_Max": max_temp,
        "Rainfall": seasonal_rainfall,
        "Humidity": avg_humidity,
        "Temp_Range": temp_range,
        "Seasonal_Rainfall": seasonal_rainfall,
        # Extra metadata for display
        "Seasonal_Rainfall_mm": seasonal_rainfall,
        "Climate_Years": len(yearly_rainfall),
        "Climate_Period": f"Last {years_back} years",
    }

    # Cache the result
    _write_cache(resolved_district, season, result)

    result["_source"] = "api"
    result["_district"] = resolved_district
    result["_fallback"] = is_fallback
    return result
