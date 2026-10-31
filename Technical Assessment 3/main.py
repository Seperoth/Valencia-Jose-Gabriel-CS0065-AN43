"""Open the dashboard with python main.py; use --cli for the console."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from cbr import (
    AREA_TYPES, DISASTER_TYPES, MIN_SIMILARITY, PRIORITIES, ROAD_ACCESS,
    Adaptation, Case, CaseStore, Match, Problem, Solution, adapt, retrieve, revise,
)

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "data" / "seed_cases.json"


class Cancelled(Exception):
    pass


def answer(prompt: str) -> str:
    value = input(prompt).strip()
    if value.lower() == ":back":
        raise Cancelled
    return value


def number(label: str, minimum: int, maximum: int, default: int | None = None) -> int:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = answer(f"{label}{suffix}: ")
        if not value and default is not None:
            return default
        try:
            result = int(value)
            if minimum <= result <= maximum:
                return result
        except ValueError:
            pass
        print(f"Enter a whole number from {minimum:,} to {maximum:,}.")


def choice(label: str, options: tuple[str, ...], default: str | None = None) -> str:
    print(f"\n{label}: " + " | ".join(f"{i}. {item}" for i, item in enumerate(options, 1)))
    selected = number("Choose", 1, len(options), options.index(default) + 1 if default else None)
    return options[selected - 1]


def text(label: str, default: str | None = None) -> str:
    while True:
        value = answer(f"{label}" + (f" [{default}]" if default else "") + ": ")
        if not value and default:
            return default
        if value and len(value) <= 1000:
            return value
        print("Enter between 1 and 1,000 characters.")


def confirm(label: str) -> bool:
    while True:
        value = answer(label + " [y/N]: ").lower()
        if value in ("y", "yes"):
            return True
        if value in ("", "n", "no"):
            return False
        print("Enter y or n.")


def read_problem() -> Problem:
    print("\n1. CASE REPRESENTATION - describe a new classroom scenario")
    print("Severity is an exercise rating from 1 to 5, not an official warning level.")
    print("Enter :back at any prompt to return to the menu.")
    return Problem(
        disaster_type=choice("Disaster type", DISASTER_TYPES),
        severity=number("Severity (1 = low, 5 = very high)", 1, 5),
        affected_people=number("Affected people", 1, 1_000_000),
        road_access=choice("Road access", ROAD_ACCESS),
        area_type=choice("Area type", AREA_TYPES),
        available_shelter_places=number("Available shelter places (people)", 0, 1_000_000),
        available_response_teams=number("Available response teams", 0, 100_000),
    )


def show_matches(matches: list[Match]) -> None:
    print("\n2. RETRIEVE - reviewed cases with the same disaster type")
    print(f"{'No.':<5}{'Case':<20}{'Similarity':>12}{'Severity':>11}{'People':>12}")
    for i, match in enumerate(matches, 1):
        print(f"{i:<5}{match.case.id:<20}{match.score:>11.1%}{match.case.problem.severity:>11}{match.case.problem.affected_people:>12,}")
    print("Similarity measures feature resemblance; it is not probability of success.")


def show_reasoning(match: Match, query: Problem) -> None:
    print(f"\nWhy {match.case.id} matched:")
    print(f"{'Feature':<28}{'New':<14}{'Stored':<14}{'Weight':>8}{'Local':>9}{'Contribution':>15}")
    for feature in match.features:
        left = str(getattr(query, feature.feature))
        right = str(getattr(match.case.problem, feature.feature))
        print(f"{feature.feature:<28}{left:<14}{right:<14}{feature.weight:>8.0%}{feature.similarity:>9.1%}{feature.contribution:>15.2%}")
    print(f"Weighted sum = {match.score:.4f} ({match.score:.1%}).")


def show_plan(problem: Problem, plan: Solution, explanation: tuple[str, ...] = ()) -> None:
    print(f"\nIllustrative planning priority: {plan.priority.upper()}")
    print(f"Proposed total shelter places: {plan.shelter_places:,}")
    print(f"Additional shelter places needed: {max(0, plan.shelter_places - problem.available_shelter_places):,}")
    print(f"Proposed total response teams: {plan.response_teams:,}")
    print(f"Additional teams needed: {max(0, plan.response_teams - problem.available_response_teams):,}")
    for line in explanation:
        print("  Reason: " + line)
    for action in plan.actions:
        print("  Review: " + action)


def reviewed_solution(problem: Problem, proposed: Solution | None = None) -> Solution:
    print("\n4. REVISE - enter your classroom review of the proposed solution")
    if proposed:
        print("Press Enter to keep a proposed value.")
    priority = choice("Planning priority", PRIORITIES, proposed.priority if proposed else None)
    shelters = number("Proposed shelter places", 0, problem.affected_people, proposed.shelter_places if proposed else None)
    teams = number("Proposed response teams", 1, 100_000, proposed.response_teams if proposed else None)
    if proposed:
        actions = proposed.actions
        if confirm("Replace the proposed review actions?"):
            actions = read_actions()
    else:
        actions = read_actions()
    return Solution(priority, shelters, teams, actions)


def read_actions() -> tuple[str, ...]:
    while True:
        value = text("Review actions, separated by semicolons")
        actions = tuple(item.strip() for item in value.split(";") if item.strip())
        if 1 <= len(actions) <= 10 and all(len(item) <= 300 for item in actions):
            return actions
        print("Provide 1 to 10 actions, each at most 300 characters.")


def retain_review(store: CaseStore, problem: Problem, proposed: Solution | None, origin: str | None) -> None:
    solution = reviewed_solution(problem, proposed)
    outcome = text("Observed outcome or classroom-review note")
    show_plan(problem, solution)
    if not confirm("Have you reviewed this solution and want to RETAIN it?"):
        print("Not retained. The library was unchanged.")
        return
    case = store.retain(problem, solution, outcome, reviewed=True, adapted_from=origin)
    print(f"\n5. RETAIN - saved {case.id}. Library now contains {len(store.load())} cases.")
    nearest = retrieve(problem, store.load())[0]
    print(f"Retrieving the same problem now returns {nearest.case.id} at {nearest.score:.1%} similarity.")


def solve(store: CaseStore) -> None:
    problem = read_problem()
    matches = retrieve(problem, store.load())
    if not matches:
        print("No reviewed case for this disaster type. Use menu 3 to add one manually.")
        return
    show_matches(matches)
    if matches[0].score < MIN_SIMILARITY:
        print("All matches are below 65%. No automatic adaptation; add a reviewed case manually.")
        return
    selected = number("Choose a case to adapt (0 = cancel)", 0, len(matches), 1)
    if not selected:
        return
    match = matches[selected - 1]
    show_reasoning(match, problem)
    proposed: Adaptation = adapt(problem, match.case)
    print("\n3. REUSE / ADAPT - apply the selected case to the new problem")
    show_plan(problem, proposed.solution, proposed.explanation)
    if any(case.problem == problem for case in store.load()):
        print("This exact problem is already in the library; no duplicate will be added.")
    elif confirm("Revise this proposal and consider retaining a new case?"):
        retain_review(store, problem, proposed.solution, match.case.id)


def browse(store: CaseStore) -> None:
    cases = store.load()
    print(f"\nCASE LIBRARY - {len(cases)} cases")
    for i, case in enumerate(cases, 1):
        p = case.problem
        print(f"{i:>2}. {case.id:<20} {p.disaster_type:<12} severity {p.severity} | {p.affected_people:,} people | {case.source}")
    if cases:
        index = number("Inspect case (0 = menu)", 0, len(cases), 0)
        if index:
            print(json.dumps(asdict(cases[index - 1]), indent=2))


def demo() -> None:
    """Demonstrate every stage using a temporary, genuinely written case file."""
    print("\nWORKED EXAMPLE - synthetic flood scenario; temporary case library")
    with tempfile.TemporaryDirectory(prefix="disaster-cbr-demo-") as directory:
        store = CaseStore(Path(directory) / "cases.json", SEED)
        before = len(store.load())
        query = Problem("flood", 5, 1200, "restricted", "urban", 700, 5)
        print("\n1. CASE REPRESENTATION")
        print(json.dumps(asdict(query), indent=2))
        matches = retrieve(query, store.load())
        show_matches(matches)
        best = matches[0]
        show_reasoning(best, query)
        result = adapt(query, best.case)
        print("\n3. REUSE / ADAPT")
        show_plan(query, result.solution, result.explanation)
        print("\n4. REVISE - example reviewer adds one coordination team.")
        corrected = revise(result.solution, result.solution.shelter_places, result.solution.response_teams + 1)
        print(f"Reviewed response teams: {result.solution.response_teams} -> {corrected.response_teams}.")
        learned = store.retain(
            query, corrected,
            "Synthetic classroom review: accepted shelter estimate and added one coordination team.",
            reviewed=True, adapted_from=best.case.id,
        )
        print(f"\n5. RETAIN - wrote {learned.id} to the temporary JSON file.")
        reloaded = store.load()
        nearest = retrieve(query, reloaded)[0]
        print(f"Case count: {before} -> {len(reloaded)}.")
        print(f"New query retrieves learned case: {nearest.case.id == learned.id}.")
        print(f"Similarity after learning: {nearest.score:.1%}.")
        print(f"Learned solution: {nearest.case.solution.response_teams} reviewed response teams.")
    print("Demo complete. Your saved library was not changed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Disaster DSS: a classroom Case-Based Reasoning program.")
    parser.add_argument("--demo", action="store_true", help="Run all CBR stages without changing saved cases.")
    parser.add_argument("--cli", action="store_true", help="Use the original terminal interface instead of the dashboard.")
    parser.add_argument("--port", type=int, default=0, help="Dashboard port (default: choose a free port).")
    parser.add_argument("--no-browser", action="store_true", help="Start the dashboard without opening a browser.")
    parser.add_argument("--data-file", type=Path, default=ROOT / "data" / "cases.json", help="JSON library for the dashboard or terminal interface.")
    args = parser.parse_args()
    if not args.cli and not args.demo:
        from dashboard import run_dashboard
        return run_dashboard(args.data_file, args.port, not args.no_browser)
    print("DISASTER DSS | Case-Based Reasoning")
    print("Synthetic classroom examples only. Not for real emergency decisions.")
    try:
        if args.demo:
            demo()
            return 0
        store = CaseStore(args.data_file, SEED)
        print(f"Saved library: {store.path}")
        store.load()
        while True:
            print("\n1. Analyze a new scenario\n2. Inspect stored cases\n3. Add a reviewed case manually\n4. Run the worked example\n5. Exit")
            try:
                selected = number("Menu", 1, 5)
                if selected == 1:
                    solve(store)
                elif selected == 2:
                    browse(store)
                elif selected == 3:
                    retain_review(store, read_problem(), None, None)
                elif selected == 4:
                    demo()
                else:
                    return 0
            except Cancelled:
                print("Cancelled. No unfinished case was retained.")
            except ValueError as error:
                print(f"Could not complete the operation: {error}")
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye. No unfinished case was retained.")
        return 0
    except (OSError, ValueError) as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
