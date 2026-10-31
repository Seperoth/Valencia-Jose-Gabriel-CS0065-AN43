"""Local browser dashboard for the CBR engine; Python standard library only."""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from cbr import (
    AREA_TYPES, DISASTER_TYPES, MIN_SIMILARITY, PRIORITIES, ROAD_ACCESS,
    CaseStore, Problem, Solution, adapt, retrieve,
)

ROOT = Path(__file__).resolve().parent


def create_server(data_file: Path, port: int = 0) -> ThreadingHTTPServer:
    store = CaseStore(data_file, ROOT / "data" / "seed_cases.json")
    store.load()  # Report a corrupt library before opening the browser.
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def respond(self, status, payload, content_type="application/json; charset=utf-8"):
            body = json.dumps(payload).encode("utf-8") if content_type.startswith("application/json") else payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.allowed_host():
                self.respond(403, {"error": "Open the dashboard using its 127.0.0.1 address."})
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/state":
                    with lock:
                        cases = store.load()
                    self.respond(200, {
                        "cases": [asdict(case) for case in cases],
                        "options": {"disaster_type": DISASTER_TYPES, "area_type": AREA_TYPES,
                                    "road_access": ROAD_ACCESS, "priority": PRIORITIES},
                        "min_similarity": MIN_SIMILARITY,
                    })
                elif path in ("/", "/app.js", "/style.css"):
                    name, content_type = {
                        "/": ("index.html", "text/html; charset=utf-8"),
                        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                        "/style.css": ("style.css", "text/css; charset=utf-8"),
                    }[path]
                    self.respond(200, (ROOT / "web" / name).read_bytes(), content_type)
                else:
                    self.respond(404, {"error": "Page not found."})
            except (OSError, ValueError) as error:
                self.respond(500, {"error": str(error)})

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.allowed_host() or self.headers.get("X-CBR-Request") != "dashboard" or (origin and origin != expected_origin):
                self.respond(403, {"error": "This request must come from the local dashboard."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32_768:
                    raise ValueError("Request must contain between 1 and 32,768 bytes.")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object.")
                path = urlsplit(self.path).path
                if path == "/api/shutdown":
                    self.respond(200, {"stopped": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                with lock:
                    problem = Problem(**payload["problem"])
                    cases = store.load()
                    if path == "/api/analyze":
                        matches = retrieve(problem, cases)
                        result = {
                            "matches": [{**asdict(match), "features": [
                                {**asdict(feature), "contribution": feature.contribution}
                                for feature in match.features
                            ]} for match in matches],
                            "duplicate": next((case.id for case in cases if case.problem == problem), None),
                        }
                    elif path == "/api/adapt":
                        source = next((case for case in cases if case.id == payload.get("case_id")), None)
                        if source is None:
                            raise ValueError("Choose a case from this library.")
                        result = asdict(adapt(problem, source))
                    elif path == "/api/retain":
                        solution = Solution(**payload["solution"])
                        outcome = payload["outcome"]
                        if not isinstance(outcome, str) or len(outcome) > 1000:
                            raise ValueError("Review note must be at most 1,000 characters.")
                        origin_id = payload.get("adapted_from")
                        if origin_id is not None:
                            source = next((case for case in cases if case.id == origin_id), None)
                            if source is None:
                                raise ValueError("The source case no longer exists.")
                            adapt(problem, source)  # Preserve the engine's eligibility guards.
                        result = asdict(store.retain(
                            problem, solution, outcome, reviewed=payload.get("reviewed"),
                            adapted_from=origin_id,
                        ))
                    else:
                        self.respond(404, {"error": "Unknown action."})
                        return
                self.respond(200, result)
            except (ValueError, TypeError, KeyError, UnicodeError) as error:
                self.respond(400, {"error": str(error)})
            except OSError as error:
                self.respond(500, {"error": f"Could not access the case library: {error}"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def run_dashboard(data_file: Path = ROOT / "data" / "cases.json", port: int = 0, open_browser: bool = True) -> int:
    try:
        server = create_server(data_file, port)
    except (OSError, ValueError) as error:
        print(f"Could not start the dashboard: {error}")
        return 1
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Disaster DSS dashboard: {url}\nKeep this process running. Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", type=Path, default=ROOT / "data" / "cases.json")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run_dashboard(args.data_file, args.port, not args.no_browser))
