"""
Geographic Shift Demo — Summer Season
=======================================
Demonstrates how the recommendation engine adapts to different climate zones
across Gujarat: Kutch → Ahmedabad → Rajkot → Surat → Navsari

Climate zone progression:
  Kutch      → Arid,       Rainfed   (extreme dry, only drought-tolerant crops)
  Ahmedabad  → Semi-Arid,  Rainfed   (slightly more humid, still dry)
  Rajkot     → Semi-Arid,  Irrigated (irrigation unlocks moisture-sensitive crops)
  Surat      → Coastal,    Irrigated (high humidity + irrigation = wide variety)
  Navsari    → Coastal,    Rainfed   (natural humidity + sea breeze, good baseline)

Run from project root:
    python -m ML.tests.demo_geographic_shift
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ML.src.suggestion_engine import FarmerDecisionSystem

# ── Terminal colours ─────────────────────────────────────────────────────────
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
MAGENTA = "\033[95m"
RESET   = "\033[0m"

RISK_COLOR = {"Low Risk": GREEN, "Medium Risk": YELLOW, "High Risk": RED}

ZONE_LABELS = {
    "arid":      f"{RED}Arid{RESET}",
    "semi_arid": f"{YELLOW}Semi-Arid{RESET}",
    "coastal":   f"{CYAN}Coastal{RESET}",
}

def suitability_bar(score: float, width: int = 12) -> str:
    filled = int(score * width)
    empty  = width - filled
    color  = GREEN if score >= 0.75 else YELLOW if score >= 0.50 else RED
    return f"{color}{'█' * filled}{'░' * empty}{RESET} {score:.0%}"

def run_demo():
    # City, district key, region type, irrigated
    cities = [
        ("Kutch",     "kutch",     "arid",      False),
        ("Ahmedabad", "ahmedabad", "semi_arid",  False),
        ("Rajkot",    "rajkot",    "semi_arid",  True),
        ("Surat",     "surat",     "coastal",    True),
        ("Navsari",   "navsari",   "coastal",    False),
    ]

    system = FarmerDecisionSystem()

    print()
    print(f"{BOLD}{CYAN}{'═'*70}{RESET}")
    print(f"{BOLD}{CYAN}  🌍  GEOGRAPHIC CROP SHIFT — SUMMER SEASON  |  GUJARAT{RESET}")
    print(f"{BOLD}{CYAN}  Kutch → Ahmedabad → Rajkot → Surat → Navsari{RESET}")
    print(f"{BOLD}{CYAN}{'═'*70}{RESET}")

    prev_crops: set[str] = set()

    for city, district, region_type, irrigated in cities:
        zone_label = ZONE_LABELS.get(region_type, region_type)
        irr_label  = f"{CYAN}💧 Irrigated{RESET}" if irrigated else f"{DIM}🌧  Rainfed{RESET}"

        print()
        print(f"  {BOLD}📍 {city.upper()}{RESET}  ·  {zone_label}  ·  {irr_label}")
        print(f"  {'─'*66}")

        result = system.recommend_safe(
            city=city,
            district=district,
            top_n=3,
            irrigated=irrigated,
        )

        if result.get("status") != "ok":
            print(f"  {RED}⚠ Error: {result.get('message')}{RESET}")
            continue

        w = result["weather_summary"]
        print(f"  🌤  Climate  : Avg {w['Temperature_Avg']}°C  |  "
              f"Rainfall {w['Seasonal_Rainfall_mm']} mm  |  "
              f"Humidity {w['Humidity']}%")
        print(f"  📊 Insight  : {DIM}{result.get('insight', '')}{RESET}")
        print()

        crops = result.get("top_recommended_crops", [])
        curr_crops = {c["crop_name"] for c in crops}

        # Work out new crops vs previous city
        new_crops   = curr_crops - prev_crops
        lost_crops  = prev_crops - curr_crops if prev_crops else set()

        medals = ["🥇", "🥈", "🥉"]
        for i, crop in enumerate(crops):
            name   = crop["crop_name"]
            suit   = crop["suitability_score"]
            risk   = crop["risk_confidence"]
            rc     = RISK_COLOR.get(risk, RESET)
            bar    = suitability_bar(suit)
            medal  = medals[i] if i < 3 else f"{i+1}."

            # Tag new crops that didn't appear in previous city
            tag = f"  {GREEN}← NEW{RESET}" if name in new_crops else ""

            print(f"    {medal}  {BOLD}{name:<22}{RESET}  {bar}  {rc}{risk}{RESET}{tag}")
            reason = crop.get("reason", "")
            if reason:
                # Print first sentence only (keep it tight)
                first = reason.split(".")[0]
                print(f"         {DIM}💡 {first}{RESET}")

        # Crops that dropped off vs last city
        if lost_crops:
            print(f"\n  {DIM}↓ No longer recommended: {', '.join(sorted(lost_crops))}{RESET}")

        if new_crops:
            print(f"  {GREEN}↑ Newly recommended  : {', '.join(sorted(new_crops))}{RESET}")

        prev_crops = curr_crops

    print()
    print(f"{BOLD}{CYAN}{'═'*70}{RESET}")
    print(f"{BOLD}  ✅ Demo complete — ran via Open-Meteo 10-year seasonal climate normals{RESET}")
    print(f"{BOLD}{CYAN}{'═'*70}{RESET}")
    print()


if __name__ == "__main__":
    run_demo()
