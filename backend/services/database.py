from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from backend.config import settings


def _get_conn() -> sqlite3.Connection:
    db_path = settings.resolved_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                phone_or_email TEXT NOT NULL,
                language    TEXT DEFAULT 'English',
                location    TEXT,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS farmer_profiles (
                farmer_id       TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL REFERENCES users(user_id),
                land_area       REAL NOT NULL,
                soil_type       TEXT,
                preferred_crops TEXT,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS predictions_history (
                prediction_id INTEGER PRIMARY KEY,
                user_id       TEXT NOT NULL,
                model_type    TEXT NOT NULL,
                crop          TEXT,
                district      TEXT NOT NULL,
                season        TEXT NOT NULL,
                predicted_value REAL NOT NULL,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weather_cache (
                cache_id     INTEGER PRIMARY KEY,
                latitude     REAL NOT NULL,
                longitude    REAL NOT NULL,
                district     TEXT,
                temperature  REAL,
                humidity     REAL,
                rainfall     REAL,
                payload_json TEXT,
                created_at   TEXT NOT NULL
            );
        """)


def upsert_user(
    *,
    user_id: str,
    name: str,
    phone_or_email: str,
    language: str,
    location: str | None,
) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, name, phone_or_email, language, location, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name,
                phone_or_email=excluded.phone_or_email,
                language=excluded.language,
                location=excluded.location,
                updated_at=excluded.updated_at
            """,
            (user_id, name, phone_or_email, language, location, updated_at),
        )


def upsert_farmer_profile(
    *,
    farmer_id: str,
    user_id: str,
    land_area: float,
    soil_type: str | None,
    preferred_crops: str | None,
) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO farmer_profiles
                (farmer_id, user_id, land_area, soil_type, preferred_crops, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(farmer_id) DO UPDATE SET
                user_id=excluded.user_id,
                land_area=excluded.land_area,
                soil_type=excluded.soil_type,
                preferred_crops=excluded.preferred_crops,
                updated_at=excluded.updated_at
            """,
            (farmer_id, user_id, float(land_area), soil_type, preferred_crops, updated_at),
        )


def get_profile(user_id: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
        user_row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not user_row:
            return None

        farmer_row = conn.execute(
            "SELECT * FROM farmer_profiles WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        if not farmer_row:
            return None

        return {"user": dict(user_row), "farmer": dict(farmer_row)}


def _next_id() -> int:
    return int(time.time() * 1_000_000)


def add_prediction_history(
    *,
    user_id: str,
    model_type: str,
    crop: str | None,
    district: str,
    season: str,
    predicted_value: float,
) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO predictions_history
                (prediction_id, user_id, model_type, crop, district, season, predicted_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_next_id(), user_id, model_type, crop, district, season, float(predicted_value), created_at),
        )


def get_prediction_history(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM predictions_history
            WHERE user_id = ?
            ORDER BY prediction_id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def save_weather_cache(
    *,
    latitude: float,
    longitude: float,
    district: str | None,
    temperature: float | None,
    humidity: float | None,
    rainfall: float | None,
    payload_json: str,
) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO weather_cache
                (cache_id, latitude, longitude, district, temperature, humidity, rainfall, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_next_id(), float(latitude), float(longitude), district,
             temperature, humidity, rainfall, payload_json, created_at),
        )
