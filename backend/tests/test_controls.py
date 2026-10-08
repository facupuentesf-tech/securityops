from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import sqlite3
import unittest
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, build_opener

import test_incidents as fixtures
import test_risks as risk_fixtures


class ControlTests(unittest.TestCase):
    setUp = fixtures.IncidentTests.setUp
    start_server = fixtures.IncidentTests.start_server
    stop_server = fixtures.IncidentTests.stop_server
    seed_admin = fixtures.IncidentTests.seed_admin
    request = fixtures.IncidentTests.request
    login_client = fixtures.IncidentTests.login_client
    payload = fixtures.IncidentTests.payload
    asset_payload = fixtures.IncidentTests.asset_payload
    risk_payload = risk_fixtures.RiskTests.risk_payload
    second_organization = risk_fixtures.RiskTests.second_organization

    def control_payload(self, **changes):
        return {"name": "Backup procedure", "type": "corrective"} | changes

    def test_creation_queries_optional_description_and_sql_parameters(self):
        self.assertEqual(self.request("GET", "/controls"), (200, []))
        code, control = self.request("POST", "/controls", self.control_payload(name="  O'Brien'); DROP TABLE risks; --  "))
        self.assertEqual(code, 201)
        self.assertEqual(control["name"], "O'Brien'); DROP TABLE risks; --")
        self.assertEqual(control["status"], "planned")
        self.assertIsNone(control["description"])
        self.assertNotIn("organization_id", control)
        self.assertEqual(datetime.fromisoformat(control["created_at"]).utcoffset(), timezone.utc.utcoffset(None))
        self.assertEqual(self.request("GET", f'/controls/{control["id"]}'), (200, control))
        self.assertEqual(self.request("GET", "/controls"), (200, [control]))
        for description in (None, "", "<script>alert(1)</script>", "O'Brien'); DROP TABLE security_controls; --"):
            code, created = self.request("POST", "/controls", self.control_payload(description=description))
            self.assertEqual(code, 201)
            self.assertEqual(created["description"], description)
        self.assertEqual(self.request("GET", "/controls/999999")[0], 404)
        self.assertEqual(self.request("GET", "/controls/not-an-id")[0], 422)

    def test_filters_all_types_states_and_and_combinations(self):
        controls = []
        for type in ("preventive", "detective", "corrective"):
            for status in ("planned", "implemented", "retired"):
                code, control = self.request("POST", "/controls", self.control_payload(type=type, status=status))
                self.assertEqual(code, 201)
                controls.append(control)
        queries = [{"type": type} for type in ("preventive", "detective", "corrective")]
        queries += [{"status": status} for status in ("planned", "implemented", "retired")]
        queries += [{"type": type, "status": status} for type in ("preventive", "detective", "corrective")
                    for status in ("planned", "implemented", "retired")]
        for query in queries:
            self.assertEqual(self.request("GET", "/controls?" + urlencode(query)),
                             (200, [control for control in controls if all(control[key] == value for key, value in query.items())]))
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("DELETE FROM security_controls WHERE type = ? AND status = ?", ("corrective", "retired"))
        self.assertEqual(self.request("GET", "/controls?type=corrective&status=retired"), (200, []))

    def test_creation_and_link_validation(self):
        invalid = [{"name": value} for value in ("", " ", "\t\n", None, True, 1)]
        invalid += [{field: value} for field in ("type", "status") for value in (None, True, "", "invalid", "x'); DROP TABLE risks; --")]
        invalid += [{"description": value} for value in (True, 1, [], {})]
        invalid += [{"organization_id": 1}, {"id": 42}, {"created_at": "2026-01-01"}]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(self.request("POST", "/controls", self.control_payload(**changes))[0], 422)
        for field in ("name", "type"):
            body = self.control_payload(); del body[field]
            self.assertEqual(self.request("POST", "/controls", body)[0], 422)
        self.assertEqual(self.request("POST", "/controls")[0], 422)
        for query in ("type=invalid", "status=invalid", "type=", "status=", "type=preventive%27%20OR%201=1--"):
            self.assertEqual(self.request("GET", "/controls?" + query)[0], 422)
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        path = f'/risks/{risk["id"]}/controls'
        for body in ({}, {"control_id": None}, {"control_id": True}, {"control_id": False},
                     {"control_id": 0}, {"control_id": -1}, {"control_id": 1.5}, {"control_id": 1.0},
                     {"control_id": "1"}, {"control_id": 1, "organization_id": 1}):
            self.assertEqual(self.request("POST", path, body)[0], 422)
        self.assertEqual(self.request("POST", path)[0], 422)
        self.assertEqual(self.request("GET", path), (200, []))

    def test_many_to_many_duplicates_unlink_and_unchanged_risk(self):
        risks = [self.request("POST", "/risks", self.risk_payload())[1] for _ in range(2)]
        controls = [self.request("POST", "/controls", self.control_payload(name=name))[1] for name in ("Backup", "Monitoring")]
        path = f'/risks/{risks[0]["id"]}/controls'
        second_path = f'/risks/{risks[1]["id"]}/controls'
        self.assertEqual(self.request("GET", path), (200, []))
        for control in reversed(controls):
            self.assertEqual(self.request("POST", path, {"control_id": control["id"]}),
                             (201, {"risk_id": risks[0]["id"], "control_id": control["id"]}))
            self.assertEqual(self.request("POST", path, {"control_id": control["id"]})[0], 409)
        self.assertEqual(self.request("GET", path), (200, controls))
        self.assertEqual(self.request("POST", second_path, {"control_id": controls[0]["id"]})[0], 201)
        self.assertEqual(self.request("GET", f'/risks/{risks[0]["id"]}'), (200, risks[0]))
        self.assertEqual(self.request("DELETE", path + f'/{controls[0]["id"]}'), (204, None))
        self.assertEqual(self.request("DELETE", path + f'/{controls[0]["id"]}')[0], 404)
        self.assertEqual(self.request("GET", path), (200, [controls[1]]))
        self.assertEqual(self.request("GET", second_path), (200, [controls[0]]))
        self.assertEqual(self.request("GET", "/controls"), (200, controls))
        for risk in risks:
            self.assertEqual(self.request("GET", f'/risks/{risk["id"]}'), (200, risk))

    def test_concurrent_duplicate_link_is_conflict(self):
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        control = self.request("POST", "/controls", self.control_payload())[1]
        clients = [self.login_client("admin@example.test", "correct horse battery") for _ in range(2)]
        path = f'/risks/{risk["id"]}/controls'
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda client: self.request("POST", path, {"control_id": control["id"]}, client=client)[0], clients))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(self.request("GET", path), (200, [control]))

    def test_permissions_authentication_and_csrf_on_all_routes(self):
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        control = self.request("POST", "/controls", self.control_payload())[1]
        path = f'/risks/{risk["id"]}/controls'
        body = {"control_id": control["id"]}
        routes = (("GET", "/controls", None), ("GET", f'/controls/{control["id"]}', None),
                  ("POST", "/controls", self.control_payload()), ("GET", path, None),
                  ("POST", path, body), ("DELETE", path + f'/{control["id"]}', None))
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        for method, route, payload in routes:
            self.assertEqual(self.request(method, route, payload, client=anonymous)[0], 401)
            if method != "GET":
                self.assertEqual(self.request(method, route, payload, send_csrf=False)[0], 403)
                self.assertEqual(self.request(method, route, payload, client=(self.opener, "invalid"))[0], 403)
        for role in ("analista", "lector"):
            self.assertEqual(self.request("POST", "/users", {"display_name": role, "email": f"{role}@example.test",
                             "password": "control user password", "role": role})[0], 201)
        analyst = self.login_client("analista@example.test", "control user password")
        reader = self.login_client("lector@example.test", "control user password")
        for method, route, payload in routes:
            if method != "GET":
                self.assertEqual(self.request(method, route, payload, client=reader)[0], 403)
        self.assertEqual(self.request("POST", "/controls", self.control_payload(), client=analyst)[0], 201)
        self.assertEqual(self.request("POST", path, body, client=analyst)[0], 201)
        for client in (analyst, reader):
            self.assertEqual(self.request("GET", f'/controls/{control["id"]}', client=client), (200, control))
            self.assertEqual(self.request("GET", path, client=client), (200, [control]))
            self.assertEqual(len(self.request("GET", "/controls", client=client)[1]), 2)
        self.assertEqual(self.request("DELETE", path + f'/{control["id"]}', client=analyst), (204, None))

    def test_isolation_both_directions_and_missing_resources(self):
        second = self.second_organization()
        clients = ((self.opener, self.csrf), second)
        controls = [self.request("POST", "/controls", self.control_payload(), client=client)[1] for client in clients]
        risks = [self.request("POST", "/risks", self.risk_payload(), client=client)[1] for client in clients]
        for client, control, risk, other_control, other_risk in (
            (clients[0], controls[0], risks[0], controls[1], risks[1]),
            (clients[1], controls[1], risks[1], controls[0], risks[0]),
        ):
            path = f'/risks/{risk["id"]}/controls'
            self.assertEqual(self.request("POST", path, {"control_id": control["id"]}, client=client)[0], 201)
            self.assertEqual(self.request("GET", path, client=client), (200, [control]))
            for query in ("", "?type=corrective", "?status=planned", "?type=corrective&status=planned"):
                self.assertEqual(self.request("GET", "/controls" + query, client=client), (200, [control]))
            self.assertEqual(self.request("GET", "/controls?type=preventive", client=client), (200, []))
            for control_id in (other_control["id"], 999999):
                self.assertEqual(self.request("GET", f'/controls/{control_id}', client=client)[0], 404)
                self.assertEqual(self.request("POST", path, {"control_id": control_id}, client=client)[0], 404)
                self.assertEqual(self.request("DELETE", path + f'/{control_id}', client=client)[0], 404)
            for risk_id in (other_risk["id"], 999999):
                foreign_path = f'/risks/{risk_id}/controls'
                self.assertEqual(self.request("GET", foreign_path, client=client)[0], 404)
                self.assertEqual(self.request("POST", foreign_path, {"control_id": control["id"]}, client=client)[0], 404)
                self.assertEqual(self.request("DELETE", foreign_path + f'/{control["id"]}', client=client)[0], 404)
            self.assertEqual(self.request("GET", path, client=client), (200, [control]))

    def test_database_constraints_and_tenant_integrity(self):
        second = self.second_organization()
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        control = self.request("POST", "/controls", self.control_payload())[1]
        foreign_risk = self.request("POST", "/risks", self.risk_payload(), client=second)[1]
        foreign_control = self.request("POST", "/controls", self.control_payload(), client=second)[1]
        self.request("POST", f'/risks/{risk["id"]}/controls', {"control_id": control["id"]})
        with closing(fixtures.app_main.connect()) as connection:
            for values in ((risk["id"], foreign_control["id"], 1), (foreign_risk["id"], control["id"], 2),
                           (risk["id"], control["id"], 2), (999999, control["id"], 1),
                           (risk["id"], 999999, 1), (risk["id"], control["id"], 1),
                           (risk["id"], control["id"], None)):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("INSERT INTO risk_controls VALUES (?, ?, ?)", values)
                connection.rollback()
            for sql, values in (
                ("UPDATE risk_controls SET control_id = ? WHERE risk_id = ?", (foreign_control["id"], risk["id"])),
                ("UPDATE risk_controls SET risk_id = ? WHERE control_id = ?", (foreign_risk["id"], control["id"])),
                ("UPDATE risk_controls SET organization_id = 2 WHERE risk_id = ?", (risk["id"],)),
                ("UPDATE risks SET organization_id = 2 WHERE id = ?", (risk["id"],)),
                ("UPDATE security_controls SET organization_id = 2 WHERE id = ?", (control["id"],)),
                ("DELETE FROM risks WHERE id = ?", (risk["id"],)),
                ("DELETE FROM security_controls WHERE id = ?", (control["id"],)),
                ("UPDATE security_controls SET name = ' ' WHERE id = ?", (control["id"],)),
                ("UPDATE security_controls SET type = 'invalid' WHERE id = ?", (control["id"],)),
                ("UPDATE security_controls SET status = 'invalid' WHERE id = ?", (control["id"],)),
                ("UPDATE security_controls SET organization_id = NULL WHERE id = ?", (control["id"],)),
                ("INSERT INTO security_controls (organization_id, name, type, created_at) VALUES (999999, 'Bad', 'preventive', '2026-01-01')", ()),
            ):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql, values)
                connection.rollback()
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_persistence_of_controls_links_and_unlinks(self):
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        control = self.request("POST", "/controls", self.control_payload())[1]
        path = f'/risks/{risk["id"]}/controls'
        self.request("POST", path, {"control_id": control["id"]})
        self.stop_server(); self.start_server()
        self.assertEqual(self.request("GET", "/controls"), (200, [control]))
        self.assertEqual(self.request("GET", path), (200, [control]))
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}'), (200, risk))
        self.assertEqual(self.request("DELETE", path + f'/{control["id"]}')[0], 204)
        self.stop_server(); self.start_server()
        self.assertEqual(self.request("GET", path), (200, []))
        self.assertEqual(self.request("GET", f'/controls/{control["id"]}'), (200, control))
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}'), (200, risk))

    def test_migration_preserves_all_existing_data_and_is_idempotent(self):
        incident = self.request("POST", "/incidents", self.payload())[1]
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        risk = self.request("POST", "/risks", self.risk_payload(asset_id=asset["id"]))[1]
        self.request("POST", f'/incidents/{incident["id"]}/assets', {"asset_id": asset["id"]})
        self.request("POST", f'/incidents/{incident["id"]}/notes', {"content": "Preserved"})
        self.request("PATCH", f'/incidents/{incident["id"]}/status', {"status": "investigating"})
        self.stop_server()
        tables = ("organizations", "users", "sessions", "incidents", "assets", "risks", "incident_assets", "incident_notes", "incident_status_history", "sqlite_sequence")
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("DROP TABLE risk_controls")
            connection.execute("DROP TABLE security_controls")
            connection.execute("DROP INDEX idx_risks_id_organization")
            connection.execute("DELETE FROM schema_migrations WHERE version = 7")
            before = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in tables}
        fixtures.app_main.migrate_database(); fixtures.app_main.migrate_database()
        with closing(fixtures.app_main.connect()) as connection:
            after = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in tables}
            self.assertEqual(before, after)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM security_controls").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM risk_controls").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 7").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.start_server()
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}'), (200, risk))
        self.assertEqual(self.request("GET", "/controls"), (200, []))
