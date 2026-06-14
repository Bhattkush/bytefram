# Smart Farming AI System

Full-stack baseline for AI-driven agricultural recommendations:

- ML engine (`ML/`) for training and inference
- FastAPI backend (`backend/`) as model bridge
- Flutter starter app (`frontend/`) for farmer-facing UI
- Firebase Firestore storage (`database/` docs)

## Project Structure

```text
Smart-Farming-App/
├── ML/
│   ├── data/
│   ├── models/
│   └── src/
├── backend/
├── frontend/
├── database/
└── docs/
```

## Features Implemented

1. Yield prediction (`/predict-yield`)
2. Crop recommendation (`/crop-recommend`)
3. Disease risk prediction (`/disease-risk`)
4. Weather alerts (`/weather-alert`)
5. Farmer profile management (`/profile`)
6. Prediction history (`/predictions/history/{user_id}`)

## Quick Start

### 1) Python setup

```powershell
cd D:\ML-Project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Environment

Copy `.env.example` to `.env` and set values.


### 3) Firebase setup (Firestore)

1. Create/select your Firebase project.
2. Enable Firestore Database.
3. Create a service account key JSON from Firebase Console.
4. Set `FIREBASE_PROJECT_ID` and either:
   - `FIREBASE_CREDENTIALS_PATH`, or
   - `FIREBASE_CREDENTIALS_JSON`



### 5) Run backend API

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Yield prediction

```bash
curl -X POST "http://localhost:8000/predict-yield" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "u001",
    "district": "Ahmedabad",
    "season": "Kharif",
    "year": 2020,
    "crop": "Bajra",
    "temperature_avg": 28.2,
    "temperature_min": 22.1,
    "temperature_max": 35.0,
    "rainfall": 1020,
    "humidity": 74,
    "n": 85,
    "p": 42,
    "k": 38,
    "ph": 6.5,
    "organic_carbon": 0.78
  }'
```

### Crop recommendation


```

## Data Download References


- Kaggle crop recommendation: [https://www.kaggle.com/datasets/uthmordewanta/crop-recommendation-dataset](https://www.kaggle.com/datasets/uthmordewanta/crop-recommendation-dataset)
- NASA HLS NDVI: [https://data.nasa.gov/dataset/hls-sentinel-2-multi-spectral-instrument-vegetation-indices-daily-global-30-m-v2-0-90ed0](https://data.nasa.gov/dataset/hls-sentinel-2-multi-spectral-instrument-vegetation-indices-daily-global-30-m-v2-0-90ed0)
- ISRO VEDAS: [https://vedas.sac.gov.in/vegetation-monitoring/](https://vedas.sac.gov.in/vegetation-monitoring/)

More details: `docs/DATA_PREPARATION.md`.
