"""
ML/src/soil_loader.py
======================
Computes per-district soil averages directly from the ML training dataset.

Why this approach is better than a separate soil CSV:
  The training CSV already contains N, P, K, pH, Organic_Carbon for all
  33 Gujarat districts. Averaging those values per district gives us soil
  data that is 100% consistent with what the model was trained on — meaning
  no gaps, no manual estimates, no silent mismatches between training and inference.

At runtime, when a farmer's district is looked up:
  1. The pre-computed district average is returned instantly
  2. If district not found — Gujarat state average is used as fallback
  3. If training CSV is missing — hardcoded Gujarat averages are used

Soil_Score (composite fertility 0–100):
  Weighted blend of normalised N, P, K, Organic_Carbon, capturing
  overall soil richness in a single comparable number.

Usage:
    loader = SoilDataLoader()
    soil = loader.get_soil("kutch")
    # Returns: {"N": 38.1, "P": 88.0, "K": 106.6, "pH": 6.29,
    #           "Organic_Carbon": 0.48, "Soil_Score": 32.5}
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Path to the main training CSV (same one used for model training)
_TRAINING_CSV = (
    Path(__file__).resolve().parents[1]
    / "data" / "external"
    / "final_ml_training_dataset_required_columns.csv"
)

# Soil columns that exist in the training data
_SOIL_COLUMNS = ["N", "P", "K", "pH", "Organic_Carbon"]

# Hardcoded Gujarat fallback — only used if the training CSV is missing entirely
_HARDCODED_FALLBACK = {
    "N": 40.0, "P": 85.0, "K": 100.0,
    "pH": 6.30, "Organic_Carbon": 0.60,
    "Soil_Score": 48.0,
}


def _normalize_district(name: str) -> str:
    """
    Cleans up a district name so lookups don't fail on small differences.
    Handles: "Ahmedabad District", "  RAJKOT ", "Chhota-Udaipur" → normalised lowercase.
    """
    return (
        str(name)
        .lower()
        .strip()
        .replace(" district", "")
        .replace("-", " ")
        .replace("_", " ")
    )


def _compute_soil_score(row: dict[str, Any]) -> float:
    """
    Computes a composite soil fertility score from 0 to 100.

    Weights:
      N  (nitrogen)        → 30%   primary plant nutrient
      P  (phosphorus)      → 20%   root growth and flowering
      K  (potassium)       → 20%   disease resistance
      OC (organic carbon)  → 30%   soil health and water retention

    Normalised against the actual min/max values seen across all 33 districts
    in the training data, so the score is directly comparable.
    """
    # These ranges are derived from the real training data output above
    ranges = {
        "N":              (30.0, 46.0),
        "P":              (79.0, 109.0),
        "K":              (88.0, 140.0),
        "Organic_Carbon": (0.48, 0.80),
    }
    weights = {"N": 0.30, "P": 0.20, "K": 0.20, "Organic_Carbon": 0.30}

    score = 0.0
    for key, weight in weights.items():
        lo, hi = ranges[key]
        raw = float(row.get(key, lo))
        normalised = max(0.0, min(1.0, (raw - lo) / (hi - lo)))
        score += normalised * weight

    return round(score * 100, 1)


class SoilDataLoader:
    """
    Reads district-level soil averages from the training CSV at startup.
    All lookups after that are instant in-memory dict fetches.
    """

    def __init__(self, training_csv: str | Path | None = None):
        csv_path = Path(training_csv) if training_csv else _TRAINING_CSV

        if not csv_path.exists():
            logger.warning(
                "Training CSV not found at %s — using hardcoded Gujarat averages for soil",
                csv_path,
            )
            self._data: dict[str, dict[str, Any]] = {}
            self._avg = dict(_HARDCODED_FALLBACK)
            return

        df = pd.read_csv(csv_path)

        # Check that all expected soil columns are present
        missing = [c for c in _SOIL_COLUMNS if c not in df.columns]
        if missing or "District" not in df.columns:
            logger.error("Training CSV missing soil columns: %s", missing)
            self._data = {}
            self._avg = dict(_HARDCODED_FALLBACK)
            return

        # Compute per-district mean AND std — same values the model was trained on
        # std tells us how consistent soil is across farms within a district
        soil_agg = (
            df.groupby("District")[_SOIL_COLUMNS]
            .agg(["mean", "std"])
            .round(2)
            .reset_index()
        )
        # Flatten multi-level columns: ("N", "mean") → "N_mean", etc.
        soil_agg.columns = [
            "District" if col[0] == "District" else f"{col[0]}_{col[1]}"
            for col in soil_agg.columns
        ]

        # Build a fast normalised-key → soil dict
        self._data = {}
        for _, row in soil_agg.iterrows():
            district_key = _normalize_district(row["District"])
            entry: dict[str, Any] = {col: float(row[f"{col}_mean"]) for col in _SOIL_COLUMNS}
            entry["Soil_Score"] = _compute_soil_score(entry)

            # Soil variability: flag districts where nitrogen varies a lot between farms
            # High N std (> 15) means some farms are rich, others are poor
            n_std = float(row.get("N_std", 0))
            if n_std > 15:
                entry["Soil_Variability"] = "High"    # farms within district differ a lot
            elif n_std > 8:
                entry["Soil_Variability"] = "Moderate"
            else:
                entry["Soil_Variability"] = "Stable"  # consistent soil across the district

            self._data[district_key] = entry

        # Pre-compute state average for fallback
        mean_cols = [f"{col}_mean" for col in _SOIL_COLUMNS]
        state_row = {col: float(soil_agg[f"{col}_mean"].mean()) for col in _SOIL_COLUMNS}
        state_row["Soil_Score"] = _compute_soil_score(state_row)
        state_row["Soil_Variability"] = "Unknown"
        self._avg = state_row

        print(
            f"Soil averages computed: {len(self._data)} districts from training data | "
            f"Soil_Score range: "
            f"{min(v['Soil_Score'] for v in self._data.values()):.0f}"
            f"–{max(v['Soil_Score'] for v in self._data.values()):.0f}/100"
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def get_soil(self, district: str) -> dict[str, Any]:
        """
        Returns soil values for a district.

        Lookup order:
          1. Exact normalised match  ("kutch" → "kutch")
          2. Partial match           ("chhota" → "chhota udaipur")
          3. Gujarat state average   (always succeeds — derived from training data)
        """
        if not self._data:
            return dict(self._avg)

        key = _normalize_district(district)

        # 1. Exact match
        if key in self._data:
            return dict(self._data[key])

        # 2. Partial match — handles "devbhoomi dwarka", spelling variants, etc.
        for stored in self._data:
            if stored in key or key in stored:
                logger.debug("Soil partial match: '%s' → '%s'", key, stored)
                return dict(self._data[stored])

        # 3. State-wide average fallback
        logger.warning("No soil entry for district '%s' — using state average", district)
        return dict(self._avg)

    def get_soil_score(self, district: str) -> float:
        """Returns just the composite fertility score (0–100) for a district."""
        return self.get_soil(district).get("Soil_Score", 50.0)

    def all_districts(self) -> list[str]:
        """Returns all districts with computed soil data."""
        return sorted(self._data.keys())

    def __len__(self) -> int:
        return len(self._data)
