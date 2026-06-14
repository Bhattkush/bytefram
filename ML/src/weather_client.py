"""
Live Weather Client — OpenWeatherMap API
==========================================
Fetches current live weather for a city and blends it with historical
seasonal normals to give the model a more accurate picture of today.

Two modes:
  1. fetch_live_weather(city)    → current conditions only (used for alerts)
  2. blend_with_historical(...)  → mixes live data + historical for predictions

Why blend and not just use live data?
  A crop takes 90 to 180 days to grow. Today's temperature alone tells us
  very little about the full season. Historical normals tell us what's
  typical; live data tells us how this specific day compares. Together,
  they give a more grounded prediction than either source alone.

  blend_weight controls how much live data influences the result:
    0.0  = pure historical (ignores today entirely)
    0.3  = 30% live + 70% historical  <-- default, a balanced mix
    1.0  = pure live (risky — one hot day doesn't define a whole season)
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(dotenv_path=_ENV_PATH)
except ImportError:
    pass

logger = logging.getLogger(__name__)

OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5"
LIVE_BLEND_WEIGHT = 0.30   # 30% live, 70% historical


class WeatherClientError(Exception):
    pass


def _get_api_key() -> str:
    key = os.getenv("OPENWEATHER_API_KEY") or os.getenv("WEATHER_API_KEY")
    if not key:
        raise WeatherClientError(
            "OPENWEATHER_API_KEY not set. Add it to .env file."
        )
    return key


# ── Current Conditions ────────────────────────────────────────────────────────

def fetch_live_weather(city: str) -> dict[str, Any]:
    """
    Gets the current weather conditions for a city from OpenWeatherMap.

    Returns a dict using the same keys the ML model expects, so it can be
    used directly as input or blended with historical data.

    Also includes some extra metadata (wind speed, feels-like temp, pressure)
    which are useful for generating short-term alerts even though the model
    doesn't use them directly.
    """
    api_key = _get_api_key()
    url = f"{OPENWEATHER_BASE}/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except requests.Timeout:
        raise WeatherClientError(f"OpenWeather took too long to respond for city: {city}")
    except requests.HTTPError as e:
        if resp.status_code == 404:
            raise WeatherClientError(f"City '{city}' not found in OpenWeather. Check spelling.")
        if resp.status_code == 401:
            raise WeatherClientError("OpenWeather API key is invalid or expired.")
        raise WeatherClientError(f"OpenWeather returned an error: {e}")
    except requests.RequestException as e:
        raise WeatherClientError(f"Could not reach OpenWeather API: {e}")

    data = resp.json()
    main = data.get("main", {})
    weather_desc = data.get("weather", [{}])[0].get("description", "")
    wind_speed = data.get("wind", {}).get("speed", 0.0)
    
    # Rain in last 1 hour (mm) — scale to rough seasonal equivalent
    rain_1h = data.get("rain", {}).get("1h", 0.0)
    # 1h rain × 24h × ~90 days (Summer season) = rough seasonal estimate
    # But we cap this heavily since one hour is not representative
    seasonal_rain_estimate = min(rain_1h * 24 * 30, 500.0)  # max 500mm cap

    temp_avg = float(main.get("temp", 25))
    temp_min = float(main.get("temp_min", temp_avg - 3))
    temp_max = float(main.get("temp_max", temp_avg + 3))
    humidity  = float(main.get("humidity", 50))

    return {
        # ── Standard ML feature keys ──────────────────────────────────────
        "Temperature_Avg": round(temp_avg, 2),
        "Temperature_Min": round(temp_min, 2),
        "Temperature_Max": round(temp_max, 2),
        "Humidity":        round(humidity, 2),
        "Rainfall":        round(seasonal_rain_estimate, 2),
        "Temp_Range":      round(temp_max - temp_min, 2),
        # ── Metadata ──────────────────────────────────────────────────────
        "_live_description": weather_desc,
        "_live_wind_speed":  wind_speed,
        "_live_source":      "openweathermap",
        "_live_city":        data.get("name", city),
        "_live_feels_like":  float(main.get("feels_like", temp_avg)),
        "_live_pressure":    float(main.get("pressure", 1013)),
    }


# ── 5-Day Forecast (for alerts) ───────────────────────────────────────────────

def fetch_weather_for_location(city: str) -> dict[str, Any]:
    """
    Fetches a 5-day weather forecast from OpenWeatherMap (3-hour intervals).

    This is used by the alert engine, not the crop recommendation engine.
    It gives us a short-term outlook which is better for generating
    specific advice like "heavy rain expected Thursday — delay sowing."

    The 5-day raw rainfall is scaled up to a rough monthly estimate so it
    can be compared against the crop water requirement thresholds.
    """
    api_key = _get_api_key()
    url = f"{OPENWEATHER_BASE}/forecast"
    params = {"q": city, "appid": api_key, "units": "metric"}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise WeatherClientError(f"OpenWeather forecast failed: {e}")

    data = resp.json()
    items = data.get("list", [])

    temps, t_mins, t_maxs, humidities = [], [], [], []
    total_rain = 0.0

    for item in items:
        m = item.get("main", {})
        temps.append(m.get("temp", 0))
        t_mins.append(m.get("temp_min", 0))
        t_maxs.append(m.get("temp_max", 0))
        humidities.append(m.get("humidity", 0))
        total_rain += item.get("rain", {}).get("3h", 0)

    def _safe_mean(lst): return sum(lst) / len(lst) if lst else 0.0

    avg_temp = _safe_mean(temps)
    overall_min = min(t_mins) if t_mins else avg_temp
    overall_max = max(t_maxs) if t_maxs else avg_temp
    avg_humidity = _safe_mean(humidities)
    monthly_rain = total_rain * 6.0   # 5-day × 6 ≈ monthly estimate

    return {
        "Temperature_Avg": round(avg_temp, 2),
        "Temperature_Min": round(overall_min, 2),
        "Temperature_Max": round(overall_max, 2),
        "Humidity":        round(avg_humidity, 2),
        "Rainfall":        round(monthly_rain, 2),
        "Rainfall_Raw_5Day": round(total_rain, 2),
        "Temp_Range":      round(overall_max - overall_min, 2),
        "_live_source":    "openweathermap_forecast",
        "_live_city":      data.get("city", {}).get("name", city),
    }


# ── Blending Live + Historical ────────────────────────────────────────────────

def blend_with_historical(
    historical: dict[str, Any],
    city: str,
    blend_weight: float = LIVE_BLEND_WEIGHT,
) -> dict[str, Any]:
    """
    Fetches today's live weather and blends it with the historical seasonal average.

    This is the main function used by the crop recommendation engine.
    Instead of relying purely on 10-year averages (which can't reflect this
    year's unusual conditions), we mix in a small portion of today's actual
    readings to make the prediction more grounded in the present.

    How the blend works:
        final_value = (live_reading x weight) + (historical_average x (1 - weight))

    We only blend temperature and humidity — NOT rainfall.
    Rainfall is kept from historical because a single day's rain reading
    cannot represent a 90-180 day season's water availability. The model
    uses seasonal rainfall, not today's rainfall.

    If the API call fails for any reason (network issue, bad key, city not found),
    the function silently falls back to pure historical data. The system never crashes.
    """
    try:
        live = fetch_live_weather(city)
    except WeatherClientError as exc:
        # If live fetch fails, just log a warning and continue with historical only
        # The system works fine without live data — it just uses the seasonal average
        logger.warning("Could not fetch live weather for %s (%s) — falling back to historical data", city, exc)
        historical["_live_blended"] = False
        historical["_live_error"] = str(exc)
        return historical

    w = max(0.0, min(1.0, blend_weight))
    h = 1.0 - w

    def blend(live_val: float, hist_val: float) -> float:
        return round(live_val * w + hist_val * h, 2)

    blended = dict(historical)   # start from historical (preserves all keys)

    # Blend temperature and humidity (today's readings shift the historical average)
    blended["Temperature_Avg"] = blend(
        live["Temperature_Avg"], historical.get("Temperature_Avg", live["Temperature_Avg"])
    )
    blended["Temperature_Min"] = blend(
        live["Temperature_Min"], historical.get("Temperature_Min", live["Temperature_Min"])
    )
    blended["Temperature_Max"] = blend(
        live["Temperature_Max"], historical.get("Temperature_Max", live["Temperature_Max"])
    )
    blended["Humidity"] = blend(
        live["Humidity"], historical.get("Humidity", live["Humidity"])
    )
    blended["Temp_Range"] = round(
        blended["Temperature_Max"] - blended["Temperature_Min"], 2
    )

    # Rainfall is always taken from historical — never blended
    # One day of rain tells us nothing about the full growing season

    # ── Metadata ────────────────────────────────────────────────────────────
    blended["_live_blended"]    = True
    blended["_live_weight"]     = w
    blended["_live_description"]= live.get("_live_description", "")
    blended["_live_wind_speed"] = live.get("_live_wind_speed", 0)
    blended["_live_city"]       = live.get("_live_city", city)
    blended["_live_current"] = {
        "Temperature_Avg": live["Temperature_Avg"],
        "Temperature_Min": live["Temperature_Min"],
        "Temperature_Max": live["Temperature_Max"],
        "Humidity":        live["Humidity"],
        "description":     live.get("_live_description", ""),
        "feels_like":      live.get("_live_feels_like", live["Temperature_Avg"]),
    }

    logger.info(
        "Weather blended for %s: live_temp=%.1f°C hist_temp=%.1f°C → blended=%.1f°C (weight=%.0f%%)",
        city,
        live["Temperature_Avg"],
        historical.get("Temperature_Avg", 0),
        blended["Temperature_Avg"],
        w * 100,
    )

    return blended
