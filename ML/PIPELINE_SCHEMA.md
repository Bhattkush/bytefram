# ByteFarm ML Pipeline — Schema Contract

> **Version:** 2.0.0  
> **Last Updated:** 2026-04-01  
> Single source of truth for all ML input/output formats.

---

## 1. Model Artifacts

| File | Description |
|---|---|
| `models/yield_model.pkl` | XGBoost regressor (joblib serialized) |
| `models/crop_encoder.pkl` | LabelEncoder for crop names → integers |
| `models/features.pkl` | Ordered list of feature names |
| `models/model_metadata.json` | Version, metrics, defaults, feature sets |

---

## 2. Input Schema — Yield Prediction

### Required Features (15 total)

| Feature | Type | Range | Description |
|---|---|---|---|
| `Temperature_Avg` | float | -20 to 60 °C | Average temperature |
| `Temperature_Min` | float | -20 to 60 °C | Minimum temperature |
| `Temperature_Max` | float | -20 to 60 °C | Maximum temperature |
| `Rainfall` | float | 0 to 10000 mm | Seasonal rainfall |
| `Humidity` | float | 0 to 100 % | Relative humidity |
| `N` | float | 0 to 500 | Nitrogen (kg/ha) |
| `P` | float | 0 to 500 | Phosphorus (kg/ha) |
| `K` | float | 0 to 500 | Potassium (kg/ha) |
| `pH` | float | 0 to 14 | Soil pH |
| `Organic_Carbon` | float | 0 to 5 % | Soil organic carbon |
| `NDVI_Peak` | float | 0 to 1 | Peak vegetation index |
| `Temp_Range` | float | derived | `Temperature_Max - Temperature_Min` |
| `GDD` | float | derived | `max(Temperature_Avg - 10, 0) × 120` |
| `Humidity_Rain_Interaction` | float | derived | `Humidity × Rainfall / 100` |
| `Crop` | int | encoded | LabelEncoder encoded crop index |

### Notes on Missing Values

- **All features have defaults** from `model_metadata.json`
- **Derived features** (`Temp_Range`, `GDD`, `Humidity_Rain_Interaction`) are auto-computed from raw weather if not provided
- **Crop name strings** (e.g. `"Groundnut"`) are auto-encoded via `crop_encoder.pkl`
- **Unknown crops** encode to `0` (no crash)
- **Any remaining `None`/`NaN`** is replaced with `0.0` as a safety net

---

## 3. Output Schema — `predict_yield_safe()`

### Success Response

```json
{
  "status": "ok",
  "yield": 2.5366,
  "warnings": [],
  "model_version": "2.0.0"
}
```

### Error Response

```json
{
  "status": "error",
  "code": "prediction_error",
  "message": "Unable to predict. Please try again. (ValueError)"
}
```

### Error Codes

| Code | Meaning |
|---|---|
| `model_not_ready` | Model file not found or failed to load |
| `invalid_input` | Payload is not a dictionary |
| `empty_input` | Payload is an empty dictionary |
| `prediction_error` | Model prediction failed (unexpected) |

---

## 4. Output Schema — `recommend_safe()`

### Success Response (abbreviated)

```json
{
  "status": "ok",
  "location": "Surat",
  "district": "surat",
  "season": "Kharif",
  "land_area_hectares": 1.0,
  "irrigated": false,
  "mode": "🛡 Safe Mode",
  "confidence": 78,
  "insight": "Surat has good rainfall. Most crops viable.",
  "advice": "Good growing conditions — diversify crops for risk management.",
  "weather_summary": {
    "Temperature_Avg": 28.5,
    "Temperature_Min": 22.1,
    "Temperature_Max": 35.8,
    "Humidity": 75.2,
    "Seasonal_Rainfall_mm": 1200.5
  },
  "top_recommended_crops": [
    {
      "crop_name": "Groundnut",
      "category": "Oilseed",
      "yield_per_hectare": 2.34,
      "total_yield_tonnes": 2.34,
      "display_yield": "2.34 tonnes",
      "production_level": "Medium",
      "suitability_score": 0.85,
      "risk_confidence": "Low Risk",
      "reason": "...",
      "market_price_per_tonne": 55000,
      "estimated_profit_inr": 128700,
      "display_profit": "₹1.29 L",
      "composite_score": 0.82
    }
  ],
  "avoid_crops": [...],
  "crops_evaluated": 18,
  "crops_filtered_out": 3
}
```

### Error Response

```json
{
  "status": "error",
  "message": "Unable to generate recommendations. Please try again. (ConnectionError)"
}
```

---

## 5. API Endpoints

| Method | Path | Input | Output | Description |
|---|---|---|---|---|
| `POST` | `/recommend` | `SmartRecommendRequest` | `SmartRecommendResponse` | **Main endpoint** — GPS → full recommendations |
| `POST` | `/predict-yield` | `YieldPredictionRequest` | `YieldPredictionResponse` | Single crop yield prediction |
| `POST` | `/crop-recommend` | `CropRecommendationRequest` | `CropRecommendationResponse` | Multi-crop ranking |
| `POST` | `/disease-risk` | `DiseaseRiskRequest` | `DiseaseRiskResponse` | Rule-based disease risk |
| `POST` | `/weather-alert` | `WeatherAlertRequest` | `WeatherAlertResponse` | Real-time weather alerts |
| `GET` | `/health` | — | `{"status": "ok"}` | Server health check |
| `GET` | `/health/model` | — | `ModelHealthResponse` | ML model health + version |

---

## 6. Error Handling Contract

**The system NEVER crashes.** Every public function follows this pattern:

```
┌─────────────────────────────────────────────┐
│  predict_yield()        → may raise         │
│  predict_yield_safe()   → NEVER raises      │  ← Use this
│  recommend()            → may raise         │
│  recommend_safe()       → NEVER raises      │  ← Use this
│  API endpoints          → JSONResponse      │  ← Always returns JSON
│  Global exception       → 500 JSON          │  ← Last resort
└─────────────────────────────────────────────┘
```

### Failure Cascade

1. **Input validation** catches bad types, missing fields, out-of-range values → returns warnings
2. **Feature construction** fills missing values from defaults → logs warnings
3. **NaN safety pass** replaces any remaining None/NaN with 0.0 → logs warnings
4. **Prediction try/except** catches model errors → returns `{"status": "error"}`
5. **Route try/except** catches service errors → returns HTTP 500 JSON
6. **Global exception handler** catches everything else → returns HTTP 500 JSON

---

## 7. Supported Crops (30)

```
Arhar/Tur, Bajra, Banana, Castor seed, Cotton(lint), Dry chillies,
Garlic, Gram, Groundnut, Guar seed, Jowar, Maize, Moong(Green Gram),
Moth, Onion, Other Cereals, Other Kharif pulses, Other Rabi pulses,
Potato, Ragi, Rapeseed &Mustard, Rice, Sesamum, Small millets,
Soyabean, Sugarcane, Tobacco, Urad, Wheat, other oilseeds
```

---

## 8. Training Script

```bash
# From project root:
python -m ML.src.train_models --base-csv ML/data/external/final_ml_training_dataset_required_columns.csv

# Error handling:
#   ❌ File not found       → prints path and exits
#   ❌ Missing columns      → prints which columns and exits
#   ⚠️  High NaN ratio      → warns but continues
#   ❌ Training crash       → prints error type and exits
#   ❌ Save failure         → prints error and exits
#   ✅ Success              → prints metrics + artifacts path
```
