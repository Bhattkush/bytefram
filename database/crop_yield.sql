-- ============================================================
-- ByteFarm AI — Crop Yield Prediction System
-- Database: SQLite  |  File: database/crop_yield.db
-- ============================================================
-- HOW TO RUN:
--   sqlite3 database/crop_yield.db < database/crop_yield.sql
--   OR open in DB Browser for SQLite → Execute SQL tab
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;


-- ============================================================
-- 1. SCHEMA — CREATE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    phone_or_email TEXT NOT NULL,
    language       TEXT NOT NULL DEFAULT 'English',
    location       TEXT,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS farmer_profiles (
    farmer_id       TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    land_area       REAL NOT NULL CHECK(land_area > 0),
    soil_type       TEXT,
    preferred_crops TEXT,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions_history (
    prediction_id   INTEGER PRIMARY KEY,
    user_id         TEXT NOT NULL,
    model_type      TEXT NOT NULL,        -- 'yield' | 'recommend'
    crop            TEXT,                 -- NULL when model_type = 'recommend'
    district        TEXT NOT NULL,
    season          TEXT NOT NULL,        -- 'Kharif' | 'Rabi' | 'Summer'
    predicted_value REAL NOT NULL,        -- tonnes per hectare
    created_at      TEXT NOT NULL         -- ISO 8601 UTC timestamp
);

CREATE TABLE IF NOT EXISTS weather_cache (
    cache_id     INTEGER PRIMARY KEY,
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL,
    district     TEXT,
    temperature  REAL,                    -- degrees Celsius
    humidity     REAL,                    -- percentage
    rainfall     REAL,                    -- mm
    payload_json TEXT,                    -- full JSON response
    created_at   TEXT NOT NULL
);


-- ============================================================
-- 2. INDEXES — Speed up common queries
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_farmer_profiles_user_id
    ON farmer_profiles(user_id);

CREATE INDEX IF NOT EXISTS idx_predictions_user_id
    ON predictions_history(user_id);

CREATE INDEX IF NOT EXISTS idx_predictions_district_season
    ON predictions_history(district, season);

CREATE INDEX IF NOT EXISTS idx_weather_cache_coords
    ON weather_cache(latitude, longitude);


-- ============================================================
-- 3. SAMPLE INSERT DATA
-- ============================================================

INSERT OR IGNORE INTO users
    (user_id, name, phone_or_email, language, location, updated_at)
VALUES
    ('farmer_001', 'Ramesh Patel',   '9876543210', 'Gujarati', 'Ahmedabad',   datetime('now')),
    ('farmer_002', 'Suresh Sharma',  '9123456789', 'Hindi',    'Rajkot',      datetime('now')),
    ('farmer_003', 'Meena Desai',    '9988776655', 'Gujarati', 'Gandhinagar', datetime('now'));


INSERT OR IGNORE INTO farmer_profiles
    (farmer_id, user_id, land_area, soil_type, preferred_crops, updated_at)
VALUES
    ('farmer_001_farm', 'farmer_001', 2.5, 'Black Cotton',  'Groundnut, Cotton, Wheat',   datetime('now')),
    ('farmer_002_farm', 'farmer_002', 5.0, 'Sandy Loam',    'Bajra, Castor, Groundnut',   datetime('now')),
    ('farmer_003_farm', 'farmer_003', 1.2, 'Red Laterite',  'Vegetables, Wheat',          datetime('now'));


INSERT OR IGNORE INTO predictions_history
    (prediction_id, user_id, model_type, crop,       district,     season,  predicted_value, created_at)
VALUES
    (1000001, 'farmer_001', 'yield',     'Groundnut', 'Ahmedabad',   'Kharif', 18.45, datetime('now', '-3 days')),
    (1000002, 'farmer_001', 'yield',     'Cotton',    'Ahmedabad',   'Kharif',  9.20, datetime('now', '-2 days')),
    (1000003, 'farmer_001', 'yield',     'Wheat',     'Ahmedabad',   'Rabi',   22.10, datetime('now', '-1 day')),
    (1000004, 'farmer_002', 'yield',     'Bajra',     'Rajkot',      'Kharif', 14.80, datetime('now', '-2 days')),
    (1000005, 'farmer_002', 'yield',     'Castor',    'Rajkot',      'Kharif', 11.30, datetime('now', '-1 day')),
    (1000006, 'farmer_003', 'yield',     'Wheat',     'Gandhinagar', 'Rabi',   20.75, datetime('now')),
    (1000007, 'farmer_001', 'recommend', NULL,        'Ahmedabad',   'Kharif',  0.00, datetime('now'));


INSERT OR IGNORE INTO weather_cache
    (cache_id, latitude, longitude, district,     temperature, humidity, rainfall, payload_json, created_at)
VALUES
    (2000001, 23.0225, 72.5714, 'ahmedabad',   32.5, 68.0,  0.0, '{"source":"OpenWeather","season":"Kharif"}', datetime('now', '-1 day')),
    (2000002, 22.3039, 70.8022, 'rajkot',      34.1, 55.0,  0.0, '{"source":"OpenWeather","season":"Kharif"}', datetime('now', '-1 day')),
    (2000003, 23.2156, 72.6369, 'gandhinagar', 30.8, 72.0,  2.3, '{"source":"OpenWeather","season":"Kharif"}', datetime('now'));


-- ============================================================
-- 4. SELECT QUERIES — View & check saved data
-- ============================================================

-- Row count for all tables
SELECT 'users'               AS table_name, COUNT(*) AS total_rows FROM users
UNION ALL
SELECT 'farmer_profiles',                   COUNT(*)               FROM farmer_profiles
UNION ALL
SELECT 'predictions_history',               COUNT(*)               FROM predictions_history
UNION ALL
SELECT 'weather_cache',                     COUNT(*)               FROM weather_cache;


-- All registered users
SELECT
    user_id,
    name,
    phone_or_email,
    language,
    location,
    updated_at
FROM users
ORDER BY updated_at DESC;


-- Farmer profiles with user name (JOIN)
SELECT
    u.name                        AS farmer_name,
    u.location,
    f.land_area || ' ha'          AS land_area,
    f.soil_type,
    f.preferred_crops,
    f.updated_at
FROM farmer_profiles f
JOIN users u ON u.user_id = f.user_id
ORDER BY f.updated_at DESC;


-- Full prediction history for a user
SELECT
    prediction_id,
    model_type,
    COALESCE(crop, '(multi-crop)') AS crop,
    district,
    season,
    ROUND(predicted_value, 2)      AS yield_t_ha,
    created_at
FROM predictions_history
WHERE user_id = 'farmer_001'
ORDER BY prediction_id DESC;


-- Average yield per crop across all users
SELECT
    crop,
    season,
    COUNT(*)                        AS predictions,
    ROUND(AVG(predicted_value), 2)  AS avg_yield_t_ha,
    ROUND(MAX(predicted_value), 2)  AS best_yield,
    ROUND(MIN(predicted_value), 2)  AS worst_yield
FROM predictions_history
WHERE crop IS NOT NULL
GROUP BY crop, season
ORDER BY avg_yield_t_ha DESC;


-- Top districts by usage
SELECT
    district,
    COUNT(*) AS total_predictions,
    ROUND(AVG(predicted_value), 2) AS avg_yield_t_ha
FROM predictions_history
WHERE crop IS NOT NULL
GROUP BY district
ORDER BY total_predictions DESC;


-- Prediction summary by season
SELECT
    season,
    COUNT(*)                        AS total_predictions,
    ROUND(AVG(predicted_value), 2)  AS avg_yield,
    ROUND(MAX(predicted_value), 2)  AS max_yield,
    ROUND(MIN(predicted_value), 2)  AS min_yield
FROM predictions_history
WHERE crop IS NOT NULL
GROUP BY season;


-- Recent weather cache (last 10 entries)
SELECT
    ROUND(latitude, 4)   AS lat,
    ROUND(longitude, 4)  AS lon,
    district,
    temperature || '°C'  AS temp,
    humidity    || '%'   AS humidity,
    rainfall    || ' mm' AS rainfall,
    created_at
FROM weather_cache
ORDER BY created_at DESC
LIMIT 10;


-- ============================================================
-- 5. UPDATE QUERIES
-- ============================================================

-- Update user language
-- UPDATE users SET language = 'Hindi', updated_at = datetime('now')
-- WHERE user_id = 'farmer_001';

-- Update farmer land area
-- UPDATE farmer_profiles SET land_area = 3.5, updated_at = datetime('now')
-- WHERE farmer_id = 'farmer_001_farm';


-- ============================================================
-- 6. DELETE / MAINTENANCE QUERIES
-- ============================================================

-- Delete weather cache older than 7 days
-- DELETE FROM weather_cache WHERE created_at < datetime('now', '-7 days');

-- Delete prediction history older than 90 days
-- DELETE FROM predictions_history WHERE created_at < datetime('now', '-90 days');

-- Delete a specific user (cascades to farmer_profiles)
-- DELETE FROM users WHERE user_id = 'farmer_001';

-- Hard reset — delete ALL data (use with caution)
-- DELETE FROM weather_cache;
-- DELETE FROM predictions_history;
-- DELETE FROM farmer_profiles;
-- DELETE FROM users;
