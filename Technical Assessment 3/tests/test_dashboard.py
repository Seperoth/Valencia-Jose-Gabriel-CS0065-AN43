from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from dataclasses import asdict
from pathlib import Path

from cbr import CaseStore, Problem, retrieve
from dashboard import create_server


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "cases.json"
        self.server = create_server(self.path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.problem = asdict(Problem("flood", 5, 1200, "restricted", "urban", 700, 5))

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def request(self, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = {"Content-Type": "application/json", "X-CBR-Request": "dashboard"}
        request_headers.update(headers or {})
        connection.request("GET" if payload is None else "POST", path,
                           None if payload is None else json.dumps(payload), request_headers)
        response = connection.getresponse()
        body = response.read()
        status, content_type = response.status, response.getheader("Content-Type")
        connection.close()
        return status, json.loads(body) if content_type.startswith("application/json") else body

    def test_dashboard_assets_and_initial_state(self):
        for path in ("/", "/app.js", "/style.css"):
            status, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertGreater(len(body), 100)
        status, state = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(len(state["cases"]), 9)
        self.assertEqual(state["min_similarity"], .65)
        self.assertEqual(self.request("/../cbr.py")[0], 404)

    def test_full_cycle_retains_review_and_retrieves_it_after_restart(self):
        status, result = self.request("/api/analyze", {"problem": self.problem})
        self.assertEqual(status, 200)
        self.assertEqual(result["matches"][0]["case"]["id"], "FLOOD-002")
        self.assertAlmostEqual(sum(f["contribution"] for f in result["matches"][0]["features"]), result["matches"][0]["score"])
        status, proposal = self.request("/api/adapt", {"problem": self.problem, "case_id": "FLOOD-002"})
        self.assertEqual(status, 200)
        self.assertEqual(proposal["shelter_shortfall"], 404)
        self.assertEqual(proposal["solution"]["response_teams"], 9)
        proposal["solution"]["response_teams"] = 10
        payload = {"problem": self.problem, "solution": proposal["solution"], "outcome": "Classroom review.", "reviewed": True, "adapted_from": "FLOOD-002"}
        status, saved = self.request("/api/retain", payload)
        self.assertEqual(status, 200)
        self.assertEqual(saved["solution"]["response_teams"], 10)
        self.assertEqual(self.request("/api/retain", payload)[0], 400)
        reopened = create_server(self.path)
        try:
            cases = CaseStore(self.path, self.path).load()
            match = retrieve(Problem(**self.problem), cases)[0]
            self.assertEqual(match.case.id, saved["id"])
            self.assertAlmostEqual(match.score, 1)
        finally:
            reopened.server_close()
        result = self.request("/api/analyze", {"problem": self.problem})[1]
        self.assertEqual(result["duplicate"], saved["id"])

    def test_no_history_allows_manual_reviewed_case(self):
        problem = {**self.problem, "disaster_type": "landslide"}
        self.assertEqual(self.request("/api/analyze", {"problem": problem})[1]["matches"], [])
        payload = {"problem": problem, "solution": {"priority": "high", "shelter_places": 500, "response_teams": 5, "actions": ["Review the exercise plan."]}, "outcome": "Reviewed exercise.", "reviewed": False}
        self.assertEqual(self.request("/api/retain", payload)[0], 400)
        payload["reviewed"] = True
        self.assertEqual(self.request("/api/retain", payload)[0], 200)

    def test_invalid_inputs_and_weak_or_cross_disaster_reuse_are_rejected(self):
        self.assertEqual(self.request("/api/analyze", {"problem": {**self.problem, "severity": 6}})[0], 400)
        self.assertEqual(self.request("/api/analyze", [1, 2])[0], 400)
        self.assertEqual(self.request("/api/analyze", {})[0], 400)
        weak = asdict(Problem("flood", 1, 1, "blocked", "mountainous", 0, 0))
        self.assertEqual(self.request("/api/adapt", {"problem": weak, "case_id": "FLOOD-002"})[0], 400)
        self.assertEqual(self.request("/api/adapt", {"problem": self.problem, "case_id": "EARTHQUAKE-001"})[0], 400)
        self.assertEqual(self.request("/api/adapt", {"problem": self.problem, "case_id": "missing"})[0], 400)

    def test_foreign_origin_host_and_missing_request_header_are_rejected(self):
        payload = {"problem": self.problem}
        self.assertEqual(self.request("/api/analyze", payload, {"Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.request("/api/analyze", payload, {"X-CBR-Request": ""})[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Host": "example.com"})[0], 403)

    def test_corrupt_library_is_reported_without_replacement(self):
        self.path.write_text("broken json", encoding="utf-8")
        self.assertEqual(self.request("/api/state")[0], 500)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "broken json")

    def test_shutdown_stops_the_server(self):
        self.assertEqual(self.request("/api/shutdown", {})[0], 200)
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
