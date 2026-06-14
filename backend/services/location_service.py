"""
Location Service — Resolve lat/lon to Gujarat district
========================================================
Uses Haversine distance against 33 Gujarat district centroids.
No external API needed — pure math.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from ML.src.constants import DISTRICT_COORDINATES, CITY_TO_DISTRICT

logger = logging.getLogger(__name__)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute distance between two GPS coordinates in kilometres."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def resolve_district_from_coords(lat: float, lon: float) -> dict[str, Any]:
    """Find the nearest Gujarat district for given GPS coordinates.

    Returns:
        {
            "district": "surat",
            "distance_km": 12.3,
            "is_outside_gujarat": False,
            "coordinates": {"lat": 21.17, "lon": 72.83},
            "warning": None
        }
    """
    nearest_district = "ahmedabad"
    min_distance = float("inf")
    nearest_coords = (23.02, 72.57)

    for district, (d_lat, d_lon) in DISTRICT_COORDINATES.items():
        dist = haversine_km(lat, lon, d_lat, d_lon)
        if dist < min_distance:
            min_distance = dist
            nearest_district = district
            nearest_coords = (d_lat, d_lon)

    warning = None
    is_outside = False

    if min_distance > 200:
        is_outside = True
        warning = (
            f"Location ({lat:.4f}, {lon:.4f}) is {min_distance:.0f} km from "
            f"Gujarat. Using nearest district '{nearest_district}' but results "
            f"may not be accurate. This tool is optimised for Gujarat, India."
        )
        logger.warning(warning)
    elif min_distance > 50:
        warning = (
            f"Location is {min_distance:.0f} km from nearest district centre "
            f"'{nearest_district}'. Results are approximate."
        )

    return {
        "district": nearest_district,
        "distance_km": round(min_distance, 2),
        "is_outside_gujarat": is_outside,
        "coordinates": {"lat": nearest_coords[0], "lon": nearest_coords[1]},
        "warning": warning,
    }


def resolve_district_from_name(name: str) -> dict[str, Any]:
    """Resolve a city or district name to a Gujarat district.

    Looks up CITY_TO_DISTRICT first, then DISTRICT_COORDINATES directly.
    """
    key = name.strip().lower()

    # Check city-to-district mapping
    mapped = CITY_TO_DISTRICT.get(key)
    if mapped and mapped in DISTRICT_COORDINATES:
        lat, lon = DISTRICT_COORDINATES[mapped]
        return {
            "district": mapped,
            "distance_km": 0.0,
            "is_outside_gujarat": False,
            "coordinates": {"lat": lat, "lon": lon},
            "warning": None,
        }

    # Check direct district name
    if key in DISTRICT_COORDINATES:
        lat, lon = DISTRICT_COORDINATES[key]
        return {
            "district": key,
            "distance_km": 0.0,
            "is_outside_gujarat": False,
            "coordinates": {"lat": lat, "lon": lon},
            "warning": None,
        }

    # Fallback
    lat, lon = DISTRICT_COORDINATES["ahmedabad"]
    return {
        "district": "ahmedabad",
        "distance_km": 0.0,
        "is_outside_gujarat": False,
        "coordinates": {"lat": lat, "lon": lon},
        "warning": f"'{name}' not found. Using Ahmedabad as fallback.",
    }
