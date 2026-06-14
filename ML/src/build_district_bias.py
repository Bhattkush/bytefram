"""
Build district × crop yield bias multipliers from the training data.
This gives each district a unique personality based on historical yields.

Output: ML/models/district_crop_bias.json
Format: { "district": { "crop": multiplier } }
  multiplier > 1.0 = this district performs ABOVE average for this crop
  multiplier < 1.0 = this district performs BELOW average
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

from .constants import DATA_DIR, MODELS_DIR

DATA_PATH = DATA_DIR / "external" / "final_ml_training_dataset_required_columns.csv"

def build_district_crop_bias():
    df = pd.read_csv(DATA_PATH)
    df["District"] = df["District"].astype(str).str.strip().str.lower()
    df["Crop"] = df["Crop"].astype(str).str.strip()

    # State-wide median yield per crop (baseline)
    state_median = df.groupby("Crop")["Yield"].median()

    # District × Crop median yield
    district_crop = df.groupby(["District", "Crop"])["Yield"].median().reset_index()

    # Compute bias = district_median / state_median
    bias_data = {}
    for _, row in district_crop.iterrows():
        district = row["District"]
        crop = row["Crop"]
        state_val = state_median.get(crop, 1.0)
        if state_val <= 0:
            state_val = 1.0

        multiplier = row["Yield"] / state_val
        # Clamp to [0.5, 2.0] to avoid extreme outliers
        multiplier = max(0.5, min(2.0, multiplier))

        if district not in bias_data:
            bias_data[district] = {}
        bias_data[district][crop] = round(multiplier, 4)

    # Save
    output_path = MODELS_DIR / "district_crop_bias.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bias_data, f, indent=2, ensure_ascii=False)

    # Print sample
    print(f"Built bias for {len(bias_data)} districts")
    for d in ["ahmedabad", "anand", "kutch", "surat"]:
        if d in bias_data:
            top3 = sorted(bias_data[d].items(), key=lambda x: x[1], reverse=True)[:3]
            bot3 = sorted(bias_data[d].items(), key=lambda x: x[1])[:3]
            print(f"\n  {d.title()}:")
            print(f"    Best:  {', '.join(f'{c}={v:.2f}x' for c,v in top3)}")
            print(f"    Worst: {', '.join(f'{c}={v:.2f}x' for c,v in bot3)}")

    # Also build district soil defaults from the data
    soil_cols = ["N", "P", "K", "pH", "Organic_Carbon"]
    available = [c for c in soil_cols if c in df.columns]
    if available:
        soil_defaults = {}
        for district, group in df.groupby("District"):
            soil_defaults[district] = {}
            for col in available:
                val = group[col].median()
                if pd.notna(val):
                    soil_defaults[district][col] = round(float(val), 2)

        soil_path = MODELS_DIR / "district_soil_defaults.json"
        with open(soil_path, "w", encoding="utf-8") as f:
            json.dump(soil_defaults, f, indent=2, ensure_ascii=False)
        print(f"\nBuilt soil defaults for {len(soil_defaults)} districts → {soil_path.name}")

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    build_district_crop_bias()
