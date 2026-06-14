import json
from pathlib import Path
import pandas as pd
import numpy as np

def build_mappings():
    base_dir = Path(__file__).resolve().parents[1]
    data_path = base_dir / "data" / "external" / "final_ml_training_dataset_required_columns.csv"
    models_dir = base_dir / "models"
    
    if not data_path.exists():
        print(f"Dataset not found at {data_path}")
        return

    df = pd.read_csv(data_path)

    # 1. Location -> Crop Mapping
    print("Building Location -> Crop mapping...")
    # Normalize to lower case, title case, or mapping generic
    location_mapping = {}
    for district, group in df.groupby("District"):
        valid_crops = group["Crop"].unique().tolist()
        # Normalizing district string (lowercase for easier searching)
        location_mapping[str(district).strip().lower()] = valid_crops
    
    with open(models_dir / "location_mapping.json", "w", encoding="utf-8") as f:
        json.dump(location_mapping, f, indent=2)

    # 2. Crop -> Production Thresholds (33rd and 66th percentile)
    print("Building Crop -> Yield Threshold mapping...")
    production_thresholds = {}
    for crop, group in df.groupby("Crop"):
        yields = group["Yield"].dropna()
        if len(yields) < 5:
            # Not enough data for robust percentiles, use global median roughly or local
             production_thresholds[str(crop).strip()] = {"low": 0.5, "high": 2.0}
        else:
             low_pct = float(np.percentile(yields, 33))
             high_pct = float(np.percentile(yields, 66))
             # ensure high > low 
             if high_pct == low_pct:
                 high_pct += 0.1
             production_thresholds[str(crop).strip()] = {
                 "low": round(low_pct, 4),
                 "high": round(high_pct, 4)
             }

    with open(models_dir / "production_thresholds.json", "w", encoding="utf-8") as f:
        json.dump(production_thresholds, f, indent=2)

    print("Mappings successfully built and saved to models directory!")

if __name__ == "__main__":
    build_mappings()
