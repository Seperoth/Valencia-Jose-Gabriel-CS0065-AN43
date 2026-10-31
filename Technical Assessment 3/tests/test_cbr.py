from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from cbr import CaseStore, Problem, WEIGHTS, adapt, assess, ratio_similarity, retrieve, revise

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_cases.json"


class CBRTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "cases.json"
        self.store = CaseStore(self.path, SEED)
        self.cases = self.store.load()
        self.base = next(case for case in self.cases if case.id == "FLOOD-002")
        self.query = Problem("flood", 5, 1200, "restricted", "urban", 700, 5)

    def test_seed_has_nine_distinct_valid_cases(self):
        self.assertEqual(len(self.cases), 9)
        self.assertEqual(len({case.id for case in self.cases}), 9)
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)

    def test_identical_problem_has_perfect_similarity(self):
        scores = assess(self.base.problem, self.base.problem)
        self.assertTrue(all(feature.similarity == 1 for feature in scores))
        self.assertAlmostEqual(sum(feature.contribution for feature in scores), 1.0)

    def test_numeric_similarity_handles_zero_and_different_scales(self):
        self.assertEqual(ratio_similarity(0, 0), 1.0)
        self.assertEqual(ratio_similarity(0, 10), 0.0)
        self.assertAlmostEqual(ratio_similarity(1000, 1200), 5 / 6)

    def test_ordinal_and_categorical_measures(self):
        query = replace(self.base.problem, severity=2, road_access="blocked", area_type="rural")
        scores = {item.feature: item.similarity for item in assess(query, self.base.problem)}
        self.assertEqual(scores["severity"], 0.5)
        self.assertEqual(scores["road_access"], 0.5)
        self.assertEqual(scores["area_type"], 0.0)

    def test_demo_ranking_and_exact_weighted_score(self):
        matches = retrieve(self.query, self.cases)
        self.assertEqual(matches[0].case.id, "FLOOD-002")
        self.assertAlmostEqual(matches[0].score, 0.9007142857142857)
        self.assertEqual([match.case.id for match in matches], ["FLOOD-002", "FLOOD-003", "FLOOD-001"])

    def test_retrieval_filters_disaster_type_and_unreviewed_cases(self):
        unreviewed = replace(self.base, id="UNREVIEWED", problem=self.query, reviewed=False)
        matches = retrieve(self.query, [*self.cases, unreviewed])
        self.assertTrue(all(match.case.problem.disaster_type == "flood" for match in matches))
        self.assertNotIn("UNREVIEWED", [match.case.id for match in matches])

    def test_missing_case_type_returns_no_match(self):
        self.assertEqual(retrieve(replace(self.query, disaster_type="landslide"), self.cases), [])

    def test_similarity_is_symmetric_and_bounded(self):
        for case in self.cases:
            left = sum(item.contribution for item in assess(self.query, case.problem))
            right = sum(item.contribution for item in assess(case.problem, self.query))
            self.assertAlmostEqual(left, right)
            self.assertGreaterEqual(left, 0)
            self.assertLessEqual(left, 1)

    def test_adaptation_scales_resources_and_computes_shortfalls(self):
        result = adapt(self.query, self.base)
        self.assertEqual(result.solution.shelter_places, 1104)
        self.assertEqual(result.solution.response_teams, 9)
        self.assertEqual(result.shelter_shortfall, 404)
        self.assertEqual(result.team_shortfall, 4)
        self.assertEqual(result.solution.priority, "critical")

    def test_adaptation_caps_shelter_places_and_nonnegative_gaps(self):
        base = replace(self.base, solution=replace(self.base.solution, shelter_places=1000))
        query = replace(self.query, available_shelter_places=2000, available_response_teams=20)
        result = adapt(query, base)
        self.assertLessEqual(result.solution.shelter_places, query.affected_people)
        self.assertEqual(result.shelter_shortfall, 0)
        self.assertEqual(result.team_shortfall, 0)

    def test_newly_blocked_access_adds_one_coordination_team(self):
        result = adapt(replace(self.query, road_access="blocked"), self.base)
        self.assertEqual(result.solution.response_teams, 10)
        self.assertTrue(any("blocked" in action for action in result.solution.actions))

    def test_identical_problem_preserves_the_reviewed_priority(self):
        reviewed = replace(self.base, solution=replace(self.base.solution, priority="high"))
        result = adapt(reviewed.problem, reviewed)
        self.assertEqual(result.solution.priority, "high")
        self.assertEqual(result.solution.response_teams, reviewed.solution.response_teams)

    def test_unsafe_analogies_and_weak_matches_are_rejected(self):
        with self.assertRaises(ValueError):
            adapt(replace(self.query, disaster_type="earthquake"), self.base)
        weak = Problem("flood", 1, 1, "blocked", "mountainous", 0, 0)
        with self.assertRaises(ValueError):
            adapt(weak, self.base)

    def test_learning_survives_reload_and_changes_future_retrieval(self):
        seed_before = SEED.read_bytes()
        result = adapt(self.query, self.base)
        corrected = revise(result.solution, 1104, 10)
        learned = self.store.retain(self.query, corrected, "Classroom review accepted.", reviewed=True, adapted_from=self.base.id)
        reopened = CaseStore(self.path, SEED)
        self.assertEqual(len(reopened.load()), 10)
        nearest = retrieve(self.query, reopened.load())[0]
        self.assertEqual(nearest.case.id, learned.id)
        self.assertEqual(nearest.case.solution.response_teams, 10)
        self.assertAlmostEqual(nearest.score, 1.0)
        self.assertEqual(SEED.read_bytes(), seed_before)

    def test_review_and_duplicate_guards_preserve_library(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.retain(self.query, self.base.solution, "Not reviewed.", reviewed=False)
        with self.assertRaises(ValueError):
            self.store.retain(self.base.problem, self.base.solution, "Duplicate.", reviewed=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_inputs_do_not_reach_reasoning(self):
        for changes in ({"severity": 6}, {"affected_people": 0}, {"available_response_teams": -1}, {"severity": True}, {"road_access": "unknown"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.query, **changes)

    def test_corrupt_json_is_not_silently_replaced_by_seed(self):
        self.path.write_text("broken json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not overwritten"):
            self.store.load()
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken json")

    def test_failed_atomic_write_keeps_previous_library(self):
        before = self.path.read_bytes()
        with patch("cbr.os.replace", side_effect=OSError("Simulated write failure")):
            with self.assertRaises(OSError):
                self.store.retain(self.query, self.base.solution, "Reviewed.", reviewed=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_interactive_query_revision_and_retention(self):
        answers = "\n".join([
            "1", "1", "5", "1200", "2", "1", "700", "5", "", "y",
            "", "", "10", "n", "Reviewed in the classroom.", "y", "5", "",
        ])
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--cli", "--data-file", str(self.path)],
            input=answers, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Library now contains 10 cases", result.stdout)
        self.assertIn("100.0% similarity", result.stdout)
        self.assertEqual(len(json.loads(self.path.read_text(encoding="utf-8"))["cases"]), 10)

    def test_demo_is_noninteractive_and_does_not_write_default_library(self):
        runtime = ROOT / "data" / "cases.json"
        before = runtime.read_bytes() if runtime.exists() else None
        result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--demo"], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        for stage in ("CASE REPRESENTATION", "RETRIEVE", "REUSE / ADAPT", "REVISE", "RETAIN"):
            self.assertIn(stage, result.stdout)
        self.assertIn("Similarity after learning: 100.0%", result.stdout)
        self.assertEqual(runtime.read_bytes() if runtime.exists() else None, before)


if __name__ == "__main__":
    unittest.main()
