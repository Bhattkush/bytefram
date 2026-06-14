from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

from .constants import DATA_DIR, MODELS_DIR
from .data_pipeline import build_training_frame, compute_default_payload

def _round_metric(value: float) -> float:
    return float(np.round(value, 6))

def train_yield_model(
    df: pd.DataFrame,
) -> tuple[XGBRegressor, dict[str, float], list[str], LabelEncoder]:
    """
    Trains the main crop yield prediction model using XGBoost.

    Takes the prepared training dataframe and returns:
      - the trained model
      - accuracy metrics (R2, RMSE, MAE, MAPE)
      - list of feature names used
      - the crop label encoder (maps crop names to numbers and back)

    We remove the top 1% of yield values before training to avoid
    the model being thrown off by rare extreme harvests in the data.
    """
    
    local_df = df.copy()
    local_df = local_df[local_df["Yield"] < local_df["Yield"].quantile(0.99)]

    features = [
        "Temperature_Avg",
        "Temperature_Min",
        "Temperature_Max",
        "Rainfall",
        "Humidity",
        "N", "P", "K",
        "pH",
        "Organic_Carbon",
        "NDVI_Peak",
        "Temp_Range",
        "GDD",
        "Humidity_Rain_Interaction",
        "Heat_Stress_Days",
        "Dry_Days",
        "Crop"
    ]
    
    if "Disease_Occurred" in features:
        features.remove("Disease_Occurred")

    le_crop = LabelEncoder()
    local_df["Crop"] = le_crop.fit_transform(local_df["Crop"])

    X = local_df[features]
    y = local_df["Yield"]

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = XGBRegressor(
        n_estimators=7000,
        learning_rate=0.03,
        max_depth=9,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        early_stopping_rounds=100,
        eval_metric="rmse"
    )

    print("\n" + "-"*50)
    print(f"Starting model training — up to {model.n_estimators} rounds, stops early if no improvement")
    print("-"*50)
    
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=100,
    )

    preds = model.predict(X_val)

    metrics = {
        "r2":   _round_metric(r2_score(y_val, preds)),
        "rmse": _round_metric(np.sqrt(mean_squared_error(y_val, preds))),
        "mae":  _round_metric(mean_absolute_error(y_val, preds)),
        "mape": _round_metric(float(np.mean(np.abs((y_val - preds) / y_val.clip(lower=0.01))))),
    }
    
    return model, metrics, features, le_crop


def validate_training_data(df: pd.DataFrame) -> list[str]:
    """
    Checks the training data for common problems before we try to train.

    A bad dataset will produce a bad model — so we catch issues early:
      - Missing required columns (the model won't even start without these)
      - Too few rows (model will memorise training data instead of learning)
      - Too many NaN values in a column (means the feature is basically useless)
      - All-zero yield values (means the data wasn't loaded correctly)

    Returns a list of problem descriptions. An empty list means all good.
    """
    issues: list[str] = []

    required = ["Yield", "Crop", "Temperature_Avg", "Rainfall", "Humidity"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        issues.append(f"Missing required columns: {', '.join(missing)}")
        return issues  # Can't continue without these

    if len(df) < 50:
        issues.append(f"Only {len(df)} rows — model may overfit (need 50+ rows)")

    # Check NaN ratio per feature
    for col in df.columns:
        nan_pct = df[col].isna().mean() * 100
        if nan_pct > 50:
            issues.append(f"Column '{col}' is {nan_pct:.0f}% NaN — too sparse")
        elif nan_pct > 20:
            issues.append(f"Warning: column '{col}' is {nan_pct:.0f}% NaN")

    # Check Yield is reasonable
    if (df["Yield"] <= 0).all():
        issues.append("All Yield values are ≤ 0 — data is invalid")

    return issues

def _save_models(
    output_dir: Path,
    yield_model: XGBRegressor,
    yield_features: list[str],
    yield_crop_encoder: LabelEncoder,
    defaults: dict,
    metrics: dict,
    feature_sets: dict,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    
    joblib.dump(yield_model, output_dir / "yield_model.pkl")
    joblib.dump(yield_crop_encoder, output_dir / "crop_encoder.pkl")
    joblib.dump(yield_features, output_dir / "features.pkl")
        
    metadata = {
        "version": "2.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "feature_sets": feature_sets,
        "defaults": defaults,
    }
    (output_dir / "model_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Smart Farming models.")
    parser.add_argument("--base-csv",
        default=str(DATA_DIR / "external" / "final_ml_training_dataset_required_columns.csv"))
    parser.add_argument("--soil-csv",  default=None)
    parser.add_argument("--ndvi-csv",  default=None)
    parser.add_argument("--prepared-csv-out",
        default=str(DATA_DIR / "final_training_enriched.csv"))
    parser.add_argument("--output-dir", default=str(MODELS_DIR))
    return parser.parse_args()

def main() -> None:
    args = _parse_args()

    # Step 1 — Load the training data and apply feature engineering
    # This builds a clean dataframe with all the columns the model needs
    try:
        training_df = build_training_frame(args.base_csv, args.soil_csv, args.ndvi_csv)
    except FileNotFoundError as exc:
        print(f"\nCould not find the training file: {exc}")
        print(f"   Looking for: {args.base_csv}")
        sys.exit(1)
    except ValueError as exc:
        print(f"\nThe training file has a problem: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nSomething went wrong while loading the data ({type(exc).__name__}): {exc}")
        sys.exit(1)

    # Step 2 — Run a quick sanity check on the data before we waste time training
    # Common issues: missing columns, too few rows, too many blank values
    issues = validate_training_data(training_df)
    if issues:
        print("\nFound some issues with the training data:")
        for issue in issues:
            print(f"   - {issue}")
        # If a critical column is missing or yield values are all zero, stop here
        fatal = [i for i in issues if "Missing required" in i or "invalid" in i]
        if fatal:
            print("\nCan't train with this data — please fix the issues above and try again.")
            sys.exit(1)
        print("   Minor issues found, but continuing anyway...\n")

    # Step 3 — Train the XGBoost yield prediction model
    # This is the heavy step — will print progress every 100 rounds
    try:
        yield_model, yield_metrics, yield_features, yield_crop_encoder = train_yield_model(training_df)
    except Exception as exc:
        print(f"\nTraining crashed ({type(exc).__name__}): {exc}")
        sys.exit(1)

    # Step 4 — Save everything to disk so the API can load it later
    # Saves: the model file, the crop encoder, feature list, and accuracy report
    try:
        all_features = sorted(set(yield_features))
        defaults     = compute_default_payload(training_df, all_features)

        metrics      = {"yield_model": yield_metrics}
        feature_sets = {"yield_model": yield_features}

        _save_models(
            output_dir=Path(args.output_dir),
            yield_model=yield_model,
            yield_features=yield_features,
            yield_crop_encoder=yield_crop_encoder,
            defaults=defaults,
            metrics=metrics,
            feature_sets=feature_sets,
        )
    except Exception as exc:
        print(f"\nCould not save the model files ({type(exc).__name__}): {exc}")
        sys.exit(1)

    print(f"\nDone! Model files saved to: {args.output_dir}")
    print("Accuracy report:")
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    main()
