"""TA4: knowledge representation, rule-based reasoning, and case-based reasoning.

All cases, response ratios, and actions are classroom examples, not emergency advice.
Run normally for a reproducible demo; add --interactive to revise and retain cases.
"""

import argparse
import json
import tempfile
from copy import deepcopy
from fractions import Fraction
from math import ceil
from pathlib import Path


# Task 1A: eight facts organized into three explicit categories.
def make_facts(hazard, severity, people, shelters, teams,
               flooding=True, area="urban", access="restricted"):
    return {
        "weather": {"hazard": hazard, "severity": severity,
                    "expected_flooding": flooding},
        "community": {"area_type": area, "affected_people": people,
                      "road_access": access},
        "resources": {"shelter_places": shelters, "response_teams": teams},
    }


FACTS = make_facts("typhoon", 5, 1200, 700, 5)


# Task 2A: each function represents one independently evaluated IF-THEN rule.
def rule_storm(facts):
    weather = facts["weather"]
    if weather["hazard"] == "typhoon" and weather["severity"] >= 4:
        return "Prepare LGU coordination and public updates."


def rule_flood(facts):
    if facts["weather"]["expected_flooding"]:
        return "Review early evacuation from flood-prone areas."


def rule_shelter(facts):
    gap = facts["community"]["affected_people"] - facts["resources"]["shelter_places"]
    if gap > 0:
        return f"Review {gap} additional shelter places for all affected people."


def rule_teams(facts):
    # One team per 200 people is an illustrative rule for this exercise only.
    required = ceil(facts["community"]["affected_people"] / 200)
    gap = required - facts["resources"]["response_teams"]
    if gap > 0:
        return f"Review {gap} additional response team(s); rule total: {required}."


def rule_urban(facts):
    if (facts["community"]["area_type"] == "urban"
            and facts["weather"]["expected_flooding"]):
        return "Coordinate evacuation support by urban neighborhood."


RULES = (rule_storm, rule_flood, rule_shelter, rule_teams, rule_urban)


# Task 2B: a single-pass inference engine checks every rule and collects all actions.
def infer(facts):
    working_memory = deepcopy(facts)
    return [(rule.__name__, rule(working_memory)) for rule in RULES]


# Task 3A: four invented cases, each with problem features and a solution.
def seed_cases():
    examples = [
        ("TYPHOON-01", make_facts("typhoon", 4, 1000, 600, 4), 800, 6),
        ("TYPHOON-02", make_facts("typhoon", 5, 2000, 1000, 8), 1600, 10),
        ("FLOOD-01", make_facts("flood", 4, 1500, 900, 5), 1200, 8),
        ("QUAKE-01", make_facts("earthquake", 4, 800, 400, 5,
                                flooding=False), 600, 7),
    ]
    return [{"id": name, "problem": problem, "solution": {
        "shelter_places": shelters, "response_teams": teams,
        "strategy": "Review accessible evacuation routes and shelter registration.",
    }, "outcome": "Synthetic classroom review; not a real disaster outcome."}
        for name, problem, shelters, teams in examples]


# Weights sum to 1. Numeric comparisons are normalized before weighting.
WEIGHTS = {"hazard": .20, "severity": .20, "expected_flooding": .10,
           "area_type": .10, "affected_people": .15, "road_access": .10,
           "shelter_places": .10, "response_teams": .05}


def similarity(new, stored):
    left = {key: value for group in new.values() for key, value in group.items()}
    right = {key: value for group in stored.values() for key, value in group.items()}
    score = 0.0
    for feature, weight in WEIGHTS.items():
        a, b = left[feature], right[feature]
        if feature == "severity":
            local = 1 - abs(a - b) / 4
        elif feature == "road_access":
            order = ("open", "restricted", "blocked")
            local = 1 - abs(order.index(a) - order.index(b)) / 2
        elif feature in ("affected_people", "shelter_places", "response_teams"):
            local = 1 - abs(a - b) / max(a, b, 1)
        else:
            local = float(a == b)
        score += weight * local
    return score


# Retrieve: compare only the same primary hazard and rank by similarity.
def retrieve(facts, cases):
    matches = [(similarity(facts, case["problem"]), case) for case in cases
               if case["problem"]["weather"]["hazard"] == facts["weather"]["hazard"]]
    return sorted(matches, key=lambda item: (-item[0], item[1]["id"]))


# Task 3C: reuse the closest solution, then adapt its resource counts.
def reuse(facts, case):
    if (facts["weather"]["hazard"] != case["problem"]["weather"]["hazard"]
            or similarity(facts, case["problem"]) < .65):
        raise ValueError("Reuse requires the same hazard and at least 65% similarity.")
    solution = deepcopy(case["solution"])
    old = case["problem"]
    scale = Fraction(facts["community"]["affected_people"],
                     old["community"]["affected_people"])
    difference = facts["weather"]["severity"] - old["weather"]["severity"]
    scale *= Fraction(100 + 15 * difference, 100)
    solution["shelter_places"] = min(facts["community"]["affected_people"],
                                    ceil(solution["shelter_places"] * scale))
    solution["response_teams"] = max(1, ceil(solution["response_teams"] * scale))
    if facts["weather"]["expected_flooding"]:
        area = facts["community"]["area_type"]
        solution["strategy"] = f"Review early {area} evacuation and accessible transport."
    return solution


# Task 3D: blank manual input keeps the proposed value unchanged.
def revise(solution, interactive=False):
    reviewed = deepcopy(solution)
    if interactive:
        for key in ("shelter_places", "response_teams"):
            value = input(f"Reviewed {key} [{reviewed[key]}]: ").strip()
            if value:
                reviewed[key] = int(value)
        value = input(f"Reviewed strategy [{reviewed['strategy']}]: ").strip()
        if value:
            reviewed["strategy"] = value
    else:
        # Explicit worked review, not an inferred action.
        reviewed["response_teams"] += 1
    return reviewed


# Task 3E: retain reviewed experience; JSON makes interactive learning persistent.
def retain(facts, solution, outcome, cases, path):
    people = facts["community"]["affected_people"]
    if (type(solution["shelter_places"]) is not int
            or not 0 <= solution["shelter_places"] <= people
            or type(solution["response_teams"]) is not int
            or solution["response_teams"] < 1
            or not solution["strategy"].strip() or not outcome.strip()):
        raise ValueError("Check reviewed resource counts, strategy, and outcome note.")
    if any(case["problem"] == facts for case in cases):
        raise ValueError("This exact problem is stored; no duplicate was added.")
    learned = {"id": f"LEARNED-{len(cases) + 1:02d}", "problem": deepcopy(facts),
               "solution": deepcopy(solution), "outcome": outcome}
    updated = [*cases, learned]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    cases.append(learned)
    return learned


def run(part, interactive, path):
    facts = deepcopy(FACTS)
    print("TA4 DISASTER PLANNING EXERCISE - illustrative data only")
    print("INPUT - 8 facts in 3 categories")
    for category, values in facts.items():
        print(f"  {category}: {values}")
    if part in ("all", "rbr"):
        print("\nRBR PROCESS - evaluate all 5 IF-THEN rules")
        checked = infer(facts)
        for name, action in checked:
            print(f"  {name}: {'FIRED' if action else 'not applicable'}")
        print("RBR OUTPUT - Rule-Based Reasoning Actions:")
        for _, action in checked:
            if action:
                print("- " + action)
    if part in ("all", "cbr"):
        cases = (json.loads(path.read_text(encoding="utf-8"))
                 if path.exists() else seed_cases())
        print(f"\nCBR RETRIEVE - {len(cases)} stored cases; same-hazard filter")
        matches = retrieve(facts, cases)
        for score, case in matches:
            print(f"  {case['id']}: {score:.1%}")
        if not matches or matches[0][0] < .65:
            print("No suitable case for automatic reuse.")
            return
        best = matches[0][1]
        proposal = reuse(facts, best)
        people = facts["community"]["affected_people"]
        print(f"CBR REUSE - adapt {best['id']} to {people:,} affected people")
        print(f"  Shelter places: {proposal['shelter_places']}; "
              f"teams: {proposal['response_teams']}")
        print("  Evacuation: " + proposal["strategy"])
        reviewed = revise(proposal, interactive)
        print(f"CBR REVISE - response teams {proposal['response_teams']} "
              f"-> {reviewed['response_teams']}")
        print(f"  Reviewed shelter places: {reviewed['shelter_places']}")
        note = (input("Outcome or review note: ").strip() if interactive
                else "Classroom review: kept the shelter estimate "
                     "and added one coordination team.")
        if interactive and input("Retain this reviewed case? [y/N]: ").lower() != "y":
            print("Case was not retained.")
            return
        before = len(cases)
        learned = retain(facts, reviewed, note, cases, path)
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        nearest = retrieve(facts, reloaded)[0]
        print(f"CBR RETAIN - saved {learned['id']}; "
              f"case count {before} -> {len(reloaded)}")
        print(f"  Same query after reload: {nearest[1]['id']} at {nearest[0]:.1%}")
        print(f"  Stored review: {nearest[1]['outcome']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=("all", "rbr", "cbr"), default="all")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--data-file", type=Path,
                        default=Path(__file__).with_name("cases.json"))
    args = parser.parse_args()
    try:
        if args.interactive:
            run(args.part, True, args.data_file)
        else:
            with tempfile.TemporaryDirectory(prefix="ta4-demo-") as directory:
                run(args.part, False, Path(directory) / "cases.json")
            print("\nDemo used a temporary library; "
                  "persistent saved cases were unchanged.")
    except (ValueError, OSError, EOFError, KeyboardInterrupt) as error:
        print(f"Stopped: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
