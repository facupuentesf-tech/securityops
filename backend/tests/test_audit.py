"""Audit integration tests use the real HTTP server and disposable SQLite databases."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
import json
import sqlite3
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import test_incidents as fixtures
import test_risks as risks
import test_controls as controls


class AuditTests(unittest.TestCase):
    setUp = fixtures.IncidentTests.setUp
    start_server = fixtures.IncidentTests.start_server
    stop_server = fixtures.IncidentTests.stop_server
    seed_admin = fixtures.IncidentTests.seed_admin
    request = fixtures.IncidentTests.request
    login_client = fixtures.IncidentTests.login_client
    payload = fixtures.IncidentTests.payload
    asset_payload = fixtures.IncidentTests.asset_payload
    risk_payload = risks.RiskTests.risk_payload
    control_payload = controls.ControlTests.control_payload
    second_organization = risks.RiskTests.second_organization

    def user(self, role="analista", suffix="analyst", name="Audit Analyst"):
        code, user = self.request("POST", "/users", {"display_name": name, "email": suffix + "@example.test",
                                "role": role, "password": "audit user password"})
        self.assertEqual(code, 201)
        return user

    def events(self, **filters):
        code, data = self.request("GET", "/audit-logs?" + urlencode({"page_size": 100} | filters))
        self.assertEqual(code, 200)
        return data["items"]

    def snapshot(self):
        with closing(fixtures.app_main.connect()) as connection:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
            return {table: [tuple(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY 1')]
                    for table in tables}

    def fail_audit(self, condition="1"):
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_logs WHEN " + condition +
                               " BEGIN SELECT RAISE(ABORT, 'Injected audit failure'); END")

    def failed_request(self, method, path, body):
        request = Request(self.base_url + path, data=json.dumps(body).encode() if body is not None else None,
                          method=method, headers={"Content-Type": "application/json", "X-CSRF-Token": self.csrf})
        with self.assertRaises(HTTPError) as caught:
            self.opener.open(request, timeout=2)
        with caught.exception as response:
            self.assertEqual(response.status, 500)
            response.read()

    def test_all_business_events_minimal_details_and_historical_actor(self):
        user = self.user(name="<img src=x onerror=alert(1)>")
        asset = self.request("POST", "/assets", self.asset_payload(description="SECRET asset description"))[1]
        risk = self.request("POST", "/risks", self.risk_payload(asset_id=asset["id"], description="SECRET risk description"))[1]
        control = self.request("POST", "/controls", self.control_payload(description="SECRET control description"))[1]
        incident = self.request("POST", "/incidents", self.payload(description="SECRET incident description"))[1]
        ip, rp = f'/incidents/{incident["id"]}', f'/risks/{risk["id"]}'
        self.assertEqual(self.request("PATCH", ip + "/status", {"status": "resolved"})[0], 200)
        note = self.request("POST", ip + "/notes", {"content": "SECRET note content"})[1]
        for path, body in ((ip + "/assets", {"asset_id": asset["id"]}), (rp + "/controls", {"control_id": control["id"]})):
            self.assertEqual(self.request("POST", path, body)[0], 201)
            self.assertEqual(self.request("DELETE", path + "/1")[0], 204)
        for path in (ip, rp):
            for target in (1, user["id"], None):
                self.assertEqual(self.request("PATCH", path + "/assignee", {"assignee_id": target})[0], 200)
        self.request("PATCH", f'/users/{user["id"]}', {"role": "lector", "is_active": False})
        self.request("POST", f'/users/{user["id"]}/password', {"password": "SECRET reset password"})
        before = self.events()
        self.assertEqual(len(before), 20)
        self.assertEqual({e["resource_type"] for e in before if e["action"] == "created"},
                         {"user", "asset", "risk", "control", "incident"})
        self.assertEqual(next(e["details"] for e in before if e["action"] == "status_changed"),
                         {"previous_status": "open", "new_status": "resolved"})
        self.assertEqual(next(e["details"] for e in before if e["action"] == "note_created"), {"note_id": note["id"]})
        for event in before:
            self.assertEqual((event["actor_id"], event["actor_name"], event["organization_id"]), (1, "Test Administrator", 1))
            self.assertEqual(datetime.fromisoformat(event["occurred_at"]).utcoffset(), timezone.utc.utcoffset(None))
            self.assertLessEqual(set(event["details"]), fixtures.app_main.AUDIT_DETAIL_KEYS[event["action"]])
        self.request("PATCH", "/users/1", {"display_name": "Renamed Admin", "email": "renamed@example.test"})
        after = self.events()
        self.assertEqual(after[1:], before)
        self.assertEqual(after[0]["actor_name"], "Test Administrator")
        self.assertEqual(after[0]["details"], {"display_name_changed": True, "email_changed": True})
        self.request("POST", "/assets", self.asset_payload())
        self.assertEqual(self.events()[0]["actor_name"], "Renamed Admin")
        serialized = json.dumps(self.events())
        for secret in ("SECRET", "password_hash", "scrypt$", "csrf_token", "token_hash", "cookie", "audit user password", "renamed@example.test"):
            self.assertNotIn(secret, serialized)
        with closing(fixtures.app_main.connect()) as connection:
            stored = str([tuple(row) for row in connection.execute("SELECT * FROM audit_logs")])
            self.assertNotIn("SECRET", stored)
            for row in connection.execute("SELECT password_hash FROM users"):
                self.assertNotIn(row[0], stored)
            for row in connection.execute("SELECT token_hash, csrf_token FROM sessions"):
                for secret in row:
                    self.assertNotIn(secret, stored)

    def test_failed_requests_and_no_effect_produce_no_events(self):
        user = self.user()
        incident = self.request("POST", "/incidents", self.payload())[1]
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        path = f'/incidents/{incident["id"]}'
        self.request("POST", path + "/assets", {"asset_id": asset["id"]})
        before = self.events()
        for method, endpoint, body, code in (
            ("PATCH", path + "/status", {"status": "open"}, 200),
            ("PATCH", path + "/assignee", {"assignee_id": None}, 200),
            ("PATCH", f'/users/{user["id"]}', {"role": "analista", "is_active": True}, 200),
            ("PATCH", path + "/status", {"status": "invalid"}, 422),
            ("PATCH", "/incidents/999/status", {"status": "resolved"}, 404),
            ("POST", path + "/assets", {"asset_id": asset["id"]}, 409),
            ("POST", path + "/notes", {"content": " "}, 422),
            ("POST", "/users", {"display_name": "Duplicate", "email": user["email"], "role": "lector", "password": "audit user password"}, 409),
            ("POST", "/assets", self.asset_payload() | {"actor_id": 2}, 422),
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.request(method, endpoint, body)[0], code)
                self.assertEqual(self.events(), before)
        self.assertEqual(self.request("POST", "/assets", self.asset_payload(), send_csrf=False)[0], 403)
        self.assertEqual(self.events(), before)
        self.request("PATCH", path + "/assignee", {"assignee_id": user["id"]})
        assigned = self.events()
        self.request("PATCH", path + "/assignee", {"assignee_id": user["id"]})
        self.assertEqual(self.events(), assigned)
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("UPDATE users SET display_name = 'Same', email = 'same@example.test' WHERE id = ?", (user["id"],))
        self.request("PATCH", f'/users/{user["id"]}', {"display_name": " Same ", "email": "SAME@example.test"})
        self.assertEqual(self.events(), assigned)

    def test_permissions_isolation_filters_validation_and_pagination(self):
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        self.assertEqual(self.request("GET", "/audit-logs", client=anonymous)[0], 401)
        for role in ("analista", "lector"):
            user = self.user(role=role, suffix=role)
            client = self.login_client(user["email"], "audit user password")
            self.assertEqual(self.request("GET", "/audit-logs", client=client)[0], 403)
        second = self.second_organization()
        foreign = self.request("POST", "/assets", self.asset_payload(), client=second)[1]
        foreign_events = self.request("GET", "/audit-logs", client=second)[1]["items"]
        self.assertEqual(len(foreign_events), 1)
        self.assertEqual(foreign_events[0]["resource_id"], foreign["id"])
        self.assertTrue(all(e["organization_id"] == 1 for e in self.events()))
        self.assertEqual(self.events(actor_id=foreign_events[0]["actor_id"]), [])
        for _ in range(28):
            self.request("POST", "/assets", self.asset_payload())
        events = self.events()
        self.assertEqual(len(events), 30)
        first = self.request("GET", "/audit-logs?page_size=7")[1]
        self.assertEqual((first["total"], first["page"], first["page_size"]), (30, 1, 7))
        paged = []
        for page in range(1, 6):
            paged.extend(self.events(page=page, page_size=7))
        self.assertEqual(paged, events)
        self.assertEqual(self.events(page=6, page_size=7), [])
        chosen = events[5]
        for filters, expected in (({"actor_id": 1, "action": "created", "resource_type": "asset"}, events[:28]),
                                  ({"actor_id": 1, "action": "created", "resource_type": "user"}, events[28:]),
                                  ({"action": "role_changed", "resource_type": "asset"}, []),
                                  ({"date_from": chosen["occurred_at"], "date_to": chosen["occurred_at"]}, [chosen])):
            self.assertEqual(self.events(**filters), expected)
        localized = datetime.fromisoformat(chosen["occurred_at"]).astimezone(timezone(timedelta(hours=-3))).isoformat()
        self.assertEqual(self.events(date_from=localized, date_to=localized), [chosen])
        for query in ("actor_id=0", "actor_id=1.5", "actor_id=true", "action=bad", "resource_type=bad",
                      "page=0", "page=-1", "page_size=101", "page_size=0", "page_size=abc", "date_from=bad",
                      "date_from=2026-01-01T00:00:00", "date_from=2027-01-01T00:00:00Z&date_to=2026-01-01T00:00:00Z",
                      "action=created%27%20OR%201=1--"):
            self.assertEqual(self.request("GET", "/audit-logs?" + query)[0], 422, query)
        self.assertEqual(self.events(actor_id=99999), [])
        for method in ("POST", "PATCH", "DELETE", "PUT"):
            for endpoint in ("/audit-logs", "/audit-logs/1"):
                self.assertIn(self.request(method, endpoint, {})[0], (404, 405))
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("UPDATE audit_logs SET occurred_at = '2026-01-01T00:00:00+00:00'")
        tied = self.events()
        self.assertEqual([e["id"] for e in tied], sorted([e["id"] for e in tied], reverse=True))
        self.assertEqual(self.events(page_size=7, page=2), tied[7:14])

    def test_audit_insert_failure_rolls_back_every_business_operation(self):
        user = self.user()
        incident = self.request("POST", "/incidents", self.payload())[1]
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        control = self.request("POST", "/controls", self.control_payload())[1]
        ip, rp = f'/incidents/{incident["id"]}', f'/risks/{risk["id"]}'
        self.request("POST", ip + "/assets", {"asset_id": asset["id"]})
        self.request("POST", rp + "/controls", {"control_id": control["id"]})
        self.fail_audit()
        before = self.snapshot()
        operations = [
            ("POST", "/incidents", self.payload()), ("POST", "/assets", self.asset_payload()),
            ("POST", "/risks", self.risk_payload()), ("POST", "/controls", self.control_payload()),
            ("POST", "/users", {"display_name": "New", "email": "new@example.test", "role": "lector", "password": "audit user password"}),
            ("PATCH", ip + "/status", {"status": "resolved"}), ("POST", ip + "/notes", {"content": "secret note"}),
            ("PATCH", ip + "/assignee", {"assignee_id": user["id"]}),
            ("PATCH", rp + "/assignee", {"assignee_id": user["id"]}),
            ("DELETE", ip + f'/assets/{asset["id"]}', None), ("DELETE", rp + f'/controls/{control["id"]}', None),
            ("PATCH", f'/users/{user["id"]}', {"role": "lector"}),
            ("PATCH", f'/users/{user["id"]}', {"is_active": False}),
            ("PATCH", f'/users/{user["id"]}', {"display_name": "Updated"}),
            ("POST", "/users/1/password", {"password": "different audit password"}),
        ]
        for method, path, body in operations:
            with self.subTest(path=path):
                self.failed_request(method, path, body)
                self.assertEqual(self.snapshot(), before)
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("DROP TRIGGER fail_audit")
        self.request("DELETE", ip + f'/assets/{asset["id"]}')
        self.request("DELETE", rp + f'/controls/{control["id"]}')
        self.fail_audit()
        before = self.snapshot()
        for path, body in ((ip + "/assets", {"asset_id": asset["id"]}), (rp + "/controls", {"control_id": control["id"]})):
            self.failed_request("POST", path, body)
            self.assertEqual(self.snapshot(), before)

    def test_automatic_removals_and_late_insert_failure_roll_back_user_and_sessions(self):
        user = self.user()
        client = self.login_client(user["email"], "audit user password")
        incident = self.request("POST", "/incidents", self.payload())[1]
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        for path in (f'/incidents/{incident["id"]}', f'/risks/{risk["id"]}'):
            self.request("PATCH", path + "/assignee", {"assignee_id": user["id"]})
        # Fail the final automatic risk event, after user and incident events were inserted.
        self.fail_audit("NEW.action = 'assignee_changed' AND NEW.resource_type = 'risk'")
        before = self.snapshot()
        for change in ({"is_active": False}, {"role": "lector"}, {"role": "lector", "is_active": False}):
            self.failed_request("PATCH", f'/users/{user["id"]}', change)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.request("GET", "/auth/session", client=client)[1]["user"]["id"], user["id"])
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("DROP TRIGGER fail_audit")
        self.request("PATCH", f'/users/{user["id"]}', {"role": "lector", "is_active": False})
        events = self.events()
        self.assertEqual(len(events) - len(before["audit_logs"]), 4)
        automatic = [e for e in events if e["details"].get("automatic")]
        self.assertEqual({e["resource_type"] for e in automatic}, {"incident", "risk"})
        self.assertTrue(all(e["details"] == {"previous_assignee_id": user["id"], "new_assignee_id": None,
                                           "automatic": True, "user_id": user["id"]} for e in automatic))
        self.assertIsNone(self.request("GET", "/auth/session", client=client)[1]["user"])
        before = self.events()
        self.request("PATCH", f'/users/{user["id"]}', {"role": "lector", "is_active": False})
        self.assertEqual(self.events(), before)
        self.request("PATCH", f'/users/{user["id"]}', {"role": "analista", "is_active": True})
        self.assertEqual(len([e for e in self.events() if e["details"].get("automatic")]), 2)
        # Independently verify both cleanup triggers with each eligibility change.
        for change in ({"role": "lector"}, {"is_active": False}):
            for kind, resource in (("incidents", incident), ("risks", risk)):
                self.request("PATCH", f'/{kind}/{resource["id"]}/assignee', {"assignee_id": user["id"]})
            count = len(self.events())
            self.request("PATCH", f'/users/{user["id"]}', change)
            self.assertEqual(len(self.events()) - count, 3)
            for kind, resource in (("incidents", incident), ("risks", risk)):
                self.assertIsNone(self.request("GET", f'/{kind}/{resource["id"]}')[1]["assignee_id"])
            self.request("PATCH", f'/users/{user["id"]}', {"role": "analista", "is_active": True})

    def test_persistence_migration_preserves_all_data_and_does_not_backfill(self):
        self.user()
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        incident = self.request("POST", "/incidents", self.payload())[1]
        risk = self.request("POST", "/risks", self.risk_payload(asset_id=asset["id"]))[1]
        control = self.request("POST", "/controls", self.control_payload())[1]
        ip = f'/incidents/{incident["id"]}'
        self.request("PATCH", ip + "/status", {"status": "resolved"})
        self.request("POST", ip + "/notes", {"content": "Preserved note"})
        self.request("POST", ip + "/assets", {"asset_id": asset["id"]})
        self.request("POST", f'/risks/{risk["id"]}/controls', {"control_id": control["id"]})
        self.request("PATCH", ip + "/assignee", {"assignee_id": 1})
        before = self.snapshot()
        events = self.events()
        self.stop_server(); self.start_server()
        self.assertEqual(self.events(), events)
        self.assertEqual(self.snapshot(), before)
        self.stop_server()
        with closing(fixtures.app_main.connect()) as connection, connection:
            fixtures.rewind_assessment_migration(connection)
            connection.execute("DROP TABLE audit_logs")
            connection.execute("DELETE FROM schema_migrations WHERE version IN (9, 10)")
        legacy = self.snapshot()
        fixtures.app_main.migrate_database()
        migrated = self.snapshot()
        for table, rows in legacy.items():
            if table == "schema_migrations":
                self.assertEqual(migrated[table][:-3], rows)
            else:
                self.assertEqual(migrated[table], rows, table)
        self.assertEqual(migrated["audit_logs"], [])
        fixtures.app_main.migrate_database()
        self.assertEqual(self.snapshot(), migrated)
        self.start_server()
        self.assertEqual(self.events(), [])
        self.request("POST", "/assets", self.asset_payload())
        self.assertEqual(len(self.events()), 1)


if __name__ == "__main__":
    unittest.main()
