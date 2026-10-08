from contextlib import closing
from http.cookiejar import CookieJar
import sqlite3
import unittest
from urllib.request import HTTPCookieProcessor, build_opener

import test_incidents as fixtures
import test_risks as risk_fixtures


class AssigneeTests(unittest.TestCase):
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

    def create_user(self, role="analista", name="Assigned Analyst", suffix="analyst"):
        code, user = self.request("POST", "/users", {"display_name": name, "role": role,
                                 "email": f"{suffix}@example.test", "password": "assignee user password"})
        self.assertEqual(code, 201)
        return user

    def resources(self):
        incident = self.request("POST", "/incidents", self.payload())[1]
        risk = self.request("POST", "/risks", self.risk_payload())[1]
        return [("incidents", incident), ("risks", risk)]

    def test_candidates_minimal_eligible_and_available_to_all_roles(self):
        analyst = self.create_user(name="<img src=x onerror=alert(1)>")
        reader = self.create_user(role="lector", suffix="reader")
        inactive = self.create_user(suffix="inactive")
        self.request("PATCH", f'/users/{inactive["id"]}', {"is_active": False})
        expected = [{"id": 1, "display_name": "Test Administrator"},
                    {"id": analyst["id"], "display_name": analyst["display_name"]}]
        for client in ((self.opener, self.csrf), self.login_client(analyst["email"], "assignee user password"),
                       self.login_client(reader["email"], "assignee user password")):
            self.assertEqual(self.request("GET", "/assignees", client=client), (200, expected))
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        self.assertEqual(self.request("GET", "/assignees", client=anonymous)[0], 401)
        reader_client = self.login_client(reader["email"], "assignee user password")
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("UPDATE users SET is_active = 0 WHERE role <> 'lector'")
        self.assertEqual(self.request("GET", "/assignees", client=reader_client), (200, []))

    def test_assign_reassign_clear_and_read_responses(self):
        analyst = self.create_user()
        for kind, original in self.resources():
            path = f'/{kind}/{original["id"]}'
            self.assertIsNone(original["assignee_id"])
            self.assertIsNone(original["assignee_name"])
            for target, name in ((1, "Test Administrator"), (analyst["id"], analyst["display_name"]),
                                 (analyst["id"], analyst["display_name"]), (None, None), (None, None)):
                code, updated = self.request("PATCH", path + "/assignee", {"assignee_id": target})
                self.assertEqual(code, 200)
                expected = original | {"assignee_id": target, "assignee_name": name}
                self.assertEqual(updated, expected)
                self.assertEqual(self.request("GET", path), (200, expected))
                self.assertEqual(self.request("GET", f'/{kind}'), (200, [expected]))
            self.request("PATCH", path + "/assignee", {"assignee_id": analyst["id"]})
            if kind == "incidents":
                code, changed = self.request("PATCH", path + "/status", {"status": "investigating"})
                self.assertEqual(code, 200)
                self.assertEqual((changed["assignee_id"], changed["assignee_name"]), (analyst["id"], analyst["display_name"]))
        self.request("PATCH", f'/users/{analyst["id"]}', {"display_name": "Renamed Analyst"})
        for kind in ("incidents", "risks"):
            self.assertEqual(self.request("GET", f'/{kind}')[1][0]["assignee_name"], "Renamed Analyst")

    def test_filters_with_existing_fields_and_ineligible_users(self):
        analyst = self.create_user()
        reader = self.create_user(role="lector", suffix="reader")
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        for kind, original in self.resources():
            path = f'/{kind}/{original["id"]}'
            self.request("PATCH", path + "/assignee", {"assignee_id": analyst["id"]})
            expected = self.request("GET", path)[1]
            if kind == "incidents":
                other = self.request("POST", "/incidents", self.payload(severity="low", status="resolved"))[1]
                match = f'/{kind}?status=open&severity=high&assignee_id={analyst["id"]}'
                empty = f'/{kind}?status=resolved&assignee_id={analyst["id"]}'
            else:
                other = self.request("POST", "/risks", self.risk_payload(asset_id=asset["id"], status="accepted"))[1]
                self.request("PATCH", f'/risks/{other["id"]}/assignee', {"assignee_id": analyst["id"]})
                other = self.request("GET", f'/risks/{other["id"]}')[1]
                match = f'/{kind}?status=accepted&level=high&asset_id={asset["id"]}&assignee_id={analyst["id"]}'
                expected = other
                empty = match.replace("level=high", "level=low")
            self.assertEqual(self.request("GET", match), (200, [expected]))
            self.assertEqual(self.request("GET", empty), (200, []))
            self.assertEqual(self.request("GET", f'/{kind}?assignee_id=1'), (200, []))
            self.assertEqual(self.request("GET", f'/{kind}?assignee_id={reader["id"]}'), (200, []))
            for value in ("0", "-1", "true", "1.5", "invalid", "null"):
                self.assertEqual(self.request("GET", f'/{kind}?assignee_id={value}')[0], 422)

    def test_strict_validation_and_ineligible_own_users(self):
        reader = self.create_user(role="lector", suffix="reader")
        inactive = self.create_user(suffix="inactive")
        self.request("PATCH", f'/users/{inactive["id"]}', {"is_active": False})
        for kind, resource in self.resources():
            path = f'/{kind}/{resource["id"]}/assignee'
            for body in ({}, {"assignee_id": True}, {"assignee_id": False}, {"assignee_id": 0},
                         {"assignee_id": -1}, {"assignee_id": 1.5}, {"assignee_id": 1.0}, {"assignee_id": "1"},
                         {"assignee_id": []}, {"assignee_id": {}}, {"assignee_id": 1, "organization_id": 1}):
                self.assertEqual(self.request("PATCH", path, body)[0], 422)
            self.assertEqual(self.request("PATCH", path)[0], 422)
            for target in (reader["id"], inactive["id"]):
                self.assertEqual(self.request("PATCH", path, {"assignee_id": target})[0], 422)
            self.assertEqual(self.request("PATCH", path, {"assignee_id": 999999})[0], 404)
            self.assertEqual(self.request("PATCH", f'/{kind}/999999/assignee', {"assignee_id": None})[0], 404)
            self.assertEqual(self.request("GET", f'/{kind}?assignee_id=999999')[0], 404)
            self.assertEqual(self.request("GET", f'/{kind}/{resource["id"]}'), (200, resource))
            payload = self.payload() if kind == "incidents" else self.risk_payload()
            self.assertEqual(self.request("POST", f'/{kind}', payload | {"assignee_id": 1})[0], 422)

    def test_permissions_and_csrf(self):
        analyst = self.create_user()
        reader = self.create_user(role="lector", suffix="reader")
        clients = [self.login_client(user["email"], "assignee user password") for user in (analyst, reader)]
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        for kind, resource in self.resources():
            path = f'/{kind}/{resource["id"]}'
            for target in (1, None):
                body = {"assignee_id": target}
                self.assertEqual(self.request("PATCH", path + "/assignee", body, client=anonymous)[0], 401)
                self.assertEqual(self.request("PATCH", path + "/assignee", body, send_csrf=False)[0], 403)
                self.assertEqual(self.request("PATCH", path + "/assignee", body, client=(self.opener, "bad"))[0], 403)
                for client in clients:
                    self.assertEqual(self.request("PATCH", path + "/assignee", body, client=client)[0], 403)
            expected = self.request("PATCH", path + "/assignee", {"assignee_id": analyst["id"]})[1]
            for client in clients:
                self.assertEqual(self.request("GET", path, client=client), (200, expected))
                self.assertEqual(self.request("GET", f'/{kind}?assignee_id={analyst["id"]}', client=client), (200, [expected]))

    def test_organization_isolation_and_candidates(self):
        second = self.second_organization()
        foreign_user = self.request("GET", "/assignees", client=second)[1][0]
        self.assertEqual(foreign_user["display_name"], "Foreign admin")
        self.assertEqual(self.request("GET", "/assignees")[1], [{"id": 1, "display_name": "Test Administrator"}])
        for kind, local in self.resources():
            payload = self.payload() if kind == "incidents" else self.risk_payload()
            foreign = self.request("POST", f'/{kind}', payload, client=second)[1]
            for client, own, own_user, other, other_user in (
                ((self.opener, self.csrf), local, 1, foreign, foreign_user["id"]),
                (second, foreign, foreign_user["id"], local, 1),
            ):
                path = f'/{kind}/{own["id"]}/assignee'
                self.assertEqual(self.request("PATCH", path, {"assignee_id": own_user}, client=client)[0], 200)
                self.assertEqual(self.request("PATCH", path, {"assignee_id": other_user}, client=client)[0], 404)
                self.assertEqual(self.request("PATCH", f'/{kind}/{other["id"]}/assignee', {"assignee_id": own_user}, client=client)[0], 404)
                self.assertEqual(self.request("PATCH", f'/{kind}/{other["id"]}/assignee', {"assignee_id": None}, client=client)[0], 404)
                self.assertEqual(self.request("GET", f'/{kind}?assignee_id={other_user}', client=client)[0], 404)
                self.assertEqual(len(self.request("GET", f'/{kind}?assignee_id={own_user}', client=client)[1]), 1)

    def test_deactivation_and_reader_role_clear_all_assignments(self):
        second = self.second_organization()
        foreign_user = self.request("GET", "/assignees", client=second)[1][0]
        foreign_resources = []
        for kind, payload in (("incidents", self.payload()), ("risks", self.risk_payload())):
            resource = self.request("POST", f'/{kind}', payload, client=second)[1]
            resource = self.request("PATCH", f'/{kind}/{resource["id"]}/assignee',
                                    {"assignee_id": foreign_user["id"]}, client=second)[1]
            foreign_resources.append((kind, resource))
        for suffix, change in (("deactivated", {"is_active": False}), ("demoted", {"role": "lector"})):
            user = self.create_user(suffix=suffix)
            assigned = self.resources() + self.resources()
            other = self.resources()
            for kind, resource in assigned:
                self.request("PATCH", f'/{kind}/{resource["id"]}/assignee', {"assignee_id": user["id"]})
            for kind, resource in other:
                self.request("PATCH", f'/{kind}/{resource["id"]}/assignee', {"assignee_id": 1})
            self.assertEqual(self.request("PATCH", f'/users/{user["id"]}', change)[0], 200)
            for kind, resource in assigned:
                self.assertEqual(self.request("GET", f'/{kind}/{resource["id"]}'), (200, resource))
            for kind, resource in other:
                self.assertEqual(self.request("GET", f'/{kind}/{resource["id"]}')[1]["assignee_id"], 1)
            for kind, resource in foreign_resources:
                self.assertEqual(self.request("GET", f'/{kind}/{resource["id"]}', client=second), (200, resource))
            self.assertNotIn(user["id"], [item["id"] for item in self.request("GET", "/assignees")[1]])
            self.request("PATCH", f'/users/{user["id"]}', {"is_active": True, "role": "analista"})
            for kind, resource in assigned:
                self.assertIsNone(self.request("GET", f'/{kind}/{resource["id"]}')[1]["assignee_id"])

    def test_user_update_and_cleanup_roll_back_completely_on_failure(self):
        user = self.create_user()
        assigned = self.resources()
        for kind, resource in assigned:
            self.request("PATCH", f'/{kind}/{resource["id"]}/assignee', {"assignee_id": user["id"]})
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("""CREATE TRIGGER fail_risk_unassignment BEFORE UPDATE OF assignee_id ON risks
                WHEN OLD.assignee_id IS NOT NULL AND NEW.assignee_id IS NULL
                BEGIN SELECT RAISE(ABORT, 'Simulated cleanup failure'); END""")
            tables = ("users", "incidents", "risks", "sessions")
            before = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in tables}
        for change in ({"is_active": False}, {"role": "lector"}, {"display_name": "Changed", "role": "lector"}):
            # The normal error response is plain text for an unexpected database error.
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as caught:
                request = fixtures.Request(self.base_url + f'/users/{user["id"]}',
                    data=fixtures.json.dumps(change).encode(), method="PATCH",
                    headers={"Content-Type": "application/json", "X-CSRF-Token": self.csrf})
                self.opener.open(request, timeout=2)
            self.assertEqual(caught.exception.code, 500)
            caught.exception.close()
            with closing(fixtures.app_main.connect()) as connection:
                after = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")] for table in tables}
                self.assertEqual(before, after)
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute("DROP TRIGGER fail_risk_unassignment")
        self.assertEqual(self.request("PATCH", f'/users/{user["id"]}', {"is_active": False})[0], 200)

    def test_database_guards_direct_writes_and_atomic_cleanup(self):
        user = self.create_user()
        reader = self.create_user(role="lector", suffix="reader")
        inactive = self.create_user(suffix="inactive")
        self.request("PATCH", f'/users/{inactive["id"]}', {"is_active": False})
        second = self.second_organization()
        foreign = self.request("GET", "/assignees", client=second)[1][0]
        resources = self.resources()
        with closing(fixtures.app_main.connect()) as connection:
            for kind, resource in resources:
                for target in (foreign["id"], reader["id"], inactive["id"], 999999):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(f"UPDATE {kind} SET assignee_id = ? WHERE id = ?", (target, resource["id"]))
                    connection.rollback()
                connection.execute(f"UPDATE {kind} SET assignee_id = ? WHERE id = ?", (user["id"], resource["id"]))
                connection.commit()
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"UPDATE {kind} SET organization_id = 2 WHERE id = ?", (resource["id"],))
                connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE users SET organization_id = 2 WHERE id = ?", (user["id"],))
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM users WHERE id = ?", (user["id"],))
            connection.rollback()
            for sql in ("UPDATE users SET role = 'lector' WHERE id = ?", "UPDATE users SET is_active = 0 WHERE id = ?"):
                connection.execute(sql, (user["id"],))
                for kind, resource in resources:
                    self.assertIsNone(connection.execute(f"SELECT assignee_id FROM {kind} WHERE id = ?", (resource["id"],)).fetchone()[0])
                connection.rollback()
                for kind, resource in resources:
                    self.assertEqual(connection.execute(f"SELECT assignee_id FROM {kind} WHERE id = ?", (resource["id"],)).fetchone()[0], user["id"])
            for sql in (
                "INSERT INTO incidents (title, description, severity, status, created_at, organization_id, assignee_id) VALUES ('Bad', 'Bad', 'high', 'open', '2026-01-01', 1, ?)",
                "INSERT INTO risks (title, probability, impact, created_at, organization_id, assignee_id) VALUES ('Bad', 1, 1, '2026-01-01', 1, ?)",
            ):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql, (foreign["id"],))
                connection.rollback()
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_persistence_and_migration_preserves_all_prior_data(self):
        asset = self.request("POST", "/assets", self.asset_payload())[1]
        incident = self.request("POST", "/incidents", self.payload())[1]
        risk = self.request("POST", "/risks", self.risk_payload(asset_id=asset["id"]))[1]
        control = self.request("POST", "/controls", {"name": "Preserved", "type": "preventive"})[1]
        self.request("POST", f'/incidents/{incident["id"]}/assets', {"asset_id": asset["id"]})
        self.request("POST", f'/incidents/{incident["id"]}/notes', {"content": "Preserved"})
        self.request("PATCH", f'/incidents/{incident["id"]}/status', {"status": "investigating"})
        self.request("POST", f'/risks/{risk["id"]}/controls', {"control_id": control["id"]})
        self.stop_server()
        tables = ("users", "sessions", "organizations", "incidents", "risks", "assets", "security_controls",
                  "incident_notes", "incident_status_history", "incident_assets", "risk_controls", "sqlite_sequence")
        with closing(fixtures.app_main.connect()) as connection, connection:
            fixtures.rewind_assignee_migration(connection)
            columns = {table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")] for table in tables}
            before = {table: [tuple(row) for row in connection.execute(f"SELECT {', '.join(columns[table])} FROM {table} ORDER BY 1")] for table in tables}
        fixtures.app_main.migrate_database(); fixtures.app_main.migrate_database()
        with closing(fixtures.app_main.connect()) as connection:
            after = {table: [tuple(row) for row in connection.execute(f"SELECT {', '.join(columns[table])} FROM {table} ORDER BY 1")] for table in tables}
            self.assertEqual(before, after)
            for kind in ("incidents", "risks"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {kind} WHERE assignee_id IS NOT NULL").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 8").fetchone()[0], 1)
        self.start_server()
        for kind, resource in (("incidents", incident), ("risks", risk)):
            path = f'/{kind}/{resource["id"]}'
            updated = self.request("PATCH", path + "/assignee", {"assignee_id": 1})[1]
            self.stop_server(); self.start_server()
            self.assertEqual(self.request("GET", path), (200, updated))
            self.request("PATCH", path + "/assignee", {"assignee_id": None})
            self.stop_server(); self.start_server()
            self.assertIsNone(self.request("GET", path)[1]["assignee_id"])
