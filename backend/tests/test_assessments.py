"""Manual residual risk estimates and immutable original-value comparisons."""
from contextlib import closing
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import sqlite3
import unittest
from urllib.request import HTTPCookieProcessor, build_opener

import test_incidents as fixtures
import test_risks as risks
import test_controls as controls
import test_audit as audit


class AssessmentTests(unittest.TestCase):
    setUp = fixtures.IncidentTests.setUp
    start_server = fixtures.IncidentTests.start_server
    stop_server = fixtures.IncidentTests.stop_server
    seed_admin = fixtures.IncidentTests.seed_admin
    request = fixtures.IncidentTests.request
    login_client = fixtures.IncidentTests.login_client
    risk_payload = risks.RiskTests.risk_payload
    control_payload = controls.ControlTests.control_payload
    second_organization = risks.RiskTests.second_organization
    snapshot = audit.AuditTests.snapshot
    fail_audit = audit.AuditTests.fail_audit
    failed_request = audit.AuditTests.failed_request
    events = audit.AuditTests.events

    def risk(self, **changes):
        code, risk = self.request("POST", "/risks", self.risk_payload(**changes))
        self.assertEqual(code, 201)
        return risk

    def body(self, **changes):
        return {"residual_probability": 2, "residual_impact": 3, "justification": "Manual estimate"} | changes

    def assess(self, risk, body=None, client=None):
        code, result = self.request("POST", f'/risks/{risk["id"]}/assessments', body or self.body(), client=client)
        self.assertEqual(code, 201)
        return result

    def history(self, risk, client=None):
        code, result = self.request("GET", f'/risks/{risk["id"]}/assessments', client=client)
        self.assertEqual(code, 200)
        return result

    def test_all_scores_limits_higher_values_and_original_unchanged(self):
        risk = self.risk(probability=1, impact=1)
        self.assertEqual(self.history(risk), [])
        for probability in range(1, 6):
            for impact in range(1, 6):
                assessment = self.assess(risk, self.body(residual_probability=probability, residual_impact=impact, justification="  Justification  "))
                self.assertEqual(assessment["residual_score"], probability * impact)
                self.assertEqual(assessment["residual_level"], fixtures.app_main.risk_level(probability * impact))
                self.assertEqual((assessment["original_probability"], assessment["original_impact"], assessment["original_score"], assessment["original_level"]), (1, 1, 1, "low"))
                self.assertEqual(assessment["justification"], "Justification")
                self.assertEqual((assessment["risk_id"], assessment["evaluator_id"], assessment["evaluator_name"]), (risk["id"], 1, "Test Administrator"))
                self.assertEqual(datetime.fromisoformat(assessment["created_at"]).utcoffset(), timezone.utc.utcoffset(None))
                self.assertNotIn("organization_id", assessment)
        self.assertEqual(len(self.history(risk)), 25)
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}')[1], risk)
        summary = self.request("GET", "/dashboard")[1]
        self.assertEqual(summary["risks"]["priority"][0]["score"], 1)
        self.assertEqual(summary["risks"]["by_level"]["low"], 1)

    def test_validation_required_strict_numbers_extras_and_text_limits(self):
        risk = self.risk()
        invalid = [{}, {"residual_probability": 2}, {"residual_probability": 2, "residual_impact": 3}]
        invalid += [self.body(**{field: value}) for field in ("residual_probability", "residual_impact")
                    for value in (True, False, 0, 6, -1, "3", 1.0, 1.5, None)]
        invalid += [self.body(justification=value) for value in ("", " \n\t ", "x" * 5001, None, True, 12)]
        invalid += [self.body(**{field: value}) for field, value in (("id", 99), ("risk_id", 99), ("organization_id", 1),
                    ("evaluator_id", 1), ("evaluator_name", "Injected"), ("actor_id", 1), ("created_at", "2026-01-01"),
                    ("original_probability", 1), ("original_impact", 1), ("original_score", 1), ("original_level", "low"),
                    ("residual_score", 1), ("residual_level", "low"), ("score", 1), ("level", "low"))]
        before = self.events()
        for body in invalid:
            self.assertEqual(self.request("POST", f'/risks/{risk["id"]}/assessments', body)[0], 422, str(body)[:100])
        self.assertEqual(self.request("POST", f'/risks/{risk["id"]}/assessments')[0], 422)
        self.assertEqual(self.history(risk), [])
        self.assertEqual(self.events(), before)
        for justification in ("x", "x" * 5000, "  x  "):
            self.assertEqual(self.assess(risk, self.body(justification=justification))["justification"], justification.strip())

    def test_roles_csrf_and_tenant_isolation(self):
        risk = self.risk()
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        foreign = self.second_organization()
        code, foreign_risk = self.request("POST", "/risks", self.risk_payload(), client=foreign)
        self.assertEqual(code, 201)
        for role in ("analista", "lector"):
            code, _ = self.request("POST", "/users", {"display_name": role, "email": role + "@example.test", "role": role, "password": "residual user password"})
            self.assertEqual(code, 201)
        analyst = self.login_client("analista@example.test", "residual user password")
        reader = self.login_client("lector@example.test", "residual user password")
        for method in ("GET", "POST"):
            body = self.body() if method == "POST" else None
            self.assertEqual(self.request(method, f'/risks/{risk["id"]}/assessments', body, client=anonymous)[0], 401)
            self.assertEqual(self.request(method, f'/risks/{risk["id"]}/assessments', body, client=foreign)[0], 404)
            self.assertEqual(self.request(method, f'/risks/{foreign_risk["id"]}/assessments', body)[0], 404)
            self.assertEqual(self.request(method, '/risks/999999/assessments', body)[0], 404)
        self.assertEqual(self.request("POST", f'/risks/{risk["id"]}/assessments', self.body(), client=reader)[0], 403)
        self.assertEqual(self.request("POST", f'/risks/{risk["id"]}/assessments', self.body(), send_csrf=False)[0], 403)
        self.assertEqual(self.request("POST", f'/risks/{risk["id"]}/assessments', self.body(), client=(self.opener, "bad csrf"))[0], 403)
        self.assertEqual(self.history(risk), [])
        own = self.assess(risk, client=analyst)
        other = self.assess(foreign_risk, client=foreign)
        self.assertEqual(self.history(risk, reader), [own])
        self.assertEqual(self.history(foreign_risk, foreign), [other])
        self.assertNotEqual(own["evaluator_id"], other["evaluator_id"])
        self.assertEqual(self.events(action="assessed")[0]["actor_id"], own["evaluator_id"])
        for method in ("PATCH", "PUT", "DELETE"):
            for path in (f'/risks/{risk["id"]}/assessments', f'/risks/{risk["id"]}/assessments/{own["id"]}'):
                self.assertIn(self.request(method, path, {})[0], (404, 405))

    def test_history_snapshots_actor_identity_and_persistence(self):
        risk = self.risk()
        first = self.assess(risk)
        self.request("PATCH", f'/risks/{risk["id"]}', {"probability": 5, "impact": 5})
        self.request("PATCH", "/users/1", {"display_name": "Renamed evaluator"})
        second = self.assess(risk, self.body(residual_probability=5, residual_impact=4))
        self.assertEqual((second["original_probability"], second["original_impact"], second["original_score"]), (5, 5, 25))
        self.assertEqual(second["evaluator_name"], "Renamed evaluator")
        self.assertEqual(self.history(risk), [second, first])
        self.assertEqual(first["original_score"], 12)
        self.assertEqual(first["evaluator_name"], "Test Administrator")
        third = self.assess(risk, self.body(residual_probability=5, residual_impact=4))
        self.assertEqual(self.history(risk), [third, second, first])
        self.assertNotEqual(third["id"], second["id"])
        # Stable ID tie-break and explicit date precedence.
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("UPDATE risk_assessments SET created_at = '2026-01-01T00:00:00+00:00'")
        tied = self.history(risk)
        self.assertEqual([a["id"] for a in tied], [third["id"], second["id"], first["id"]])
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("UPDATE risk_assessments SET created_at = '2026-02-01T00:00:00+00:00' WHERE id = ?", (first["id"],))
        before = self.history(risk)
        self.assertEqual(before[0]["id"], first["id"])
        self.stop_server(); self.start_server()
        self.assertEqual(self.history(risk), before)

    def test_minimal_audit_and_atomic_rollback(self):
        risk = self.risk()
        control = self.request("POST", "/controls", self.control_payload())[1]
        self.request("POST", f'/risks/{risk["id"]}/controls', {"control_id": control["id"]})
        self.request("PATCH", f'/risks/{risk["id"]}/assignee', {"assignee_id": 1})
        before = self.snapshot()
        assessment = self.assess(risk, self.body(justification="SECRET justification <script>unsafe</script>"))
        event = self.events(action="assessed")[0]
        self.assertEqual(event["details"], {"assessment_id": assessment["id"], "original_probability": 3,
                         "original_impact": 4, "original_score": 12, "residual_probability": 2, "residual_impact": 3, "residual_score": 6})
        self.assertEqual((event["resource_type"], event["resource_id"], event["organization_id"]), ("risk", risk["id"], 1))
        for secret in ("SECRET", "justification", "password", "csrf", "token", "<script>"):
            self.assertNotIn(secret, json.dumps(event))
        after = self.snapshot()
        for table in before:
            if table not in ("risk_assessments", "audit_logs", "sqlite_sequence"):
                self.assertEqual(after[table], before[table], table)
        self.fail_audit("NEW.action = 'assessed'")
        before = self.snapshot()
        self.failed_request("POST", f'/risks/{risk["id"]}/assessments', self.body())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.history(risk), [assessment])
        self.request("PATCH", f'/controls/{control["id"]}', {"status": "implemented"})
        self.assertEqual(self.history(risk), [assessment])
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}')[1]["score"], 12)

    def test_database_guards_tenant_relationships_and_numeric_snapshot(self):
        risk = self.risk()
        foreign = self.second_organization()
        foreign_risk = self.request("POST", "/risks", self.risk_payload(), client=foreign)[1]
        assessment = self.assess(risk)
        with closing(fixtures.app_main.connect()) as connection:
            foreign_id = connection.execute("SELECT id FROM users WHERE organization_id = 2").fetchone()[0]
            for column, value in (("organization_id", 2), ("risk_id", foreign_risk["id"]), ("evaluator_id", foreign_id),
                                  ("residual_probability", 0), ("residual_impact", 6), ("residual_probability", 1.5),
                                  ("original_probability", 0), ("original_impact", 6), ("original_score", 1),
                                  ("justification", ""), ("justification", "x" * 5001), ("justification", " padded ")):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"UPDATE risk_assessments SET {column} = ? WHERE id = ?", (value, assessment["id"]))
                connection.rollback()
            for table, id in (("risks", risk["id"]), ("users", 1)):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"UPDATE {table} SET organization_id = 2 WHERE id = ?", (id,))
                connection.rollback()
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_versioned_migration_preserves_all_data_and_audit_sequences(self):
        risk = self.risk()
        self.request("POST", "/controls", self.control_payload())
        self.stop_server()
        with closing(fixtures.app_main.connect()) as connection, connection:
            fixtures.rewind_assessment_migration(connection)
            # Restore the pre-011 action CHECK and preserve events.
            events = [tuple(row) for row in connection.execute("SELECT * FROM audit_logs ORDER BY id")]
            connection.execute("DROP TABLE audit_logs")
            script = (fixtures.BACKEND / "migrations/009_audit_logs.sql").read_text(encoding="utf-8").replace("'user_updated'))", "'user_updated', 'updated'))")
            connection.executescript(script)
            connection.executemany("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", events)
            connection.execute("UPDATE sqlite_sequence SET seq = 800 WHERE name = 'audit_logs'")
        before = self.snapshot()
        fixtures.app_main.migrate_database()
        after = self.snapshot()
        for table, rows in before.items():
            self.assertEqual(after[table][:-1] if table == "schema_migrations" else after[table], rows, table)
        self.assertEqual(after["risk_assessments"], [])
        fixtures.app_main.migrate_database()
        self.assertEqual(self.snapshot(), after)
        self.start_server()
        self.assertEqual(self.history(risk), [])
        self.assess(risk)
        self.assertEqual(self.events()[0]["id"], 801)


if __name__ == "__main__":
    unittest.main()
