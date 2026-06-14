from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .constants import (
    BASE_REQUIRED_COLUMNS,
    DATA_DIR,
    DEFAULT_SOIL_VALUES,
    ENGINEERED_COLUMNS,
    SEASON_DAYS,
    SOIL_FEATURE_COLUMNS,
)


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    as_text = str(value).strip().lower()
    return re.sub(r"[^a-z0-9]+", "", as_text)


def _canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    column_aliases = {
        "district": "District",
        "district_name": "District",
        "state": "State",
        "state_name": "State",
        "crop": "Crop",
        "crop_name": "Crop",
        "label": "Crop",
        "year": "Year",
        "n": "N",
        "nitrogen": "N",
        "p": "P",
        "phosphorus": "P",
        "k": "K",
        "potassium": "K",
        "ph": "pH",
        "p_h": "pH",
        "organiccarbon": "Organic_Carbon",
        "organic_carbon": "Organic_Carbon",
        "organic carbon": "Organic_Carbon",
        "ndvi": "NDVI_Peak",
        "ndvi_peak": "NDVI_Peak",
    }

    renamed: dict[str, str] = {}
    for column in df.columns:
        key = column.strip().lower()
        renamed[column] = column_aliases.get(key, column)
    return df.rename(columns=renamed)


def _validate_base_columns(df: pd.DataFrame) -> None:
    missing = [col for col in BASE_REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"Base training dataset is missing columns: {missing_str}")


def load_base_training_frame(base_csv_path: Path | str) -> pd.DataFrame:
    """
    Loads the raw training CSV and standardises all column names.

    Column names differ across datasets (e.g. 'crop' vs 'Crop' vs 'label'),
    so we normalise everything up front to avoid confusing the model later.
    Also checks that all required columns are present before proceeding.
    """
    base_df = pd.read_csv(base_csv_path)
    base_df = _canonicalize_columns(base_df)
    _validate_base_columns(base_df)
    return base_df


# District-level soil defaults (from your original data catalog)
# Use these ONLY when you have no real soil CSV — they are constant per district
# which limits the yield model, but at least the columns won't be missing/NaN
DISTRICT_SOIL_DEFAULTS = {
    # Format: "District": {"N": ..., "P": ..., "K": ..., "pH": ..., "Organic_Carbon": ...}
    # If you have real per-district values, put them here
    "Ahmedabad":   {"N": 70, "P": 40, "K": 45, "pH": 6.7, "Organic_Carbon": 0.75},
    "Gandhinagar": {"N": 68, "P": 38, "K": 43, "pH": 6.9, "Organic_Carbon": 0.72},
    # Fallback default used for any district not listed:
    "__default__": {"N": 65, "P": 35, "K": 40, "pH": 6.8, "Organic_Carbon": 0.70},
}

def attach_soil_columns(df: pd.DataFrame, soil_csv: Path | None = None) -> pd.DataFrame:
    """
    Adds soil data columns (N, P, K, pH, Organic_Carbon) to the training frame.

    Two options, in order of preference:
      1. A real soil CSV with per-district measurements  ← use this if you have it
      2. District-level average defaults hardcoded below  ← used when no CSV is given

    Soil data helps the model understand that the same crop behaves differently
    in nutrient-rich vs nutrient-poor land, even with identical weather.
    """
    df = df.copy()

    if soil_csv is not None and soil_csv.exists():
        soil = pd.read_csv(soil_csv)
        # Make sure district names match between the two files before joining
        if "District" in soil.columns and "District" in df.columns:
            soil["District"] = soil["District"].astype(str).str.strip().str.title()
            df["District"]   = df["District"].astype(str).str.strip().str.title()
            # Join on District + Year if the soil file has yearly readings,
            # otherwise just join on District
            join_keys = ["District", "Year"] if "Year" in soil.columns else ["District"]
            df = df.merge(soil, on=join_keys, how="left")
            matched = df['N'].notna().sum()
            print(f"Soil data joined: {matched} out of {len(df)} rows matched from {soil_csv.name}")
    else:
        print("No soil file provided — using average soil values per district as a fallback")
        defaults_df = pd.DataFrame.from_dict(DISTRICT_SOIL_DEFAULTS, orient="index")
        defaults_df.index.name = "District"
        defaults_df = defaults_df.reset_index()
        if "District" in df.columns:
            df["District"] = df["District"].astype(str).str.strip().str.title()
            df = df.merge(defaults_df, on="District", how="left")

        # Any district not in our defaults table gets the state-wide average
        fallback = DISTRICT_SOIL_DEFAULTS["__default__"]
        for col, val in fallback.items():
            if col not in df.columns:
                df[col] = val
            df[col] = df[col].fillna(val)

    return df


def attach_ndvi_column(df: pd.DataFrame, ndvi_csv: Path | None = None) -> pd.DataFrame:
    """
    Adds the NDVI_Peak column (Normalised Difference Vegetation Index).

    NDVI measures how green/healthy crops look from satellite imagery.
    Values range from 0.0 (bare soil) to 1.0 (dense, healthy vegetation).

    If no satellite data file is provided, we use 0.5 as a neutral placeholder.
    This means the model gets no vegetation signal — it still works, but
    adding real NDVI data would meaningfully improve prediction accuracy.
    """
    df = df.copy()

    if ndvi_csv is not None and ndvi_csv.exists():
        ndvi_df = pd.read_csv(ndvi_csv)
        # Join on whichever common keys exist (District, Year, Season, Crop)
        join_keys = [k for k in ["District", "Year", "Season", "Crop"] if k in ndvi_df.columns and k in df.columns]
        if join_keys:
            df = df.merge(ndvi_df[join_keys + ["NDVI_Peak"]], on=join_keys, how="left")
            matched = df["NDVI_Peak"].notna().sum()
            print(f"NDVI data joined: {matched} out of {len(df)} rows matched")
        df["NDVI_Peak"] = df.get("NDVI_Peak", pd.Series(0.5, index=df.index)).fillna(0.5)
    elif "District" in df.columns and "Season" in df.columns:
        # Use district + season NDVI estimates instead of a flat 0.5 placeholder.
        # Each district gets a realistic vegetation index based on land use and ecology.
        # This gives the model a real signal to learn from (arid vs alluvial vs coastal).
        from .ndvi_loader import get_ndvi
        df["NDVI_Peak"] = df.apply(
            lambda row: get_ndvi(str(row["District"]), str(row.get("Season", "Kharif"))),
            axis=1,
        )
        ndvi_min = df["NDVI_Peak"].min()
        ndvi_max = df["NDVI_Peak"].max()
        print(f"NDVI assigned from district+season lookup: range {ndvi_min:.2f}–{ndvi_max:.2f} across {len(df)} rows")
    else:
        print("No NDVI source available — setting NDVI_Peak to 0.5 (neutral placeholder)")
        df["NDVI_Peak"] = 0.5

    return df


def build_training_frame(
    base_csv_path: Path | str,
    soil_csv_path: Path | str | None = None,
    ndvi_csv_path: Path | str | None = None,
) -> pd.DataFrame:
    """
    Main entry point for preparing training data.

    Loads the base crop/weather dataset, then adds:
      1. Soil data (N, P, K, pH, Organic Carbon)
      2. NDVI vegetation index
      3. Derived weather features (GDD, heat stress days, dry days, etc.)

    The result is a single clean dataframe ready to be fed into the model.
    """
    df = load_base_training_frame(base_csv_path)

    # Add soil columns if they're not already in the dataset
    if "N" not in df.columns:
        df = attach_soil_columns(df, Path(soil_csv_path) if soil_csv_path else None)

    # Add NDVI if not already in the dataset
    if "NDVI_Peak" not in df.columns:
        df = attach_ndvi_column(df, Path(ndvi_csv_path) if ndvi_csv_path else None)

    # Derived weather features — computed from existing columns
    # These give the model richer signals than raw temperature/rainfall alone

    # Temp_Range: how wide the daily temperature swing is (hot days + cold nights = stress)
    if "Temperature_Max" in df.columns and "Temperature_Min" in df.columns and "Temp_Range" not in df.columns:
        df["Temp_Range"] = df["Temperature_Max"] - df["Temperature_Min"]

    # GDD: Growing Degree Days — total accumulated heat above 10°C over the season
    # Higher GDD = more energy available for crop growth
    if "Temperature_Avg" in df.columns and "GDD" not in df.columns:
        df["GDD"] = (df["Temperature_Avg"] - 10).clip(lower=0) * 120

    # Humidity_Rain_Interaction: captures how humid + rainy conditions compound
    # (high humidity + high rain = disease risk; low humidity + low rain = drought stress)
    if "Humidity" in df.columns and "Rainfall" in df.columns and "Humidity_Rain_Interaction" not in df.columns:
        df["Humidity_Rain_Interaction"] = df["Humidity"] * df["Rainfall"] / 100

    # Heat stress features — added during the April 2026 model upgrade
    # These two features help the model tell apart a "hot but manageable" season
    # from one with sustained heat that damages crops

    # Heat_Stress_Days: roughly how many days in the season had temperatures above 35°C
    # Estimated from average Tmax — a Tmax of 40°C means almost every day was stressful
    if "Temperature_Max" in df.columns and "Heat_Stress_Days" not in df.columns:
        season_days_map = {"Kharif": 120, "Rabi": 130, "Summer": 100}
        if "Season" in df.columns:
            season_days = df["Season"].map(season_days_map).fillna(110)
        else:
            season_days = 110
        heat_fraction = ((df["Temperature_Max"] - 35) / 10).clip(lower=0, upper=1)
        df["Heat_Stress_Days"] = (heat_fraction * season_days).round(1)

    # Dry_Days: roughly how many days had little or no rainfall
    # Estimated by assuming each rainy day contributes about 5mm of rainfall
    if "Rainfall" in df.columns and "Dry_Days" not in df.columns:
        if "Season" in df.columns:
            season_days = df["Season"].map(season_days_map).fillna(110)
        else:
            season_days = 110
        rainy_days = (df["Rainfall"] / 5).clip(upper=season_days)
        df["Dry_Days"] = (season_days - rainy_days).clip(lower=0).round(1)

    print(f"Training data ready: {len(df)} rows across {len(df.columns)} features")
    return df


def create_disease_labels(df: pd.DataFrame) -> pd.Series:
    if "Disease_Label" in df.columns:
        return pd.to_numeric(df["Disease_Label"], errors="coerce").fillna(0).astype(int)

    temperature_ok = df["Temperature_Avg"].between(20, 34, inclusive="both")
    humidity_high = df["Humidity"] >= 75
    rainfall_high = df["Rainfall"] >= 900
    ndvi_stress = df.get("NDVI_Peak", pd.Series(0.5, index=df.index)) < 0.35

    label = ((temperature_ok & humidity_high & rainfall_high) | ndvi_stress).astype(int)
    return label


def compute_default_payload(df: pd.DataFrame, features: Iterable[str]) -> dict[str, object]:
    defaults: dict[str, object] = {}
    for feature in features:
        if feature not in df.columns:
            continue
        series = df[feature]
        if pd.api.types.is_numeric_dtype(series):
            defaults[feature] = float(series.median())
        else:
            mode = series.mode(dropna=True)
            defaults[feature] = str(mode.iloc[0]) if not mode.empty else ""
    return defaults


@dataclass
class PrepareDataResult:
    input_rows: int
    output_rows: int
    output_path: Path


def run_prepare_data(
    base_csv_path: Path | str,
    output_csv_path: Path | str,
    soil_csv_path: Path | str | None,
    ndvi_csv_path: Path | str | None,
) -> PrepareDataResult:
    prepared = build_training_frame(base_csv_path, soil_csv_path, ndvi_csv_path)
    out = Path(output_csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(out, index=False)

    return PrepareDataResult(
        input_rows=len(pd.read_csv(base_csv_path)),
        output_rows=len(prepared),
        output_path=out,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Smart Farming training data.")
    parser.add_argument(
        "--base-csv",
        default=str(DATA_DIR / "final_training_lean_model_ready_with_season.csv"),
        help="Path to base training CSV.",
    )
    parser.add_argument(
        "--soil-csv",
        default=None,
        help="Path to soil CSV (N/P/K/pH). Optional.",
    )
    parser.add_argument(
        "--ndvi-csv",
        default=None,
        help="Path to NDVI CSV. Optional.",
    )
    parser.add_argument(
        "--output-csv",
        default=str(DATA_DIR / "final_training_enriched.csv"),
        help="Path where enriched dataset should be saved.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_prepare_data(
        base_csv_path=args.base_csv,
        output_csv_path=args.output_csv,
        soil_csv_path=args.soil_csv,
        ndvi_csv_path=args.ndvi_csv,
    )
    print(
        f"Prepared training data: input_rows={result.input_rows}, "
        f"output_rows={result.output_rows}, output='{result.output_path}'"
    )


if __name__ == "__main__":
    main()

