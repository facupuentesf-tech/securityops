from contextlib import closing
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import sqlite3
import unittest
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, build_opener

import test_incidents as fixtures


class RiskTests(unittest.TestCase):
    setUp = fixtures.IncidentTests.setUp
    start_server = fixtures.IncidentTests.start_server
    stop_server = fixtures.IncidentTests.stop_server
    seed_admin = fixtures.IncidentTests.seed_admin
    request = fixtures.IncidentTests.request
    login_client = fixtures.IncidentTests.login_client
    asset_payload = fixtures.IncidentTests.asset_payload
    payload = fixtures.IncidentTests.payload

    def risk_payload(self, **changes):
        return {"title": "Possible data loss", "probability": 3, "impact": 4} | changes

    def test_creation_lookup_optional_fields_and_sql_parameters(self):
        self.assertEqual(self.request("GET", "/risks"), (200, []))
        code, risk = self.request("POST", "/risks", self.risk_payload(title="  O'Brien'); DROP TABLE risks; --  "))
        self.assertEqual(code, 201)
        self.assertEqual(risk["title"], "O'Brien'); DROP TABLE risks; --")
        self.assertEqual((risk["score"], risk["level"], risk["status"]), (12, "high", "identified"))
        self.assertIsNone(risk["description"])
        self.assertIsNone(risk["asset_id"])
        self.assertIsNone(risk["asset_name"])
        self.assertNotIn("organization_id", risk)
        self.assertEqual(datetime.fromisoformat(risk["created_at"]).utcoffset(), timezone.utc.utcoffset(None))
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}'), (200, risk))
        self.assertEqual(self.request("GET", "/risks"), (200, [risk]))
        for description in (None, "", "<script>alert(1)</script>", "O'Brien"):
            code, created = self.request("POST", "/risks", self.risk_payload(description=description))
            self.assertEqual(code, 201)
            self.assertEqual(created["description"], description)
        self.assertEqual(self.request("GET", "/risks/999999")[0], 404)

    def test_matrix_all_combinations_and_exact_boundaries(self):
        for score, expected in ((1, "low"), (4, "low"), (5, "medium"), (9, "medium"),
                                (10, "high"), (16, "high"), (17, "critical"), (25, "critical")):
            self.assertEqual(fixtures.app_main.risk_level(score), expected)
        risks = []
        for probability in range(1, 6):
            for impact in range(1, 6):
                score = probability * impact
                expected = "low" if score <= 4 else "medium" if score <= 9 else "high" if score <= 16 else "critical"
                code, risk = self.request("POST", "/risks", self.risk_payload(probability=probability, impact=impact))
                self.assertEqual(code, 201)
                self.assertEqual((risk["score"], risk["level"]), (score, expected))
                risks.append(risk)
        for level in ("low", "medium", "high", "critical"):
            self.assertEqual(self.request("GET", "/risks?level=" + level),
                             (200, [risk for risk in risks if risk["level"] == level]))

    def test_filters_combine_with_and_and_asset_association(self):
        assets = [self.request("POST", "/assets", self.asset_payload(name=name))[1] for name in ("Server", "Unused")]
        cases = ({"status": "identified", "probability": 1, "impact": 4},
                 {"status": "treating", "probability": 3, "impact": 3, "asset_id": assets[0]["id"]},
                 {"status": "accepted", "probability": 5, "impact": 5, "asset_id": assets[0]["id"]})
        risks = [self.request("POST", "/risks", self.risk_payload(**case))[1] for case in cases]
        self.assertEqual(risks[1]["asset_name"], "Server")
        filters = ({"status": "identified"}, {"status": "treating"}, {"status": "accepted"},
                   {"level": "low"}, {"level": "high"}, {"asset_id": assets[0]["id"]},
                   {"asset_id": assets[1]["id"]}, {"status": "treating", "level": "medium"},
                   {"status": "treating", "level": "medium", "asset_id": assets[0]["id"]},
                   {"status": "accepted", "level": "medium", "asset_id": assets[0]["id"]})
        for query in filters:
            expected = [risk for risk in risks if all(risk[key] == value for key, value in query.items())]
            self.assertEqual(self.request("GET", "/risks?" + urlencode(query)), (200, expected))

    def test_validation_rejects_boolean_coercion_extra_fields_and_filters(self):
        invalid = [{"title": value} for value in ("", " ", "\t\n", None, 42)]
        invalid += [{field: value} for field in ("probability", "impact")
                    for value in (True, False, 0, 6, -1, 1.5, 1.0, "3", None)]
        invalid += [{"asset_id": value} for value in (True, False, 0, -1, 1.5, "1")]
        invalid += [{"status": value} for value in ("open", "", None)]
        invalid += [{field: value} for field, value in (("organization_id", 1), ("score", 12), ("level", "high"), ("description", 42))]
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(self.request("POST", "/risks", self.risk_payload(**changes))[0], 422)
        for field in ("title", "probability", "impact"):
            body = self.risk_payload(); del body[field]
            self.assertEqual(self.request("POST", "/risks", body)[0], 422)
        self.assertEqual(self.request("POST", "/risks")[0], 422)
        for query in ("status=invalid", "level=invalid", "asset_id=0", "asset_id=-1", "asset_id=true", "asset_id=1.5",
                      "status=identified%27%20OR%201=1--"):
            self.assertEqual(self.request("GET", "/risks?" + query)[0], 422)
        self.assertEqual(self.request("GET", "/risks/not-an-id")[0], 422)
        self.assertEqual(self.request("GET", "/risks"), (200, []))

    def test_permissions_authentication_and_csrf(self):
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        for method, path, body in (("GET", "/risks", None), ("GET", "/risks/1", None), ("POST", "/risks", self.risk_payload())):
            self.assertEqual(self.request(method, path, body, client=anonymous)[0], 401)
        self.assertEqual(self.request("POST", "/risks", self.risk_payload(), send_csrf=False)[0], 403)
        self.assertEqual(self.request("POST", "/risks", self.risk_payload(), client=(self.opener, "invalid"))[0], 403)
        for role in ("analista", "lector"):
            self.assertEqual(self.request("POST", "/users", {"display_name": role, "email": f"{role}@example.test",
                             "password": "risk user password", "role": role})[0], 201)
        analyst = self.login_client("analista@example.test", "risk user password")
        reader = self.login_client("lector@example.test", "risk user password")
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        code, risk = self.request("POST", "/risks", self.risk_payload(asset_id=asset["id"]), client=analyst)
        self.assertEqual(code, 201)
        self.assertEqual(self.request("POST", "/risks", self.risk_payload(), client=reader)[0], 403)
        for client in (analyst, reader):
            self.assertEqual(self.request("GET", "/risks", client=client), (200, [risk]))
            self.assertEqual(self.request("GET", f'/risks/{risk["id"]}', client=client), (200, risk))

    def second_organization(self):
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("INSERT INTO organizations (name, created_at) VALUES ('Risk tenant', '2026-01-01')")
            connection.execute("INSERT INTO users (display_name, email, password_hash, role, organization_id, created_at) "
                               "VALUES (?, ?, ?, ?, 2, ?)", ("Foreign admin", "foreign@example.test",
                               fixtures.app_main.hash_password("foreign risk password"), "administrador", "2026-01-01"))
        return self.login_client("foreign@example.test", "foreign risk password")

    def test_organization_isolation_both_directions_and_missing_assets(self):
        second = self.second_organization()
        local_asset = self.request("POST", "/assets", self.asset_payload())[1]
        foreign_asset = self.request("POST", "/assets", self.asset_payload(), client=second)[1]
        local = self.request("POST", "/risks", self.risk_payload(asset_id=local_asset["id"]))[1]
        foreign = self.request("POST", "/risks", self.risk_payload(asset_id=foreign_asset["id"]), client=second)[1]
        for client, own, other, own_asset, other_asset in (
            ((self.opener, self.csrf), local, foreign, local_asset, foreign_asset),
            (second, foreign, local, foreign_asset, local_asset),
        ):
            self.assertEqual(self.request("GET", "/risks", client=client), (200, [own]))
            self.assertEqual(self.request("GET", f'/risks/{other["id"]}', client=client)[0], 404)
            self.assertEqual(self.request("GET", f'/risks/{own["id"]}', client=client), (200, own))
            self.assertEqual(self.request("GET", f'/risks?status=identified&level=high&asset_id={own_asset["id"]}', client=client), (200, [own]))
            for asset_id in (other_asset["id"], 999999):
                self.assertEqual(self.request("POST", "/risks", self.risk_payload(asset_id=asset_id), client=client)[0], 404)
                self.assertEqual(self.request("GET", f'/risks?asset_id={asset_id}', client=client)[0], 404)

    def test_database_integrity_and_restart_persistence(self):
        self.second_organization()
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        risk = self.request("POST", "/risks", self.risk_payload(asset_id=asset["id"]))[1]
        with closing(fixtures.app_main.connect()) as connection:
            for sql, params in (
                ("UPDATE risks SET organization_id = 2 WHERE id = ?", (risk["id"],)),
                ("UPDATE risks SET asset_id = 999999 WHERE id = ?", (risk["id"],)),
                ("UPDATE assets SET organization_id = 2 WHERE id = ?", (asset["id"],)),
                ("DELETE FROM assets WHERE id = ?", (asset["id"],)),
                ("UPDATE risks SET probability = 6 WHERE id = ?", (risk["id"],)),
                ("UPDATE risks SET impact = 1.5 WHERE id = ?", (risk["id"],)),
                ("UPDATE risks SET status = 'open' WHERE id = ?", (risk["id"],)),
                ("UPDATE risks SET title = ' ' WHERE id = ?", (risk["id"],)),
                ("UPDATE risks SET organization_id = NULL WHERE id = ?", (risk["id"],)),
            ):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql, params)
                connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO risks (organization_id, title, probability, impact, asset_id, created_at) "
                                   "VALUES (2, 'Foreign', 1, 1, ?, '2026-01-01')", (asset["id"],))
            connection.rollback()
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.stop_server(); self.start_server()
        self.assertEqual(self.request("GET", f'/risks/{risk["id"]}'), (200, risk))
        self.assertEqual(self.request("GET", f'/risks?asset_id={asset["id"]}'), (200, [risk]))

    def test_migration_preserves_existing_data_and_is_idempotent(self):
        incident = self.request("POST", "/incidents", self.payload())[1]
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        self.request("POST", f'/incidents/{incident["id"]}/assets', {"asset_id": asset["id"]})
        self.request("POST", f'/incidents/{incident["id"]}/notes', {"content": "Existing note"})
        self.request("PATCH", f'/incidents/{incident["id"]}/status', {"status": "investigating"})
        self.stop_server()
        tables = ("organizations", "users", "sessions", "incidents", "assets", "incident_assets", "incident_notes", "incident_status_history")
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("DROP TABLE risks")
            connection.execute("DELETE FROM schema_migrations WHERE version = 6")
            before = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in tables}
        fixtures.app_main.migrate_database(); fixtures.app_main.migrate_database()
        with closing(fixtures.app_main.connect()) as connection:
            after = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in tables}
            self.assertEqual(before, after)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM risks").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 6").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.start_server()
        self.assertEqual(self.request("GET", "/risks"), (200, []))
