"""Dashboard tests through the real HTTP server and an interleaved SQLite reader."""
from contextlib import closing
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import sqlite3
import unittest
from unittest.mock import patch
from urllib.request import HTTPCookieProcessor, build_opener

import test_incidents as fixtures
import test_risks as risks
import test_controls as controls


class DashboardTests(unittest.TestCase):
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

    def summary(self, client=None, query=""):
        code, data = self.request("GET", "/dashboard" + query, client=client)
        self.assertEqual(code, 200)
        self.assertEqual(datetime.fromisoformat(data["generated_at"]).utcoffset(), timezone.utc.utcoffset(None))
        return data

    def create(self, path, payload, client=None):
        code, body = self.request("POST", path, payload, client=client)
        self.assertEqual(code, 201)
        return body

    def without_time(self, data):
        return {key: value for key, value in data.items() if key != "generated_at"}

    def test_empty_categories_and_read_only_summary(self):
        with closing(fixtures.app_main.connect()) as connection:
            before = [tuple(row) for row in connection.execute("SELECT * FROM schema_migrations")]
        data = self.summary()
        self.assertEqual(set(data), {"generated_at", "incidents", "assets", "risks", "controls"})
        self.assertEqual(data["incidents"], {"total": 0, "by_status": {"open": 0, "investigating": 0, "resolved": 0},
                         "by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
                         "pending": {"total": 0, "unassigned": 0, "recent": []}})
        self.assertEqual(data["assets"], {"total": 0, "by_criticality": {"low": 0, "medium": 0, "high": 0, "critical": 0}})
        self.assertEqual(data["risks"], {"total": 0, "by_status": {"identified": 0, "treating": 0, "accepted": 0},
                         "by_level": {"low": 0, "medium": 0, "high": 0, "critical": 0}, "unassigned_pending": 0, "priority": []})
        self.assertEqual(data["controls"], {"total": 0, "by_status": {"planned": 0, "implemented": 0, "retired": 0}})
        with closing(fixtures.app_main.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0], 0)
            self.assertEqual([tuple(row) for row in connection.execute("SELECT * FROM schema_migrations")], before)

    def test_counts_assignments_and_many_to_many_do_not_duplicate(self):
        incidents = []
        for state, severity in (("open", "low"), ("open", "medium"), ("investigating", "high"), ("resolved", "critical")):
            incidents.append(self.create("/incidents", self.payload(status=state, severity=severity)))
        self.request("PATCH", f'/incidents/{incidents[1]["id"]}/assignee', {"assignee_id": 1})
        assets = [self.create("/assets", self.asset_payload(criticality=value)) for value in ("low", "medium", "high", "critical")]
        risk_rows = [self.create("/risks", self.risk_payload(probability=p, impact=i, status=state))
                     for p, i, state in ((1, 4, "identified"), (3, 3, "treating"), (4, 4, "accepted"), (5, 5, "identified"))]
        self.request("PATCH", f'/risks/{risk_rows[1]["id"]}/assignee', {"assignee_id": 1})
        control_rows = [self.create("/controls", self.control_payload(status=state)) for state in ("planned", "implemented", "retired")]
        before = self.without_time(self.summary())
        for incident in incidents[:2]:
            for asset in assets:
                self.create(f'/incidents/{incident["id"]}/assets', {"asset_id": asset["id"]})
        for risk in risk_rows[:2]:
            for control in control_rows:
                self.create(f'/risks/{risk["id"]}/controls', {"control_id": control["id"]})
        data = self.summary()
        self.assertEqual(self.without_time(data), before)
        self.assertEqual(data["incidents"]["total"], 4)
        self.assertEqual(data["incidents"]["by_status"], {"open": 2, "investigating": 1, "resolved": 1})
        self.assertEqual(data["incidents"]["by_severity"], dict.fromkeys(("low", "medium", "high", "critical"), 1))
        self.assertEqual((data["incidents"]["pending"]["total"], data["incidents"]["pending"]["unassigned"]), (3, 2))
        self.assertEqual(data["assets"], {"total": 4, "by_criticality": dict.fromkeys(("low", "medium", "high", "critical"), 1)})
        self.assertEqual(data["risks"]["total"], 4)
        self.assertEqual(data["risks"]["by_level"], dict.fromkeys(("low", "medium", "high", "critical"), 1))
        self.assertEqual(data["risks"]["by_status"], {"identified": 2, "treating": 1, "accepted": 1})
        self.assertEqual(data["risks"]["unassigned_pending"], 2)
        self.assertEqual(data["controls"], {"total": 3, "by_status": {"planned": 1, "implemented": 1, "retired": 1}})

    def test_recent_pending_selection_and_stable_date_id_order(self):
        incidents = [self.create("/incidents", self.payload(status="investigating" if n % 2 else "open")) for n in range(8)]
        resolved = self.create("/incidents", self.payload(status="resolved"))
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("UPDATE incidents SET created_at = '2026-01-01T00:00:00+00:00'")
            connection.execute("UPDATE incidents SET created_at = '2026-02-01T00:00:00+00:00' WHERE id = ?", (incidents[0]["id"],))
        data = self.summary()["incidents"]
        expected = [incidents[0]["id"]] + [i["id"] for i in reversed(incidents[-4:])]
        self.assertEqual([i["id"] for i in data["pending"]["recent"]], expected)
        self.assertEqual((data["total"], data["pending"]["total"], data["pending"]["unassigned"]), (9, 8, 8))
        self.assertNotIn(resolved["id"], expected)
        self.assertTrue(all(set(i) == {"id", "title", "status", "severity", "created_at"} for i in data["pending"]["recent"]))
        self.assertEqual(self.summary()["incidents"], data)

    def test_priority_score_boundaries_and_stable_id_order(self):
        rows = [self.create("/risks", self.risk_payload(probability=p, impact=i, status=state)) for p, i, state in
                ((1, 1, "identified"), (1, 4, "identified"), (1, 5, "identified"), (3, 3, "treating"),
                 (2, 5, "identified"), (4, 4, "treating"), (4, 5, "identified"), (5, 5, "accepted"),
                 (5, 4, "treating"), (5, 4, "identified"))]
        data = self.summary()["risks"]
        expected = [rows[n]["id"] for n in (9, 8, 6, 5, 4)]
        self.assertEqual([r["id"] for r in data["priority"]], expected)
        self.assertEqual([r["score"] for r in data["priority"]], [20, 20, 20, 16, 10])
        self.assertEqual(data["by_level"], {"low": 2, "medium": 2, "high": 2, "critical": 4})
        self.assertEqual(data["unassigned_pending"], 9)
        self.assertTrue(all(set(r) == {"id", "title", "status", "probability", "impact", "score", "level", "created_at"} for r in data["priority"]))
        self.assertEqual(self.summary()["risks"], data)
        for row in data["priority"]:
            self.assertEqual(row["score"], row["probability"] * row["impact"])
            self.assertEqual(row["level"], fixtures.app_main.risk_level(row["score"]))

    def test_auth_roles_isolation_and_no_user_or_audit_data(self):
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        self.assertEqual(self.request("GET", "/dashboard", client=anonymous)[0], 401)
        for role in ("analista", "lector"):
            self.create("/users", {"display_name": "PRIVATE user", "email": role + "@example.test", "role": role, "password": "dashboard role password"})
        self.create("/incidents", self.payload(title="Own incident", description="PRIVATE description"))
        self.create("/risks", self.risk_payload(title="Own risk", description="PRIVATE description"))
        self.create("/assets", self.asset_payload())
        self.create("/controls", self.control_payload())
        expected = self.without_time(self.summary())
        for role in ("analista", "lector"):
            client = self.login_client(role + "@example.test", "dashboard role password")
            data = self.summary(client)
            self.assertEqual(self.without_time(data), expected)
            for forbidden in ("PRIVATE", "audit_logs", "actor_name", "email", "password", "users", "csrf", "token"):
                self.assertNotIn(forbidden, json.dumps(data))
        foreign = self.second_organization()
        self.assertTrue(all(self.summary(foreign)[name]["total"] == 0 for name in ("incidents", "assets", "risks", "controls")))
        for _ in range(2):
            self.create("/incidents", self.payload(title="Foreign incident"), foreign)
            self.create("/risks", self.risk_payload(title="Foreign risk", probability=5, impact=5), foreign)
            self.create("/assets", self.asset_payload(), foreign)
            self.create("/controls", self.control_payload(), foreign)
        self.assertEqual(self.without_time(self.summary(query="?organization_id=2&actor_id=2")), expected)
        self.assertNotIn("Foreign", json.dumps(self.summary()))
        foreign_data = self.summary(foreign, "?organization_id=1%27%20OR%201=1--")
        self.assertTrue(all(foreign_data[name]["total"] == 2 for name in ("incidents", "assets", "risks", "controls")))
        self.assertNotIn("Own", json.dumps(foreign_data))
        for role in ("analista", "lector"):
            client = self.login_client(role + "@example.test", "dashboard role password")
            self.assertEqual(self.without_time(self.summary(client)), expected)

    def test_all_queries_share_one_snapshot_under_concurrent_writes(self):
        # WAL permits a writer to commit between summary SELECTs while the reader
        # retains its original snapshot. This verifies the explicit BEGIN matters.
        with closing(fixtures.app_main.connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        test = self
        interleaved = False
        statements = []

        class InterleavingConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                nonlocal interleaved
                statements.append((sql, parameters))
                cursor = super().execute(sql, parameters)
                if "FROM incidents" in sql and not interleaved:
                    interleaved = True
                    for path, body in (("/incidents", test.payload()), ("/assets", test.asset_payload()),
                                       ("/risks", test.risk_payload()), ("/controls", test.control_payload())):
                        test.create(path, body)
                return cursor

        def connect():
            connection = sqlite3.connect(self.database, factory=InterleavingConnection)
            connection.row_factory = sqlite3.Row
            return connection

        with patch.object(fixtures.app_main, "connect", connect):
            data = fixtures.app_main.dashboard({"organization_id": 1})
        self.assertTrue(interleaved)
        self.assertEqual(statements[0][0], "BEGIN")
        for sql, parameters in statements[1:]:
            self.assertIn("organization_id = ?", sql)
            self.assertEqual(parameters, (1,))
        self.assertTrue(all(data[name]["total"] == 0 for name in ("incidents", "assets", "risks", "controls")))
        self.assertTrue(all(self.summary()[name]["total"] == 1 for name in ("incidents", "assets", "risks", "controls")))


if __name__ == "__main__":
    unittest.main()
