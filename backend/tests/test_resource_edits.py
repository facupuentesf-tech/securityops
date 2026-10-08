"""Partial resource edits, transactional auditing and migration preservation."""
from contextlib import closing
from http.cookiejar import CookieJar
import json
import sqlite3
import unittest
from urllib.request import HTTPCookieProcessor, build_opener

import test_incidents as fixtures
import test_risks as risks
import test_controls as controls
import test_audit as audit


class ResourceEditTests(unittest.TestCase):
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
    snapshot = audit.AuditTests.snapshot
    fail_audit = audit.AuditTests.fail_audit
    failed_request = audit.AuditTests.failed_request
    events = audit.AuditTests.events

    def create(self, path, body, client=None):
        code, result = self.request("POST", path, body, client=client)
        self.assertEqual(code, 201)
        return result

    def resources(self):
        return {"assets": self.create("/assets", self.asset_payload(description="Original asset description")),
                "risks": self.create("/risks", self.risk_payload(description="Original risk description")),
                "controls": self.create("/controls", self.control_payload(description="Original control description"))}

    def edit(self, kind, original, changes, client=None):
        code, result = self.request("PATCH", f'/{kind}/{original["id"]}', changes, client=client)
        self.assertEqual(code, 200)
        return result

    def test_partial_full_null_and_server_recalculation(self):
        original = self.resources()
        for kind, resource in original.items():
            field = "title" if kind == "risks" else "name"
            updated = self.edit(kind, resource, {field: "  New name  "})
            self.assertEqual(updated, resource | {field: "New name"})
            cleared = self.edit(kind, updated, {"description": None})
            self.assertEqual(cleared, updated | {"description": None})
            empty = self.edit(kind, cleared, {"description": ""})
            self.assertEqual(empty["description"], "")
        asset = self.edit("assets", original["assets"], {"type": "data", "criticality": "critical", "description": "Updated description"})
        self.assertEqual((asset["type"], asset["criticality"]), ("data", "critical"))
        risk = self.edit("risks", original["risks"], {"probability": 5, "impact": 4, "status": "treating", "asset_id": asset["id"]})
        self.assertEqual((risk["score"], risk["level"], risk["asset_id"], risk["asset_name"]), (20, "critical", asset["id"], "New name"))
        self.assertIsNone(risk["assignee_id"])
        risk = self.edit("risks", risk, {"probability": 1})
        self.assertEqual((risk["score"], risk["level"], risk["impact"]), (4, "low", 4))
        risk = self.edit("risks", risk, {"asset_id": None})
        self.assertIsNone(risk["asset_id"]); self.assertIsNone(risk["asset_name"])
        control = self.edit("controls", original["controls"], {"type": "preventive", "status": "implemented"})
        self.assertEqual((control["type"], control["status"]), ("preventive", "implemented"))
        for kind, resource in original.items():
            current = self.request("GET", f'/{kind}/{resource["id"]}')[1]
            self.assertEqual(current["id"], resource["id"])
            self.assertEqual(current["created_at"], resource["created_at"])
            self.assertEqual(self.request("GET", "/" + kind)[1], [current])

    def test_validation_empty_unknown_protected_and_invalid_null(self):
        for kind, original in self.resources().items():
            field = "title" if kind == "risks" else "name"
            invalid = [{}, {field: ""}, {field: "  "}, {field: None}, {field: 42}, {"description": 12},
                       {"unknown": 1}, {"id": 1}, {"organization_id": 1}, {"created_at": "2026-01-01"},
                       {"assignee_id": None}, {"assignee_name": "Unauthorized"}, {"score": 1}, {"level": "low"}]
            if kind == "risks":
                invalid += [{key: value} for key in ("probability", "impact") for value in (None, True, False, 0, 6, 1.0, 1.5, "3")]
                invalid += [{"asset_id": v} for v in (True, False, 0, -1, 1.5, "1")]
                invalid += [{"status": v} for v in (None, "open", "", 12)]
            else:
                invalid += [{"type": v} for v in (None, "invalid", "", 12)]
                key = "criticality" if kind == "assets" else "status"
                invalid += [{key: v} for v in (None, "invalid", "", 12)]
            before = self.events()
            for body in invalid:
                with self.subTest(kind=kind, body=body):
                    self.assertEqual(self.request("PATCH", f'/{kind}/{original["id"]}', body)[0], 422)
                    self.assertEqual(self.request("GET", f'/{kind}/{original["id"]}')[1], original)
            self.assertEqual(self.request("PATCH", f'/{kind}/{original["id"]}')[0], 422)
            self.assertEqual(self.events(), before)

    def test_roles_csrf_isolation_missing_resources_and_associated_assets(self):
        resources = self.resources()
        for role in ("analista", "lector"):
            self.create("/users", {"display_name": role, "email": role + "@example.test", "role": role, "password": "resource edit password"})
        analyst = self.login_client("analista@example.test", "resource edit password")
        reader = self.login_client("lector@example.test", "resource edit password")
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        foreign = self.second_organization()
        foreign_asset = self.create("/assets", self.asset_payload(), foreign)
        for kind, original in resources.items():
            field = "title" if kind == "risks" else "name"
            body = {field: "Analyst edited"}
            before = self.events()
            for client, expected in ((anonymous, 401), (reader, 403), (foreign, 404)):
                self.assertEqual(self.request("PATCH", f'/{kind}/{original["id"]}', body, client=client)[0], expected)
            self.assertEqual(self.request("PATCH", f'/{kind}/{original["id"]}', body, send_csrf=False)[0], 403)
            self.assertEqual(self.request("PATCH", f'/{kind}/{original["id"]}', body, client=(self.opener, "bad csrf"))[0], 403)
            self.assertEqual(self.request("PATCH", f'/{kind}/999999', body)[0], 404)
            self.assertEqual(self.events(), before)
            self.edit(kind, original, body, analyst)
            self.assertEqual(self.events()[0]["actor_id"], 2)
            foreign_resource = self.create('/' + kind, {"assets": self.asset_payload(), "risks": self.risk_payload(), "controls": self.control_payload()}[kind], foreign)
            self.assertEqual(self.request("PATCH", f'/{kind}/{foreign_resource["id"]}', body)[0], 404)
        risk = resources["risks"]
        before = self.events()
        for asset_id in (999999, foreign_asset["id"]):
            self.assertEqual(self.request("PATCH", f'/risks/{risk["id"]}', {"asset_id": asset_id, "probability": 5})[0], 404)
        self.assertEqual(self.events(), before)
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}')[1]["probability"], risk["probability"])

    def test_audit_minimal_details_noop_and_normalized_text(self):
        original = self.resources()
        changes = {"assets": {"name": "SECRET asset name", "description": "SECRET asset description", "type": "data", "criticality": "critical"},
                   "risks": {"title": "SECRET risk title", "description": "SECRET risk description", "probability": 5, "impact": 5, "status": "accepted", "asset_id": original["assets"]["id"]},
                   "controls": {"name": "SECRET control name", "description": "SECRET control description", "type": "detective", "status": "implemented"}}
        for kind, resource in original.items():
            before = len(self.events())
            updated = self.edit(kind, resource, changes[kind])
            event = self.events()[0]
            self.assertEqual(len(self.events()), before + 1)
            self.assertEqual((event["action"], event["resource_type"], event["resource_id"], event["actor_id"], event["organization_id"]),
                             ("updated", {"assets": "asset", "risks": "risk", "controls": "control"}[kind], resource["id"], 1, 1))
            expected = {}
            for field, value in changes[kind].items():
                if field in ("name", "title", "description"):
                    expected[field + "_changed"] = True
                else:
                    expected["previous_" + field] = resource[field]; expected["new_" + field] = value
            self.assertEqual(event["details"], expected)
            self.assertNotIn("SECRET", json.dumps(event))
            self.assertNotIn("SECRET", str(self.snapshot()["audit_logs"]))
            before_events = self.events()
            self.edit(kind, updated, changes[kind])
            text_field = "title" if kind == "risks" else "name"
            self.edit(kind, updated, {text_field: "  " + updated[text_field] + "  "})
            self.assertEqual(self.events(), before_events)
            self.edit(kind, updated, {"description": None})
            self.assertEqual(self.events()[0]["details"], {"description_changed": True})
            before_events = self.events()
            self.edit(kind, updated, {"description": None})
            self.assertEqual(self.events(), before_events)
        own_edits = self.events(action="updated", resource_type="risk")
        self.assertEqual(len(own_edits), 2)

    def test_links_assignees_created_dates_dashboard_and_control_no_score_reduction(self):
        original = self.resources()
        asset, risk, control = (original[k] for k in ("assets", "risks", "controls"))
        incident = self.create("/incidents", self.payload())
        self.create(f'/incidents/{incident["id"]}/assets', {"asset_id": asset["id"]})
        other_control = self.create("/controls", self.control_payload())
        for target in (control, other_control):
            self.create(f'/risks/{risk["id"]}/controls', {"control_id": target["id"]})
        self.request("PATCH", f'/risks/{risk["id"]}/assignee', {"assignee_id": 1})
        self.edit("risks", risk, {"asset_id": asset["id"]})
        before = self.snapshot()
        self.edit("assets", asset, {"name": "Updated asset", "criticality": "critical"})
        self.edit("controls", control, {"status": "implemented"})
        unchanged_risk = self.request("GET", f'/risks/{risk["id"]}')[1]
        self.assertEqual((unchanged_risk["score"], unchanged_risk["level"]), (risk["score"], risk["level"]))
        self.assertEqual(unchanged_risk["asset_name"], "Updated asset")
        updated = self.edit("risks", risk, {"probability": 5, "impact": 5, "status": "treating"})
        self.assertEqual((updated["score"], updated["level"], updated["assignee_id"], updated["asset_id"]), (25, "critical", 1, asset["id"]))
        after = self.snapshot()
        for table in ("incident_assets", "risk_controls", "incidents", "users", "sessions", "incident_notes", "incident_status_history"):
            self.assertEqual(after[table], before[table], table)
        self.assertEqual([c["id"] for c in self.request("GET", f'/risks/{risk["id"]}/controls')[1]], [control["id"], other_control["id"]])
        summary = self.request("GET", "/dashboard")[1]
        self.assertEqual(summary["risks"]["by_level"]["critical"], 1)
        self.assertEqual(summary["risks"]["priority"][0]["score"], 25)
        self.assertEqual(summary["assets"]["by_criticality"]["critical"], 1)
        self.assertEqual(summary["controls"]["by_status"]["implemented"], 1)
        self.stop_server(); self.start_server()
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}')[1], updated)

    def test_insert_failure_rolls_back_each_edit_and_related_data(self):
        original = self.resources()
        risk, asset, control = original["risks"], original["assets"], original["controls"]
        self.create(f'/risks/{risk["id"]}/controls', {"control_id": control["id"]})
        self.request("PATCH", f'/risks/{risk["id"]}/assignee', {"assignee_id": 1})
        self.fail_audit("NEW.action = 'updated'")
        before = self.snapshot()
        for kind, changes in (("assets", {"name": "Fail", "description": None, "criticality": "critical"}),
                              ("risks", {"probability": 5, "impact": 5, "status": "treating", "asset_id": asset["id"]}),
                              ("controls", {"name": "Fail", "type": "detective", "status": "implemented"})):
            self.failed_request("PATCH", f'/{kind}/{original[kind]["id"]}', changes)
            self.assertEqual(self.snapshot(), before)
        # No-op edits need no insert even when audit inserts are broken.
        for kind, resource in original.items():
            field = "title" if kind == "risks" else "name"
            self.edit(kind, resource, {field: resource[field]})
            self.assertEqual(self.snapshot(), before)

    def test_migration_preserves_all_tables_events_and_sequence_high_water_mark(self):
        self.resources()
        before_events = self.events()
        self.stop_server()
        with closing(fixtures.app_main.connect()) as connection, connection:
            rows = [tuple(row) for row in connection.execute("SELECT * FROM audit_logs ORDER BY id")]
            connection.execute("DROP TABLE audit_logs")
            connection.executescript((fixtures.BACKEND / "migrations/009_audit_logs.sql").read_text(encoding="utf-8"))
            connection.executemany("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            connection.execute("UPDATE sqlite_sequence SET seq = 900 WHERE name = 'audit_logs'")
            connection.execute("DELETE FROM schema_migrations WHERE version = 10")
        before = self.snapshot()
        fixtures.app_main.migrate_database()
        after = self.snapshot()
        for table, rows in before.items():
            self.assertEqual(after[table][:-1] if table == "schema_migrations" else after[table], rows, table)
        fixtures.app_main.migrate_database()
        self.assertEqual(self.snapshot(), after)
        self.start_server()
        self.assertEqual(self.events(), before_events)
        asset = self.request("GET", "/assets")[1][0]
        self.edit("assets", asset, {"criticality": "critical"})
        self.assertEqual(self.events()[0]["id"], 901)


if __name__ == "__main__":
    unittest.main()

