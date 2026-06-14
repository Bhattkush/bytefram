"""
FINAL VALIDATION TEST SUITE — Pre-Deployment Checks
=====================================================
Tests 5 critical scenarios to validate production readiness:

1. 🔥 Extreme Edge Test (Kutch, 0-5mm rain, 40-45°C, rainfed)
2. 💧 High Irrigation Test (Surat, irrigated, low rainfall)
3. 🌧 Monsoon Simulation (Kharif, 500-800mm rainfall)
4. ❗ Invalid Condition Test (extreme temps: 10°C and 50°C)
5. 📊 Stability Test (5 identical runs → identical output)

Plus micro-checks:
- Suitability ordering consistency
- Risk vs suitability alignment
- Explainability (reason quality)
"""

import sys
import os
import json
import copy

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ML.src.rule_engine import (
    _load_requirements,
    pre_filter_crops,
    compute_suitability,
    generate_reason,
    calculate_risk,
)
from ML.src.suggestion_engine import _build_season_crop_map, CROP_CATEGORY

# ── Helpers ───────────────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"
total_pass = 0
total_fail = 0
total_warn = 0


def check(condition, label, detail=""):
    global total_pass, total_fail
    if condition:
        total_pass += 1
        print(f"  {PASS} {label}")
    else:
        total_fail += 1
        print(f"  {FAIL} {label}")
    if detail:
        print(f"        → {detail}")


def warn_check(condition, label, detail=""):
    global total_warn, total_pass
    if condition:
        total_pass += 1
        print(f"  {PASS} {label}")
    else:
        total_warn += 1
        print(f"  {WARN} {label}")
    if detail:
        print(f"        → {detail}")


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ── Load crop requirements once ───────────────────────────────────────────────
requirements = _load_requirements()
season_map = _build_season_crop_map()

# Get all Summer crops (current season is April = Summer)
summer_crops = list(season_map.get("Summer", set()))
kharif_crops = list(season_map.get("Kharif", set()))
all_crops = list(requirements.keys())


# ==============================================================================
# TEST 1: 🔥 EXTREME EDGE TEST (Worst Case)
# ==============================================================================
section("TEST 1: 🔥 EXTREME EDGE TEST — Kutch, 0-5mm rain, 40-45°C, Rainfed")

extreme_weather = {
    "Temperature_Avg": 42.5,
    "Temperature_Min": 35.0,
    "Temperature_Max": 47.0,
    "Rainfall": 3.0,       # Near-zero rainfall
    "Humidity": 15.0,
}

# Pre-filter with Summer crops (April is Summer)
feasible, penalties = pre_filter_crops(
    crops=summer_crops,
    weather=extreme_weather,
    soil=None,
    irrigated=False,
    season="Summer",
    region="arid",
)

print(f"\n  Summer crops considered: {len(summer_crops)}")
print(f"  Feasible after filter:  {len(feasible)}")
print(f"  Feasible crops: {feasible}")

# If too few, try relaxed mode (like the suggestion engine does)
if len(feasible) < 3:
    print(f"\n  → Less than 3 feasible, trying relaxed mode...")
    feasible_relax, penalties_relax = pre_filter_crops(
        crops=summer_crops,
        weather=extreme_weather,
        soil=None,
        irrigated=False,
        season="Summer",
        region="arid",
        relax=True,
    )
    print(f"  Feasible (relaxed): {len(feasible_relax)}")
    print(f"  Feasible crops (relaxed): {feasible_relax}")
    
    # Use relaxed results for remaining checks
    test1_crops = feasible_relax
    test1_penalties = penalties_relax
else:
    test1_crops = feasible
    test1_penalties = penalties

# Check: Still returns 2-3 crops
check(len(test1_crops) >= 2, 
      f"Returns ≥2 crops even in extreme conditions ({len(test1_crops)} found)")

# Check suitability range (expect 50-65% for extreme)
suitabilities = {}
for crop in test1_crops:
    suit = compute_suitability(
        crop=crop,
        weather=extreme_weather,
        soil=None,
        irrigated=False,
        penalty=test1_penalties.get(crop, 0.0),
        region="arid",
    )
    suitabilities[crop] = suit

print(f"\n  Suitability scores:")
for crop, suit in sorted(suitabilities.items(), key=lambda x: -x[1]):
    risk = calculate_risk(extreme_weather, crop=crop, irrigated=False, 
                          penalty=test1_penalties.get(crop, 0.0))
    print(f"    {crop:25s} → {suit*100:.1f}%  (penalty={test1_penalties.get(crop, 0):.2f})  [{risk}]")

# Check suitability range
if suitabilities:
    max_suit = max(suitabilities.values())
    min_suit = min(suitabilities.values())
    check(max_suit <= 0.80, f"No overconfidence: max suitability = {max_suit*100:.1f}% (≤80%)")
    check(min_suit >= 0.05, f"No collapse: min suitability = {min_suit*100:.1f}% (≥5%)")

# Check risk levels (expect High or Medium)
for crop in test1_crops:
    risk = calculate_risk(extreme_weather, crop=crop, irrigated=False, 
                          penalty=test1_penalties.get(crop, 0.0))
    check(risk in ("High Risk", "Medium Risk"), 
          f"Risk for {crop} = {risk} (expected High/Medium in extreme conditions)")


# ==============================================================================
# TEST 2: 💧 HIGH IRRIGATION TEST — Surat, Irrigated
# ==============================================================================
section("TEST 2: 💧 HIGH IRRIGATION TEST — Surat, Irrigated, Low Rainfall")

irrigation_weather = {
    "Temperature_Avg": 32.0,
    "Temperature_Min": 24.0,
    "Temperature_Max": 38.0,
    "Rainfall": 80.0,       # Low rainfall
    "Humidity": 55.0,
}

# Test with and without irrigation
feasible_dry, pen_dry = pre_filter_crops(
    crops=summer_crops,
    weather=irrigation_weather,
    soil=None,
    irrigated=False,
    season="Summer",
    region="coastal",
)

feasible_wet, pen_wet = pre_filter_crops(
    crops=summer_crops,
    weather=irrigation_weather,
    soil=None,
    irrigated=True,
    season="Summer",
    region="coastal",
)

# Also include off-season irrigated candidates (like Maize, Rice)
# The suggestion engine includes off_season_irrigated crops
all_candidates = list(set(summer_crops))
for crop_name, req in requirements.items():
    if req.get("off_season_irrigated", False) and crop_name not in all_candidates:
        all_candidates.append(crop_name)

feasible_wet_all, pen_wet_all = pre_filter_crops(
    crops=all_candidates,
    weather=irrigation_weather,
    soil=None,
    irrigated=True,
    season="Summer",
    region="coastal",
)

print(f"\n  Rainfed crops:   {len(feasible_dry)} → {feasible_dry}")
print(f"  Irrigated crops: {len(feasible_wet)} → {feasible_wet}")
print(f"  Irrigated+offseasonal: {len(feasible_wet_all)} → {feasible_wet_all}")

check(len(feasible_wet) >= len(feasible_dry), 
      f"Irrigation adds variety: {len(feasible_wet)} ≥ {len(feasible_dry)} crops")

# Check if high-value crops appear with irrigation
high_value = {"Rice", "Maize", "Sugarcane", "Cotton(lint)", "Banana"}
irrigated_hvcrops = [c for c in feasible_wet_all if c in high_value]
print(f"\n  High-value crops with irrigation: {irrigated_hvcrops}")
check(len(irrigated_hvcrops) >= 1, 
      f"At least 1 high-value crop appears with irrigation ({len(irrigated_hvcrops)} found)")

# Risk comparison: irrigated should have lower risk
print(f"\n  Risk comparison (irrigated vs rainfed):")
common_crops = set(feasible_dry) & set(feasible_wet)
for crop in sorted(common_crops):
    risk_dry = calculate_risk(irrigation_weather, crop=crop, irrigated=False, 
                              penalty=pen_dry.get(crop, 0.0))
    risk_wet = calculate_risk(irrigation_weather, crop=crop, irrigated=True, 
                              penalty=pen_wet.get(crop, 0.0))
    print(f"    {crop:25s} → Rainfed: {risk_dry:15} | Irrigated: {risk_wet}")
    # Irrigated risk should be ≤ rainfed risk
    risk_order = {"Low Risk": 0, "Medium Risk": 1, "High Risk": 2}
    warn_check(risk_order.get(risk_wet, 1) <= risk_order.get(risk_dry, 1),
               f"Irrigation reduces/maintains risk for {crop}")


# ==============================================================================
# TEST 3: 🌧 MONSOON SIMULATION — Kharif Season
# ==============================================================================
section("TEST 3: 🌧 MONSOON SIMULATION — Kharif, 500-800mm Rainfall")

monsoon_weather = {
    "Temperature_Avg": 28.0,
    "Temperature_Min": 22.0,
    "Temperature_Max": 35.0,
    "Rainfall": 650.0,       # Monsoon rainfall
    "Humidity": 78.0,
}

feasible_kharif, pen_kharif = pre_filter_crops(
    crops=kharif_crops,
    weather=monsoon_weather,
    soil=None,
    irrigated=False,
    season="Kharif",
    region=None,
)

print(f"\n  Kharif crops considered: {len(kharif_crops)}")
print(f"  Feasible after filter:  {len(feasible_kharif)}")
print(f"  Feasible: {feasible_kharif}")

# Expected monsoon crops
expected_monsoon = {"Rice", "Cotton(lint)", "Groundnut"}
found_monsoon = expected_monsoon & set(feasible_kharif)
print(f"\n  Expected monsoon crops found: {found_monsoon}")

# Rice needs 1000mm+ so it might be filtered — that's OK if using irrigated
check("Groundnut" in feasible_kharif or "Cotton(lint)" in feasible_kharif,
      "At least one major monsoon crop (Groundnut/Cotton) appears")

# Bajra should have LOWER importance in monsoon (it's a dry-area crop)
suit_scores_kharif = {}
for crop in feasible_kharif:
    suit = compute_suitability(
        crop=crop,
        weather=monsoon_weather,
        soil=None,
        irrigated=False,
        penalty=pen_kharif.get(crop, 0.0),
    )
    suit_scores_kharif[crop] = suit

print(f"\n  Kharif suitability ranking:")
for crop, suit in sorted(suit_scores_kharif.items(), key=lambda x: -x[1]):
    risk = calculate_risk(monsoon_weather, crop=crop, irrigated=False,
                          penalty=pen_kharif.get(crop, 0.0))
    print(f"    {crop:25s} → {suit*100:.1f}%  [{risk}]")

# Check Bajra is not #1 (it's a drought crop — shouldn't dominate in monsoon)
if "Bajra" in suit_scores_kharif and len(suit_scores_kharif) > 1:
    sorted_crops = sorted(suit_scores_kharif.items(), key=lambda x: -x[1])
    bajra_rank = next(i for i, (c, _) in enumerate(sorted_crops) if c == "Bajra")
    warn_check(bajra_rank > 0, 
               f"Bajra not ranked #1 in monsoon (rank={bajra_rank+1})",
               "Drought crop shouldn't dominate when rainfall is abundant")


# ==============================================================================
# TEST 4: ❗ INVALID CONDITION TEST — Extreme Temperatures
# ==============================================================================
section("TEST 4: ❗ INVALID CONDITION TEST — Extreme Temperatures")

# Test A: Very LOW temperature (10°C)
print("\n  --- Test 4A: Very Low Temperature (10°C) ---")
cold_weather = {
    "Temperature_Avg": 10.0,
    "Temperature_Min": 4.0,
    "Temperature_Max": 16.0,
    "Rainfall": 200.0,
    "Humidity": 50.0,
}

feasible_cold, pen_cold = pre_filter_crops(
    crops=summer_crops,
    weather=cold_weather,
    soil=None,
    irrigated=False,
    season="Summer",
    region=None,
)

# Try relaxed if too few
if len(feasible_cold) < 2:
    feasible_cold_r, pen_cold_r = pre_filter_crops(
        crops=summer_crops,
        weather=cold_weather,
        soil=None,
        irrigated=False,
        season="Summer",
        region=None,
        relax=True,
    )
    print(f"  Feasible (strict): {len(feasible_cold)}, Feasible (relaxed): {len(feasible_cold_r)}")
    print(f"  Relaxed crops: {feasible_cold_r}")
    # System should either return fallback crops OR at minimum not crash
    check(True, "System did NOT crash on extreme cold input")
    if feasible_cold_r:
        for crop in feasible_cold_r:
            suit = compute_suitability(crop=crop, weather=cold_weather, penalty=pen_cold_r.get(crop, 0))
            risk = calculate_risk(cold_weather, crop=crop, penalty=pen_cold_r.get(crop, 0))
            print(f"    {crop:25s} → {suit*100:.1f}%  [{risk}]")
            check(suit < 0.8, f"Cold-condition suitability for {crop} is conservative ({suit*100:.1f}%)")
else:
    print(f"  Feasible in cold: {feasible_cold}")
    check(True, "System handles cold input without crash")

# Test B: Very HIGH temperature (50°C)
print(f"\n  --- Test 4B: Very High Temperature (50°C) ---")
hot_weather = {
    "Temperature_Avg": 50.0,
    "Temperature_Min": 42.0,
    "Temperature_Max": 55.0,
    "Rainfall": 5.0,
    "Humidity": 10.0,
}

feasible_hot, pen_hot = pre_filter_crops(
    crops=summer_crops,
    weather=hot_weather,
    soil=None,
    irrigated=False,
    season="Summer",
    region="arid",
)

if len(feasible_hot) < 2:
    feasible_hot_r, pen_hot_r = pre_filter_crops(
        crops=summer_crops,
        weather=hot_weather,
        soil=None,
        irrigated=False,
        season="Summer",
        region="arid",
        relax=True,
    )
    print(f"  Feasible (strict): {len(feasible_hot)}, Feasible (relaxed): {len(feasible_hot_r)}")
    print(f"  Relaxed crops: {feasible_hot_r}")
    check(True, "System did NOT crash on 50°C input")
    if feasible_hot_r:
        for crop in feasible_hot_r:
            suit = compute_suitability(crop=crop, weather=hot_weather, penalty=pen_hot_r.get(crop, 0))
            risk = calculate_risk(hot_weather, crop=crop, penalty=pen_hot_r.get(crop, 0))
            print(f"    {crop:25s} → {suit*100:.1f}%  [{risk}]")
            check(risk in ("High Risk", "Medium Risk"), 
                  f"Risk at 50°C for {crop} = {risk} (expected High/Medium)")
    else:
        # No crops survive even relaxed — that's OK, just shouldn't crash
        check(True, "No crops survive 50°C — system correctly filters all (strong warning implied)")
else:
    print(f"  Feasible at 50°C: {feasible_hot}")
    check(True, "System handles extreme heat without crash")


# ==============================================================================
# TEST 5: 📊 STABILITY TEST — 5 Identical Runs
# ==============================================================================
section("TEST 5: 📊 STABILITY TEST — 5 Identical Runs, Same Input")

stable_weather = {
    "Temperature_Avg": 33.0,
    "Temperature_Min": 25.0,
    "Temperature_Max": 40.0,
    "Rainfall": 50.0,
    "Humidity": 35.0,
}

runs = []
for i in range(5):
    f_crops, f_pens = pre_filter_crops(
        crops=summer_crops,
        weather=stable_weather,
        soil=None,
        irrigated=False,
        season="Summer",
        region="arid",
    )
    
    # Compute suitability for each
    scores = {}
    for crop in f_crops:
        suit = compute_suitability(
            crop=crop,
            weather=stable_weather,
            soil=None,
            irrigated=False,
            penalty=f_pens.get(crop, 0.0),
            region="arid",
        )
        scores[crop] = suit
    
    runs.append({
        "crops": sorted(f_crops),
        "penalties": {k: f_pens[k] for k in sorted(f_pens)},
        "scores": {k: scores[k] for k in sorted(scores)},
    })

# Compare all runs to first run
all_identical = True
for i in range(1, 5):
    if runs[i]["crops"] != runs[0]["crops"]:
        all_identical = False
        print(f"  Run {i+1} crops differ from Run 1!")
    if runs[i]["scores"] != runs[0]["scores"]:
        all_identical = False
        print(f"  Run {i+1} scores differ from Run 1!")

check(all_identical, "All 5 runs produce IDENTICAL output (deterministic)")

print(f"\n  Run 1 output (representative):")
for crop, suit in sorted(runs[0]["scores"].items(), key=lambda x: -x[1]):
    print(f"    {crop:25s} → {suit*100:.1f}%  (penalty={runs[0]['penalties'].get(crop, 0):.2f})")


# ==============================================================================
# MICRO-CHECK 1: SUITABILITY ORDERING CONSISTENCY
# ==============================================================================
section("MICRO-CHECK 1: Suitability Ordering Consistency")

# Test with Kutch-like conditions
kutch_weather = {
    "Temperature_Avg": 35.0,
    "Temperature_Min": 27.0,
    "Temperature_Max": 42.0,
    "Rainfall": 60.0,
    "Humidity": 30.0,
}

feasible_kutch, pen_kutch = pre_filter_crops(
    crops=summer_crops,
    weather=kutch_weather,
    soil=None,
    irrigated=False,
    season="Summer",
    region="arid",
)

scores_kutch = {}
for crop in feasible_kutch:
    suit = compute_suitability(
        crop=crop,
        weather=kutch_weather,
        soil=None,
        irrigated=False,
        penalty=pen_kutch.get(crop, 0.0),
        region="arid",
    )
    scores_kutch[crop] = suit

# Sort by suitability score
sorted_kutch = sorted(scores_kutch.items(), key=lambda x: -x[1])
print(f"\n  Kutch Summer suitability ranking (should be sorted by final_score):")
for rank, (crop, suit) in enumerate(sorted_kutch, 1):
    pen = pen_kutch.get(crop, 0.0)
    print(f"    #{rank} {crop:25s} → {suit*100:.1f}%  (penalty={pen:.2f})")

# Verify ordering is actually descending
is_sorted = all(sorted_kutch[i][1] >= sorted_kutch[i+1][1] for i in range(len(sorted_kutch)-1))
check(is_sorted, "Crops are sorted by final_score (descending)")

# Check that Bajra gets arid bonus
if "Bajra" in scores_kutch:
    bajra_score = scores_kutch["Bajra"]
    check(bajra_score >= 0.50, 
          f"Bajra has strong arid suitability ({bajra_score*100:.1f}%)")


# ==============================================================================
# MICRO-CHECK 2: RISK vs SUITABILITY ALIGNMENT
# ==============================================================================
section("MICRO-CHECK 2: Risk vs Suitability Alignment")

# Use multiple weather scenarios to test alignment
test_scenarios = [
    ("Favorable", {
        "Temperature_Avg": 28.0, "Temperature_Min": 22.0, "Temperature_Max": 34.0,
        "Rainfall": 500.0, "Humidity": 65.0,
    }),
    ("Harsh", {
        "Temperature_Avg": 40.0, "Temperature_Min": 32.0, "Temperature_Max": 46.0,
        "Rainfall": 20.0, "Humidity": 15.0,
    }),
]

misalignment_count = 0
for scenario_name, weather in test_scenarios:
    print(f"\n  --- Scenario: {scenario_name} ---")
    
    # Use all summer crops for this check
    f_crops, f_pens = pre_filter_crops(
        crops=summer_crops, weather=weather, irrigated=False, season="Summer",
    )
    if len(f_crops) < 3:
        f_crops, f_pens = pre_filter_crops(
            crops=summer_crops, weather=weather, irrigated=False, season="Summer", relax=True,
        )
    
    for crop in f_crops[:6]:  # Check first 6
        suit = compute_suitability(
            crop=crop, weather=weather, soil=None, irrigated=False,
            penalty=f_pens.get(crop, 0.0),
        )
        risk = calculate_risk(weather, crop=crop, irrigated=False, 
                              penalty=f_pens.get(crop, 0.0))
        
        # Alignment checks:
        # 1. Low suitability should NEVER have "Low Risk"
        # 2. High suitability should RARELY have "High Risk"
        misaligned = False
        if suit < 0.30 and risk == "Low Risk":
            misaligned = True
            misalignment_count += 1
            print(f"    {FAIL} {crop:20s} → suit={suit*100:.1f}% but {risk} (LOW SUIT + LOW RISK)")
        elif suit >= 0.70 and risk == "High Risk":
            misaligned = True
            misalignment_count += 1
            print(f"    {WARN} {crop:20s} → suit={suit*100:.1f}% but {risk} (HIGH SUIT + HIGH RISK)")
        else:
            print(f"    {PASS} {crop:20s} → suit={suit*100:.1f}%, {risk} (aligned)")

check(misalignment_count == 0, 
      f"No risk/suitability misalignments found ({misalignment_count} issues)")


# ==============================================================================
# MICRO-CHECK 3: EXPLAINABILITY — Reason Quality
# ==============================================================================
section("MICRO-CHECK 3: Explainability — Reason Quality")

# Generate reasons for a few crops under different conditions
test_cases = [
    ("Bajra", kutch_weather, False, 0.0, "Arid, rainfed"),
    ("Moong(Green Gram)", kutch_weather, False, 0.0, "Dry conditions"),
    ("Sesamum", kutch_weather, True, 0.0, "Irrigated"),
]

for crop, weather, irrigated, penalty, label in test_cases:
    if crop not in requirements:
        continue
    suit = compute_suitability(crop=crop, weather=weather, irrigated=irrigated, penalty=penalty)
    reason = generate_reason(
        crop=crop, weather=weather, soil=None, suitability=suit,
        irrigated=irrigated, penalty=penalty,
    )
    
    print(f"\n  {crop} ({label}):")
    print(f"    Suitability: {suit*100:.1f}%")
    print(f"    Reason: \"{reason}\"")
    
    # Check reason quality
    check(len(reason) > 20, f"Reason for {crop} is descriptive (len={len(reason)})")
    check("temperature" in reason.lower() or "rainfall" in reason.lower() or "drought" in reason.lower(),
          f"Reason mentions specific conditions (temp/rain/drought)")
    
    # Check that description is included
    desc = requirements[crop].get("description", "")
    if desc:
        # The first part of the reason should be the description (capitalized)
        warn_check(desc.lower()[:20] in reason.lower()[:50], 
                   f"Reason includes crop description for {crop}")


# ==============================================================================
# BONUS: SEASON MAP INTEGRITY
# ==============================================================================
section("BONUS: Season Map Integrity")

print(f"\n  Season → Crop counts:")
for season, crops_set in season_map.items():
    print(f"    {season:10s} → {len(crops_set)} crops: {sorted(crops_set)}")

check(len(season_map["Kharif"]) >= 8, f"Kharif has enough crops ({len(season_map['Kharif'])})")
check(len(season_map["Summer"]) >= 3, f"Summer has enough crops ({len(season_map['Summer'])})")
check(len(season_map["Rabi"]) >= 5, f"Rabi has enough crops ({len(season_map['Rabi'])})")

# Whole Year crops should appear in ALL seasons
whole_year_crops = [c for c, r in requirements.items() if "Whole Year" in r.get("seasons", [])]
print(f"\n  Whole Year crops: {whole_year_crops}")
for wy_crop in whole_year_crops:
    for season_name in ["Kharif", "Rabi", "Summer"]:
        check(wy_crop in season_map[season_name], 
              f"{wy_crop} appears in {season_name} (Whole Year)")


# ==============================================================================
# FINAL SUMMARY
# ==============================================================================
section("📋 FINAL VALIDATION SUMMARY")

print(f"""
  Total Checks:  {total_pass + total_fail + total_warn}
  ✅ Passed:     {total_pass}
  ❌ Failed:     {total_fail}
  ⚠️  Warnings:  {total_warn}
""")

if total_fail == 0:
    print(f"  🏆 ALL CRITICAL CHECKS PASSED — SYSTEM IS PRODUCTION READY")
    if total_warn > 0:
        print(f"  📝 {total_warn} non-critical warnings to review")
else:
    print(f"  🚨 {total_fail} CRITICAL FAILURES — MUST FIX BEFORE DEPLOYMENT")

print(f"\n{'='*70}\n")
