#!/usr/bin/env python3
"""
Arail Example — Georgia Peanut Farmer

A self-contained demo that runs WITHOUT a model loaded.
It uses the offline goal parser and experiment tracker to show the full
lab workflow:  goal → experiments → observations → results.

Run:
    python3 examples/peanut_farmer/run.py
"""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `arail` is importable even
# without `pip install -e .`
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from arail.skills.goal_parser import GoalParser
from arail.skills.experiment_tracker import ExperimentTracker


def main() -> None:
    sep = "=" * 70

    print()
    print(sep)
    print("  Arail — Georgia Peanut Farmer Example")
    print(sep)
    print()

    # -----------------------------------------------------------------
    # Step 1: Parse goal (offline — no model needed)
    # -----------------------------------------------------------------
    print("STEP 1  Parse your goal")
    print("-" * 70)

    parser = GoalParser()
    goal = parser.parse_offline(
        "I want to grow the best peanuts in Georgia with sustainable practices"
    )

    print(f"  Domain:     {goal['domain']}")
    print(f"  Objective:  {goal['primary_objective']}")
    print(f"  Entities:   {goal['extracted_entities']}")
    print(f"  Confidence: {goal['confidence']}")
    print()

    # -----------------------------------------------------------------
    # Step 2: Curated data (hardcoded for demo)
    # -----------------------------------------------------------------
    print("STEP 2  Lab curates relevant data")
    print("-" * 70)

    data_sources = {
        "USDA NASS":   "Georgia peanut yield 2023: 3,840 lbs/acre",
        "NOAA":        "Growing season: Apr 15 – Oct 15, avg 85 °F",
        "NRCS Soil":   "Ideal pH 5.9–7.0, sandy loam preferred",
        "Extension":   "3-year rotation reduces pests significantly",
    }
    for src, summary in data_sources.items():
        print(f"  [{src}]  {summary}")
    print()

    # -----------------------------------------------------------------
    # Step 3: Create experiments
    # -----------------------------------------------------------------
    print("STEP 3  Set up experiments")
    print("-" * 70)

    tracker = ExperimentTracker(experiments_dir="./experiments")

    exp1 = tracker.create(
        hypothesis="Splitting nitrogen at V6 + R1 increases yield by >10%",
        methodology="Split-field test, 2 reps, measure yield per acre",
        variables={"treatment": "split_N_V6_R1", "control": "single_application"},
        duration_days=180,
        metrics=["yield_per_acre", "plant_health_score"],
        domain="farming",
    )
    print(f"  Created: {exp1['id']} — {exp1['hypothesis']}")

    exp2 = tracker.create(
        hypothesis="Winter cover crop improves soil organic matter by 20%",
        methodology="Plant rye on half the field, bare soil control",
        variables={"treatment": "rye_cover", "control": "bare_soil"},
        duration_days=365,
        metrics=["organic_matter_pct", "soil_moisture"],
        domain="farming",
    )
    print(f"  Created: {exp2['id']} — {exp2['hypothesis']}")
    print()

    # -----------------------------------------------------------------
    # Step 4: Simulate season
    # -----------------------------------------------------------------
    print("STEP 4  Run season (simulated)")
    print("-" * 70)

    tracker.start(exp1["id"])
    tracker.observe(exp1["id"], "Planted Apr 18. Soil temp 68 °F.")
    tracker.observe(exp1["id"], "V6 nitrogen applied May 30. Plants vigorous.",
                    data={"nitrogen_lbs_acre": 40})
    tracker.observe(exp1["id"], "R1 nitrogen applied Jul 12.",
                    data={"nitrogen_lbs_acre": 30})
    tracker.observe(exp1["id"], "Harvest Oct 8. Treatment rows visibly larger.")

    tracker.complete(
        exp1["id"],
        results={"yield_per_acre": 4320, "plant_health_score": 8.5,
                 "increase_pct": 12.5},
        conclusion="Split nitrogen increased yield 12.5 % over single app.",
        success=True,
    )
    print(f"  Experiment {exp1['id']} completed — yield 4,320 lbs/acre (+12.5 %)")

    tracker.start(exp2["id"])
    tracker.observe(exp2["id"], "Rye planted Nov 1 after peanut harvest.")
    print(f"  Experiment {exp2['id']} in progress — cover crop planted")
    print()

    # -----------------------------------------------------------------
    # Step 5: Summary
    # -----------------------------------------------------------------
    print("STEP 5  Lab summary")
    print("-" * 70)

    all_exps = tracker.list_all()
    completed = [e for e in all_exps if e["status"] == "completed"]
    in_prog = [e for e in all_exps if e["status"] == "in_progress"]

    print(f"  Total experiments: {len(all_exps)}")
    print(f"  Completed:         {len(completed)}")
    print(f"  In progress:       {len(in_prog)}")

    if completed:
        exp = completed[0]
        print()
        print(f"  Latest result ({exp['id']}):")
        print(f"    Hypothesis supported: {exp.get('hypothesis_supported')}")
        print(f"    Yield:                {exp['results']['yield_per_acre']} lbs/acre")
        print(f"    Conclusion:           {exp['conclusion']}")

    print()
    print(sep)
    print("  Done. Experiment data saved to ./experiments/")
    print(sep)
    print()


if __name__ == "__main__":
    main()
