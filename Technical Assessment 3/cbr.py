"""Explainable Case-Based Reasoning for synthetic disaster-planning exercises.

No third-party packages are required. All resource rules are classroom
assumptions, not validated emergency-management recommendations.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from fractions import Fraction
from math import ceil
from pathlib import Path
from uuid import uuid4


DISASTER_TYPES = ("flood", "typhoon", "earthquake", "landslide")
AREA_TYPES = ("urban", "rural", "coastal", "mountainous")
ROAD_ACCESS = ("open", "restricted", "blocked")
PRIORITIES = ("routine", "high", "critical")
MIN_SIMILARITY = 0.65

# Total = 1.0. These weights are chosen for this exercise, not learned from data.
WEIGHTS = {
    "disaster_type": 0.25,
    "severity": 0.20,
    "affected_people": 0.15,
    "road_access": 0.15,
    "area_type": 0.10,
    "available_shelter_places": 0.10,
    "available_response_teams": 0.05,
}


def integer(value: int, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}.")


@dataclass(frozen=True)
class Problem:
    """Knowledge representation: categorical, ordinal, and numerical features."""

    disaster_type: str
    severity: int
    affected_people: int
    road_access: str
    area_type: str
    available_shelter_places: int
    available_response_teams: int

    def __post_init__(self) -> None:
        for name, choices in (
            ("disaster_type", DISASTER_TYPES),
            ("road_access", ROAD_ACCESS),
            ("area_type", AREA_TYPES),
        ):
            if getattr(self, name) not in choices:
                raise ValueError(f"{name} must be one of: {', '.join(choices)}.")
        integer(self.severity, "Severity", 1, 5)
        integer(self.affected_people, "Affected people", 1, 1_000_000)
        integer(self.available_shelter_places, "Shelter places", 0, 1_000_000)
        integer(self.available_response_teams, "Response teams", 0, 100_000)


@dataclass(frozen=True)
class Solution:
    priority: str
    shelter_places: int
    response_teams: int
    actions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.priority not in PRIORITIES:
            raise ValueError(f"Priority must be one of: {', '.join(PRIORITIES)}.")
        integer(self.shelter_places, "Proposed shelter places", 0, 1_000_000)
        integer(self.response_teams, "Proposed response teams", 1, 100_000)
        if not isinstance(self.actions, (tuple, list)) or not 1 <= len(self.actions) <= 10:
            raise ValueError("Provide between 1 and 10 review actions.")
        if any(not isinstance(a, str) or not a.strip() or len(a) > 300 for a in self.actions):
            raise ValueError("Each review action must contain 1 to 300 characters.")
        object.__setattr__(self, "actions", tuple(a.strip() for a in self.actions))


@dataclass(frozen=True)
class Case:
    id: str
    problem: Problem
    solution: Solution
    outcome: str
    reviewed: bool
    source: str
    created_at: str
    adapted_from: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("A case needs an ID.")
        if type(self.reviewed) is not bool:
            raise ValueError("reviewed must be true or false.")
        if not isinstance(self.outcome, str) or not self.outcome.strip():
            raise ValueError("A case needs a recorded outcome or classroom review.")
        if self.solution.shelter_places > self.problem.affected_people:
            raise ValueError("Proposed shelter places cannot exceed affected people.")
        if self.source not in ("synthetic", "classroom_review"):
            raise ValueError("Case source must be synthetic or classroom_review.")

    @classmethod
    def from_dict(cls, data: dict) -> Case:
        return cls(
            **{
                **data,
                "problem": Problem(**data["problem"]),
                "solution": Solution(**data["solution"]),
            }
        )


@dataclass(frozen=True)
class FeatureScore:
    feature: str
    weight: float
    similarity: float

    @property
    def contribution(self) -> float:
        return self.weight * self.similarity


@dataclass(frozen=True)
class Match:
    case: Case
    score: float
    features: tuple[FeatureScore, ...]


@dataclass(frozen=True)
class Adaptation:
    solution: Solution
    shelter_shortfall: int
    team_shortfall: int
    explanation: tuple[str, ...]


def ratio_similarity(left: int, right: int) -> float:
    """Relative numerical similarity; handles two zero values without division."""
    return 1.0 - abs(left - right) / max(left, right, 1)


def assess(query: Problem, previous: Problem) -> tuple[FeatureScore, ...]:
    """Local measures are bounded in [0, 1]; their weighted sum is the score."""
    scores = []
    for feature, weight in WEIGHTS.items():
        left, right = getattr(query, feature), getattr(previous, feature)
        if feature == "severity":
            local = 1.0 - abs(left - right) / 4
        elif feature == "road_access":
            local = 1.0 - abs(ROAD_ACCESS.index(left) - ROAD_ACCESS.index(right)) / 2
        elif feature in ("affected_people", "available_shelter_places", "available_response_teams"):
            local = ratio_similarity(left, right)
        else:
            local = float(left == right)
        scores.append(FeatureScore(feature, weight, local))
    return tuple(scores)


def retrieve(query: Problem, cases: list[Case], top_k: int = 3) -> list[Match]:
    """Retrieve: filter by hazard and review status, then rank transparently."""
    integer(top_k, "top_k", 1, 100)
    matches = []
    for case in cases:
        if not case.reviewed or case.problem.disaster_type != query.disaster_type:
            continue
        features = assess(query, case.problem)
        matches.append(Match(case, sum(f.contribution for f in features), features))
    return sorted(matches, key=lambda match: (-match.score, match.case.id))[:top_k]


def adapt(query: Problem, previous: Case) -> Adaptation:
    """Reuse/adapt using explicit classroom rules, rather than just copying."""
    if not previous.reviewed or query.disaster_type != previous.problem.disaster_type:
        raise ValueError("Adaptation needs a reviewed case of the same disaster type.")
    score = sum(f.contribution for f in assess(query, previous.problem))
    if score < MIN_SIMILARITY:
        raise ValueError("Similarity is below 65%; add a reviewed case instead of adapting.")

    # Fractions prevent floating-point rounding from adding an unintended unit.
    population_factor = Fraction(query.affected_people, previous.problem.affected_people)
    severity_factor = Fraction(100 + 15 * (query.severity - previous.problem.severity), 100)
    scale = population_factor * severity_factor
    shelter_places = min(query.affected_people, ceil(previous.solution.shelter_places * scale))
    response_teams = max(1, ceil(previous.solution.response_teams * scale))
    actions = list(previous.solution.actions)
    explanations = [
        f"Population factor: {query.affected_people}/{previous.problem.affected_people} = {float(population_factor):.2f}.",
        f"Severity factor: 1 + 0.15 x ({query.severity} - {previous.problem.severity}) = {float(severity_factor):.2f}.",
        "Scale prior resources by both factors, round up, and cap shelter places at affected people.",
    ]
    if query.road_access == "blocked" and previous.problem.road_access != "blocked":
        response_teams += 1
        actions.append("Review the blocked-access assumption with the coordination team.")
        explanations.append("Newly blocked access: add one illustrative coordination team.")
    if response_teams > 100_000:
        raise ValueError("Adaptation exceeds the exercise's team limit; enter a reviewed solution manually.")
    priority_index = PRIORITIES.index(previous.solution.priority)
    if query.severity > previous.problem.severity or (
        query.road_access == "blocked" and previous.problem.road_access != "blocked"
    ):
        priority_index = min(len(PRIORITIES) - 1, priority_index + 1)
    elif query.severity < previous.problem.severity and query.road_access != "blocked":
        priority_index = max(0, priority_index - 1)
    priority = PRIORITIES[priority_index]
    explanations.append(
        f"Start from the stored priority ({previous.solution.priority}); "
        "adjust one level for changed severity or newly blocked access."
    )
    solution = Solution(priority, shelter_places, response_teams, tuple(actions[:10]))
    return Adaptation(
        solution,
        max(0, shelter_places - query.available_shelter_places),
        max(0, response_teams - query.available_response_teams),
        tuple(explanations),
    )


class CaseStore:
    """Retain cases in a local JSON file; never overwrite a corrupt case base."""

    def __init__(self, path: Path, seed_path: Path):
        self.path, self.seed_path = Path(path), Path(seed_path)

    def load(self) -> list[Case]:
        if not self.path.exists():
            cases = self._read(self.seed_path)
            self._write(cases)
            return cases
        return self._read(self.path)

    @staticmethod
    def _read(path: Path) -> list[Case]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["schema_version"] != 1 or not isinstance(data["cases"], list):
                raise ValueError("Unsupported case-file structure.")
            cases = [Case.from_dict(item) for item in data["cases"]]
            if len({case.id for case in cases}) != len(cases):
                raise ValueError("Case IDs must be unique.")
            return cases
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"Cannot read {path.name}: {error} The file was not overwritten.") from error

    def _write(self, cases: list[Case]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"schema_version": 1, "cases": [asdict(case) for case in cases]}
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=self.path.name + ".", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(temp_path, self.path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    def retain(
        self, problem: Problem, solution: Solution, outcome: str, *,
        reviewed: bool, adapted_from: str | None = None,
    ) -> Case:
        if reviewed is not True:
            raise ValueError("Review the proposed solution before retaining it.")
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError("Record an outcome or classroom-review note before retaining.")
        cases = self.load()
        if any(case.problem == problem for case in cases):
            raise ValueError("This exact problem is already stored; no duplicate was added.")
        if adapted_from is not None and not any(case.id == adapted_from for case in cases):
            raise ValueError("The source case does not exist in this library.")
        case = Case(
            "LEARNED-" + uuid4().hex[:8].upper(), problem, solution,
            outcome.strip(), True, "classroom_review",
            datetime.now(timezone.utc).isoformat(), adapted_from,
        )
        self._write([*cases, case])
        return case


def revise(solution: Solution, shelter_places: int, response_teams: int) -> Solution:
    """Revise: retain unchanged evidence/actions while accepting reviewed counts."""
    return replace(solution, shelter_places=shelter_places, response_teams=response_teams)
