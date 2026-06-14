from __future__ import annotations

import json
from typing import Any

import requests

from backend.config import settings
from backend.services.database import save_weather_cache


class WeatherServiceError(RuntimeError):
    pass


def _build_alerts(current_temp: float, forecast_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []

    temps = [current_temp]
    rain_values = []
    for item in forecast_items[:8]:
        main = item.get("main", {})
        temps.append(float(main.get("temp", current_temp)))
        rain = item.get("rain", {})
        rain_values.append(float(rain.get("3h", 0.0)))

    max_temp = max(temps) if temps else current_temp
    min_temp = min(temps) if temps else current_temp
    max_rain = max(rain_values) if rain_values else 0.0

    if max_rain >= 10:
        alerts.append(
            {
                "type": "rain_warning",
                "severity": "high",
                "message": "Heavy rain expected in next 24 hours. Protect fertilizer and seedlings.",
            }
        )
    elif max_rain >= 4:
        alerts.append(
            {
                "type": "rain_watch",
                "severity": "medium",
                "message": "Moderate rain expected. Plan irrigation accordingly.",
            }
        )

    if max_temp >= 40:
        alerts.append(
            {
                "type": "heatwave",
                "severity": "high",
                "message": "Heatwave conditions likely. Increase irrigation and avoid afternoon spray.",
            }
        )
    elif max_temp >= 35:
        alerts.append(
            {
                "type": "heat_stress",
                "severity": "medium",
                "message": "High daytime temperature expected. Monitor moisture stress.",
            }
        )

    if min_temp <= 8:
        alerts.append(
            {
                "type": "cold_stress",
                "severity": "high",
                "message": "Cold stress risk detected. Consider crop cover or anti-frost measures.",
            }
        )

    return alerts


def fetch_weather_and_alerts(latitude: float, longitude: float, district: str | None = None) -> dict[str, Any]:
    if not settings.weather_api_key:
        raise WeatherServiceError("OPENWEATHER_API_KEY is missing. Set it in your environment.")

    weather_url = f"{settings.weather_base_url}/weather"
    forecast_url = f"{settings.weather_base_url}/forecast"
    common_params = {
        "lat": latitude,
        "lon": longitude,
        "appid": settings.weather_api_key,
        "units": "metric",
    }

    weather_resp = requests.get(weather_url, params=common_params, timeout=20)
    forecast_resp = requests.get(forecast_url, params=common_params, timeout=20)
    if weather_resp.status_code >= 400:
        raise WeatherServiceError(
            f"Weather API error ({weather_resp.status_code}): {weather_resp.text[:300]}"
        )
    if forecast_resp.status_code >= 400:
        raise WeatherServiceError(
            f"Forecast API error ({forecast_resp.status_code}): {forecast_resp.text[:300]}"
        )

    weather_data = weather_resp.json()
    forecast_data = forecast_resp.json()
    current = {
        "temperature": float(weather_data.get("main", {}).get("temp", 0.0)),
        "humidity": float(weather_data.get("main", {}).get("humidity", 0.0)),
        "rainfall_1h": float(weather_data.get("rain", {}).get("1h", 0.0)),
        "description": weather_data.get("weather", [{}])[0].get("description", "unknown"),
    }
    alerts = _build_alerts(current["temperature"], forecast_data.get("list", []))

    payload = {
        "latitude": latitude,
        "longitude": longitude,
        "current": current,
        "alerts": alerts,
    }
    save_weather_cache(
        latitude=latitude,
        longitude=longitude,
        district=district,
        temperature=current["temperature"],
        humidity=current["humidity"],
        rainfall=current["rainfall_1h"],
        payload_json=json.dumps(payload),
    )
    return payload

