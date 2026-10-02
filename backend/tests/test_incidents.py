import json
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND = Path(__file__).resolve().parents[1]


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "incidents.db"
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        script = (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0, sys.argv[1]); import main; import uvicorn; "
            "main.DATABASE_PATH = Path(sys.argv[2]); "
            "uvicorn.run(main.app, host='127.0.0.1', port=int(sys.argv[3]), log_level='error')"
        )
        self.server = subprocess.Popen(
            [sys.executable, "-c", script, str(BACKEND), str(self.database), str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                if self.request("GET", "/health")[0] == 200:
                    return
            except (URLError, TimeoutError):
                pass
            if self.server.poll() is not None:
                self.fail("The server exited during startup")
            time.sleep(0.05)
        self.stop_server()
        self.fail("The server did not start")

    def stop_server(self):
        if self.server.poll() is None:
            self.server.terminate()
            self.server.wait(timeout=10)

    def request(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            self.base_url + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=2)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def payload(self, **changes):
        return dict(title="Suspicious login", description="Failed login attempts",
                    severity="high", status="open") | changes

    def test_creation_listing_lookup_and_health(self):
        self.assertEqual(self.request("GET", "/health"), (200, {"status": "ok"}))
        self.assertEqual(self.request("GET", "/incidents"), (200, []))
        payload = self.payload(title="O'Brien'); DROP TABLE incidents; --")
        status, incident = self.request("POST", "/incidents", payload)
        self.assertEqual(status, 201)
        self.assertGreater(incident["id"], 0)
        for key, value in payload.items():
            self.assertEqual(incident[key], value)
        date = datetime.fromisoformat(incident["created_at"].replace("Z", "+00:00"))
        self.assertEqual(date.utcoffset(), timedelta(0))
        self.assertEqual(self.request("GET", "/incidents"), (200, [incident]))
        self.assertEqual(self.request("GET", f'/incidents/{incident["id"]}'), (200, incident))
        self.assertEqual(self.request("GET", "/incidents/999999")[0], 404)

    def test_invalid_payloads(self):
        for field, values in {
            "title": ["", "   ", "\t\n", None],
            "description": ["", "   ", "\t\n", None],
            "severity": ["urgent", "HIGH", "", None],
            "status": ["closed", "OPEN", "", None],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.request("POST", "/incidents", self.payload(**{field: value}))[0], 422)
        for field in ("title", "description", "severity"):
            payload = self.payload()
            del payload[field]
            self.assertEqual(self.request("POST", "/incidents", payload)[0], 422)
        self.assertEqual(self.request("GET", "/incidents"), (200, []))

    def test_allowed_values_and_default_status(self):
        for severity in ("low", "medium", "high", "critical"):
            for status in ("open", "investigating", "resolved"):
                code, incident = self.request("POST", "/incidents", self.payload(severity=severity, status=status))
                self.assertEqual(code, 201)
                self.assertEqual((incident["severity"], incident["status"]), (severity, status))
        payload = self.payload()
        del payload["status"]
        self.assertEqual(self.request("POST", "/incidents", payload)[1]["status"], "open")

    def test_incident_filters(self):
        incidents = []
        for status in ("open", "investigating", "resolved"):
            for severity in ("low", "medium", "high", "critical"):
                code, incident = self.request("POST", "/incidents", self.payload(status=status, severity=severity))
                self.assertEqual(code, 201)
                incidents.append(incident)
        # Include two matches for one combination to verify ordering and completeness.
        _, duplicate = self.request("POST", "/incidents", self.payload(status="open", severity="low"))
        incidents.append(duplicate)
        self.assertEqual(self.request("GET", "/incidents"), (200, incidents))
        for status in ("open", "investigating", "resolved"):
            with self.subTest(status=status):
                expected = [item for item in incidents if item["status"] == status]
                self.assertEqual(self.request("GET", "/incidents?" + urlencode({"status": status})), (200, expected))
        for severity in ("low", "medium", "high", "critical"):
            with self.subTest(severity=severity):
                expected = [item for item in incidents if item["severity"] == severity]
                self.assertEqual(self.request("GET", "/incidents?" + urlencode({"severity": severity})), (200, expected))
            for status in ("open", "investigating", "resolved"):
                with self.subTest(status=status, severity=severity):
                    expected = [item for item in incidents if item["status"] == status and item["severity"] == severity]
                    query = urlencode({"status": status, "severity": severity})
                    self.assertEqual(self.request("GET", "/incidents?" + query), (200, expected))

    def test_incident_filters_without_matches(self):
        self.request("POST", "/incidents", self.payload(status="open", severity="high"))
        self.request("POST", "/incidents", self.payload(status="resolved", severity="low"))
        for query in ("status=investigating", "severity=critical", "status=open&severity=low"):
            with self.subTest(query=query):
                self.assertEqual(self.request("GET", "/incidents?" + query), (200, []))

    def test_incident_filters_invalid_values(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        for field, values in {
            "status": ("closed", "OPEN", "", " ", "null", "open' OR 1=1 --"),
            "severity": ("urgent", "HIGH", "", " ", "null", "high' OR 1=1 --"),
        }.items():
            for value in values:
                for combined in (False, True):
                    with self.subTest(field=field, value=value, combined=combined):
                        filters = {field: value}
                        if combined:
                            filters.update({"severity": "high"} if field == "status" else {"status": "open"})
                        self.assertEqual(self.request("GET", "/incidents?" + urlencode(filters))[0], 422)
        self.assertEqual(self.request("GET", "/incidents"), (200, [incident]))

    def test_update_status_only(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        _, other = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}/status'
        for status in ("investigating", "resolved", "open", "open"):
            with self.subTest(status=status):
                expected = incident | {"status": status}
                self.assertEqual(
                    self.request("PATCH", path, {"status": status, "title": "Ignored title"}),
                    (200, expected),
                )
                self.assertEqual(self.request("GET", f'/incidents/{incident["id"]}'), (200, expected))
                self.assertEqual(self.request("GET", "/incidents"), (200, [expected, other]))

    def test_update_status_validations(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}/status'
        payloads = [{}, {"title": "Missing status"}]
        payloads += [{"status": value} for value in (
            "closed", "OPEN", "", "   ", None, 1, True, [], {},
            "resolved'; DROP TABLE incidents; --",
        )]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("PATCH", path, payload)[0], 422)
        self.assertEqual(self.request("PATCH", path)[0], 422)
        self.assertEqual(self.request("GET", "/incidents"), (200, [incident]))

    def test_update_status_not_found(self):
        self.assertEqual(
            self.request("PATCH", "/incidents/999999/status", {"status": "resolved"}),
            (404, {"detail": "Incident not found"}),
        )
        self.assertEqual(self.request("GET", "/incidents"), (200, []))

    def test_updated_status_persists_after_process_restart(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        _, other = self.request("POST", "/incidents", self.payload())
        expected = incident | {"status": "resolved"}
        self.assertEqual(
            self.request("PATCH", f'/incidents/{incident["id"]}/status', {"status": "resolved"}),
            (200, expected),
        )
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("GET", f'/incidents/{incident["id"]}'), (200, expected))
        self.assertEqual(self.request("GET", "/incidents"), (200, [expected, other]))

    def test_history_records_changes_and_persists(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        _, other = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}'
        self.assertEqual(self.request("GET", path + "/history"), (200, []))
        for status in ("investigating", "resolved", "resolved", "open"):
            self.assertEqual(self.request("PATCH", path + "/status", {"status": status})[0], 200)
        code, history = self.request("GET", path + "/history")
        self.assertEqual(code, 200)
        self.assertEqual(
            [(entry["previous_status"], entry["new_status"]) for entry in history],
            [("open", "investigating"), ("investigating", "resolved"), ("resolved", "open")],
        )
        ids = [entry["id"] for entry in history]
        self.assertEqual(ids, sorted(set(ids)))
        for entry in history:
            self.assertEqual(entry["incident_id"], incident["id"])
            timestamp = datetime.fromisoformat(entry["changed_at"].replace("Z", "+00:00"))
            self.assertEqual(timestamp.utcoffset(), timedelta(0))
        self.assertEqual(self.request("GET", f'/incidents/{other["id"]}/history'), (200, []))
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("GET", path + "/history"), (200, history))
        self.assertEqual(self.request("GET", path), (200, incident))

    def test_history_not_found_and_invalid_changes(self):
        self.assertEqual(self.request("GET", "/incidents/999999/history"),
                         (404, {"detail": "Incident not found"}))
        _, incident = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}'
        for payload in ({}, {"status": None}, {"status": "invalid"}):
            self.assertEqual(self.request("PATCH", path + "/status", payload)[0], 422)
        self.assertEqual(self.request("PATCH", "/incidents/999999/status", {"status": "resolved"})[0], 404)
        self.assertEqual(self.request("GET", path + "/history"), (200, []))
        self.assertEqual(self.request("GET", path), (200, incident))
        with closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM incident_status_history").fetchone()[0], 0)

    def test_history_failure_rolls_back_status_update(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}'
        # Force an insertion failure in the temporary database after the UPDATE.
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("""
                CREATE TRIGGER reject_history BEFORE INSERT ON incident_status_history
                BEGIN SELECT RAISE(ABORT, 'Simulated history failure'); END
            """)
        request = Request(self.base_url + path + "/status", method="PATCH",
                          data=json.dumps({"status": "resolved"}).encode(),
                          headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 500)
        caught.exception.close()
        self.assertEqual(self.request("GET", path), (200, incident))
        self.assertEqual(self.request("GET", path + "/history"), (200, []))
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("DROP TRIGGER reject_history")
        self.assertEqual(self.request("PATCH", path + "/status", {"status": "resolved"})[0], 200)
        self.assertEqual(len(self.request("GET", path + "/history")[1]), 1)

    def test_history_table_added_to_existing_database(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        self.stop_server()
        # Reproduce the schema before history existed, retaining incident data.
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("DROP TABLE incident_status_history")
        self.start_server()
        path = f'/incidents/{incident["id"]}'
        self.assertEqual(self.request("GET", path), (200, incident))
        self.assertEqual(self.request("GET", path + "/history"), (200, []))
        self.assertEqual(self.request("PATCH", path + "/status", {"status": "investigating"})[0], 200)
        entry = self.request("GET", path + "/history")[1][0]
        self.assertEqual((entry["previous_status"], entry["new_status"]), ("open", "investigating"))

    def test_persistence_after_process_restart(self):
        code, incident = self.request("POST", "/incidents", self.payload())
        self.assertEqual(code, 201)
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("GET", "/incidents"), (200, [incident]))
        self.assertEqual(self.request("GET", f'/incidents/{incident["id"]}'), (200, incident))
        code, second = self.request("POST", "/incidents", self.payload())
        self.assertEqual(code, 201)
        self.assertGreater(second["id"], incident["id"])


if __name__ == "__main__":
    unittest.main()
