import json
from pathlib import Path
from datetime import datetime

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"

def get_season_from_date(date_obj=None) -> str:
    """Return Kharif, Rabi, or Summer based on month."""
    if date_obj is None:
        date_obj = datetime.now()
    
    month = date_obj.month
    if 6 <= month <= 10:
        return "Kharif"
    elif 3 <= month <= 5:
        return "Summer"
    else:  # 11, 12, 1, 2
        return "Rabi"

def get_valid_crops_for_location(district_name: str) -> list[str]:
    """Return list of historically valid crops for a district. If unknown, returns empty."""
    mapping_file = MODELS_DIR / "location_mapping.json"
    if mapping_file.exists():
        with open(mapping_file, "r") as f:
            mapping = json.load(f)
        district = str(district_name).strip().lower()
        return mapping.get(district, [])
    return []

def classify_production_level(crop: str, yield_val: float) -> str:
    """Classify the payload yield value as High, Medium, or Low."""
    thresholds_file = MODELS_DIR / "production_thresholds.json"
    if thresholds_file.exists():
        with open(thresholds_file, "r") as f:
            thresholds = json.load(f)
        
        crop_name = str(crop).strip()
        if crop_name in thresholds:
            t = thresholds[crop_name]
            # Soften thresholds to make labels feel more realistic/encouraging
            realistic_high = t["high"] * 0.85
            realistic_low = t["low"] * 0.70
            
            if yield_val >= realistic_high:
                return "High"
            elif yield_val <= realistic_low:
                return "Low"
            else:
                return "Medium"
    
    # Fallback absolute heuristic if NO data
    if yield_val > 4.0: return "High"
    if yield_val < 1.0: return "Low"
    return "Medium"
