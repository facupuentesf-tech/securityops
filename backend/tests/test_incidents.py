import json
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, build_opener
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import main as app_main


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "incidents.db"
        app_main.DATABASE_PATH = self.database
        self.cookiejar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookiejar))
        self.csrf = None
        self.start_server()
        self.addCleanup(self.stop_server)
        self.seed_admin()

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

    def seed_admin(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "INSERT INTO users (display_name, email, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "Test Administrator",
                    "admin@example.test",
                    app_main.hash_password("correct horse battery"),
                    "administrador",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
        code, body = self.request(
            "POST", "/auth/login",
            {"email": "admin@example.test", "password": "correct horse battery"},
        )
        self.assertEqual(code, 200)
        self.assertEqual(body["user"]["role"], "administrador")
        self.csrf = body["csrf_token"]

    def stop_server(self):
        if self.server.poll() is None:
            self.server.terminate()
            self.server.wait(timeout=10)

    def request(self, method, path, payload=None, client=None, send_csrf=True):
        opener, csrf = client or (self.opener, self.csrf)
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if send_csrf and csrf and method not in ("GET", "HEAD", "OPTIONS"):
            headers["X-CSRF-Token"] = csrf
        request = Request(
            self.base_url + path, data=data, method=method,
            headers=headers,
        )
        try:
            response = opener.open(request, timeout=2)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def login_client(self, email, password):
        client = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        code, body = self.request(
            "POST", "/auth/login", {"email": email, "password": password}, client=client
        )
        self.assertEqual(code, 200)
        return client[0], body["csrf_token"]

    def payload(self, **changes):
        return dict(title="Suspicious login", description="Failed login attempts",
                    severity="high", status="open") | changes

    def test_web_page_assets_and_docs(self):
        for path, content_type, expected in (
            ("/", "text/html", 'lang="es"'),
            ("/static/app.js", "javascript", "textContent"),
            ("/static/styles.css", "text/css", "@media"),
            ("/docs", "text/html", "swagger-ui"),
        ):
            with self.subTest(path=path), urlopen(self.base_url + path, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(content_type, response.headers["Content-Type"])
                self.assertIn(expected, response.read().decode("utf-8"))

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
            self.assertEqual(entry["changed_by"], 1)
            self.assertEqual(entry["changed_by_name"], "Test Administrator")
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
                          headers={
                              "Content-Type": "application/json",
                              "X-CSRF-Token": self.csrf,
                              "Cookie": "; ".join(
                                  f"{cookie.name}={cookie.value}" for cookie in self.cookiejar
                              ),
                          })
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

    def test_notes_creation_listing_and_persistence(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        _, other = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}/notes'
        self.assertEqual(self.request("GET", path), (200, []))
        content = "O'Brien'); DROP TABLE incident_notes; --"
        code, note = self.request("POST", path, {"content": " \t" + content + "\n "})
        self.assertEqual(code, 201)
        self.assertGreater(note["id"], 0)
        self.assertEqual(note["incident_id"], incident["id"])
        self.assertEqual(note["content"], content)
        self.assertEqual(note["created_by"], 1)
        self.assertEqual(note["created_by_name"], "Test Administrator")
        timestamp = datetime.fromisoformat(note["created_at"].replace("Z", "+00:00"))
        self.assertEqual(timestamp.utcoffset(), timedelta(0))
        self.assertEqual(self.request("GET", path), (200, [note]))
        self.assertEqual(self.request("GET", f'/incidents/{other["id"]}/notes'), (200, []))
        self.assertEqual(self.request("GET", f'/incidents/{incident["id"]}'), (200, incident))
        self.assertEqual(self.request("GET", f'/incidents/{incident["id"]}/history'), (200, []))
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("GET", path), (200, [note]))
        code, second = self.request("POST", path, {"content": "Second note"})
        self.assertEqual(code, 201)
        self.assertGreater(second["id"], note["id"])
        self.assertEqual(self.request("GET", path), (200, [note, second]))

    def test_notes_order_by_date_then_id(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}/notes'
        notes = [self.request("POST", path, {"content": content})[1]
                 for content in ("Created first", "Created second", "Created third")]
        # Make ID order differ from date order and give two rows equal timestamps.
        timestamps = ("2026-10-01T12:00:00+00:00", "2026-10-01T11:00:00+00:00",
                      "2026-10-01T11:00:00+00:00")
        with closing(sqlite3.connect(self.database)) as connection, connection:
            for note, timestamp in zip(notes, timestamps):
                connection.execute("UPDATE incident_notes SET created_at = ? WHERE id = ?",
                                   (timestamp, note["id"]))
                note["created_at"] = timestamp.replace("+00:00", "Z")
        self.assertEqual(self.request("GET", path), (200, [notes[1], notes[2], notes[0]]))

    def test_notes_validation_and_length_boundaries(self):
        _, incident = self.request("POST", "/incidents", self.payload())
        path = f'/incidents/{incident["id"]}/notes'
        invalid = [{}] + [{"content": value} for value in
                         ("", "   ", "\t\n", "\u2003", None, 123, True, [], {}, "x" * 5001)]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:80]):
                self.assertEqual(self.request("POST", path, payload)[0], 422)
        self.assertEqual(self.request("POST", path)[0], 422)
        self.assertEqual(self.request("GET", path), (200, []))
        for content in ("x", "x" * 5000):
            with self.subTest(length=len(content)):
                code, note = self.request("POST", path, {"content": " \t" + content + "\n "})
                self.assertEqual(code, 201)
                self.assertEqual(note["content"], content)

    def test_notes_not_found(self):
        path = "/incidents/999999/notes"
        expected = (404, {"detail": "Incident not found"})
        self.assertEqual(self.request("GET", path), expected)
        self.assertEqual(self.request("POST", path, {"content": "Investigation"}), expected)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM incident_notes").fetchone()[0], 0)

    def test_versioned_migrations_preserve_legacy_incidents_history_and_notes(self):
        self.stop_server()
        self.database.unlink()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executescript("""
                CREATE TABLE incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
                    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
                    status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'resolved')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE incident_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id INTEGER NOT NULL REFERENCES incidents(id),
                    previous_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    changed_at TEXT NOT NULL
                );
                CREATE TABLE incident_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id INTEGER NOT NULL REFERENCES incidents(id),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO incidents VALUES (17, 'Legacy incident', 'Existing data', 'high', 'investigating', '2025-01-01T00:00:00+00:00');
                INSERT INTO incident_status_history VALUES (8, 17, 'open', 'investigating', '2025-01-02T00:00:00+00:00');
                INSERT INTO incident_notes VALUES (9, 17, 'Legacy note', '2025-01-03T00:00:00+00:00');
            """)
        self.start_server()
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.seed_admin()
        self.assertEqual(self.request("GET", "/incidents/17")[0], 200)
        self.assertEqual(self.request("GET", "/incidents/17/history")[1][0]["id"], 8)
        self.assertEqual(self.request("GET", "/incidents/17/notes")[1][0]["id"], 9)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall(),
                [(1,), (2,)],
            )
            self.assertEqual(
                connection.execute("SELECT changed_by FROM incident_status_history WHERE id = 8").fetchone()[0],
                None,
            )

    def test_authentication_cookie_csrf_and_logout(self):
        with closing(sqlite3.connect(self.database)) as connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM users WHERE email = 'admin@example.test'"
            ).fetchone()[0]
        self.assertTrue(password_hash.startswith("scrypt$"))
        self.assertTrue(app_main.verify_password("correct horse battery", password_hash))
        self.assertFalse(app_main.verify_password("incorrect password", password_hash))
        session_cookie = next(cookie for cookie in self.cookiejar if cookie.name == "securityops_session")
        self.assertTrue(session_cookie.has_nonstandard_attr("HttpOnly"))
        self.assertEqual(session_cookie.get_nonstandard_attr("SameSite").lower(), "strict")
        self.assertEqual(self.request("GET", "/auth/session")[1]["user"]["email"], "admin@example.test")
        self.assertEqual(
            self.request("POST", "/incidents", self.payload(), send_csrf=False)[0], 403
        )
        self.assertEqual(self.request("POST", "/auth/logout")[0], 200)
        self.assertEqual(self.request("GET", "/incidents")[0], 401)

    def test_expired_session_is_rejected(self):
        cookie = next(cookie for cookie in self.cookiejar if cookie.name == "securityops_session")
        token_hash = hashlib.sha256(cookie.value.encode("utf-8")).hexdigest()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE sessions SET expires_at = 0 WHERE token_hash = ?", (token_hash,))
        self.assertEqual(self.request("GET", "/incidents")[0], 401)

    def test_protected_endpoints_reject_anonymous_requests(self):
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        for method, path, payload in (
            ("GET", "/incidents", None),
            ("GET", "/incidents/1", None),
            ("GET", "/incidents/1/history", None),
            ("GET", "/incidents/1/notes", None),
            ("POST", "/incidents", self.payload()),
            ("PATCH", "/incidents/1/status", {"status": "resolved"}),
            ("GET", "/users", None),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path, payload, client=anonymous)[0], 401)
        self.assertEqual(self.request("GET", "/health", client=anonymous), (200, {"status": "ok"}))

    def test_role_permissions_and_admin_user_management(self):
        created = self.request(
            "POST", "/users",
            {
                "display_name": "Analyst",
                "email": "analyst@example.test",
                "password": "analyst password 123",
                "role": "analista",
            },
        )
        self.assertEqual(created[0], 201)
        analyst = self.login_client("analyst@example.test", "analyst password 123")
        incident_code, incident = self.request(
            "POST", "/incidents", self.payload(), client=analyst
        )
        self.assertEqual(incident_code, 201)
        path = f'/incidents/{incident["id"]}'
        self.assertEqual(
            self.request("PATCH", path + "/status", {"status": "investigating"}, client=analyst)[0],
            200,
        )
        self.assertEqual(
            self.request("POST", path + "/notes", {"content": "Analyst note"}, client=analyst)[0],
            201,
        )
        self.assertEqual(self.request("GET", "/users", client=analyst)[0], 403)

        self.assertEqual(self.request(
            "POST", "/users",
            {
                "display_name": "Reader",
                "email": "reader@example.test",
                "password": "reader password 123",
                "role": "lector",
            },
        )[0], 201)
        reader = self.login_client("reader@example.test", "reader password 123")
        for route in ("/incidents", path, path + "/history", path + "/notes"):
            self.assertEqual(self.request("GET", route, client=reader)[0], 200)
        self.assertEqual(self.request("POST", "/incidents", self.payload(), client=reader)[0], 403)
        self.assertEqual(
            self.request("PATCH", path + "/status", {"status": "resolved"}, client=reader)[0],
            403,
        )
        self.assertEqual(
            self.request("POST", path + "/notes", {"content": "No access"}, client=reader)[0],
            403,
        )
        self.assertEqual(self.request("POST", "/users", {}, client=reader)[0], 403)

        analyst_id = created[1]["id"]
        updated_analyst = self.request(
            "PATCH",
            f"/users/{analyst_id}",
            {
                "display_name": "Updated Analyst",
                "email": "updated-analyst@example.test",
                "role": "lector",
            },
        )
        self.assertEqual(updated_analyst[0], 200)
        self.assertEqual(updated_analyst[1]["display_name"], "Updated Analyst")
        self.assertEqual(updated_analyst[1]["email"], "updated-analyst@example.test")
        self.assertEqual(updated_analyst[1]["role"], "lector")
        self.assertEqual(
            self.request("PATCH", f"/users/{analyst_id}", {"is_active": False})[0], 200
        )
        self.assertEqual(self.request("GET", "/incidents", client=analyst)[0], 401)

    def test_admin_user_password_reset_and_last_admin_guard(self):
        self.assertEqual(
            self.request("PATCH", "/users/1", {"is_active": False})[0], 409
        )
        _, user = self.request(
            "POST", "/users",
            {
                "display_name": "Temporary Reader",
                "email": "temporary@example.test",
                "password": "temporary password 123",
                "role": "lector",
            },
        )
        old_password_client = self.login_client("temporary@example.test", "temporary password 123")
        self.assertEqual(
            self.request(
                "POST", f'/users/{user["id"]}/password', {"password": "replacement pass 123"}
            )[0],
            200,
        )
        self.assertEqual(self.request("GET", "/auth/session", client=old_password_client)[1]["user"], None)
        bad_client = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        self.assertEqual(self.request(
            "POST", "/auth/login",
            {"email": "temporary@example.test", "password": "temporary password 123"},
            client=bad_client,
        )[0], 401)
        replacement_client = self.login_client("temporary@example.test", "replacement pass 123")
        self.assertEqual(
            self.request("GET", "/auth/session", client=replacement_client)[1]["user"]["id"],
            user["id"],
        )

    def test_login_rejects_invalid_credentials_and_disabled_accounts(self):
        client = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        self.assertEqual(self.request(
            "POST", "/auth/login",
            {"email": "admin@example.test", "password": "incorrect password"},
            client=client,
        )[0], 401)
        _, analyst = self.request(
            "POST", "/users",
            {
                "display_name": "Disabled",
                "email": "disabled@example.test",
                "password": "disabled account pass",
                "role": "lector",
            },
        )
        self.request("PATCH", f'/users/{analyst["id"]}', {"is_active": False})
        disabled_client = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        self.assertEqual(self.request(
            "POST", "/auth/login",
            {"email": "disabled@example.test", "password": "disabled account pass"},
            client=disabled_client,
        )[0], 401)

    def test_local_bootstrap_command_creates_only_first_admin(self):
        database = Path(self.directory.name) / "bootstrap.db"
        environment = os.environ.copy()
        environment["SECURITYOPS_DATABASE"] = str(database)
        result = subprocess.run(
            [sys.executable, str(BACKEND / "main.py"), "create-admin"],
            input=(
                "bootstrap@example.test\n"
                "Bootstrap Admin\n"
                "a unique bootstrap password\n"
                "a unique bootstrap password\n"
            ),
            text=True,
            capture_output=True,
            env=environment,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(sqlite3.connect(database)) as connection:
            user = connection.execute(
                "SELECT email, role, password_hash FROM users"
            ).fetchone()
            self.assertEqual(user[0:2], ("bootstrap@example.test", "administrador"))
            self.assertTrue(app_main.verify_password("a unique bootstrap password", user[2]))
            self.assertNotIn("a unique bootstrap password", user[2])
        duplicate = subprocess.run(
            [sys.executable, str(BACKEND / "main.py"), "create-admin"],
            text=True,
            capture_output=True,
            env=environment,
            timeout=30,
        )
        self.assertEqual(duplicate.returncode, 1)

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
