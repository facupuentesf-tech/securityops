import csv
import io
import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor

import test_incidents as fixtures
import test_risks as risk_fixtures
import test_controls as control_fixtures


class ReportTests(unittest.TestCase):
    setUp = fixtures.IncidentTests.setUp
    start_server = fixtures.IncidentTests.start_server
    stop_server = fixtures.IncidentTests.stop_server
    seed_admin = fixtures.IncidentTests.seed_admin
    request = fixtures.IncidentTests.request
    login_client = fixtures.IncidentTests.login_client
    payload = fixtures.IncidentTests.payload
    asset_payload = fixtures.IncidentTests.asset_payload
    risk_payload = risk_fixtures.RiskTests.risk_payload
    control_payload = control_fixtures.ControlTests.control_payload
    second_organization = risk_fixtures.RiskTests.second_organization

    def create(self, path, payload, client=None):
        code, body = self.request("POST", path, payload, client=client)
        self.assertEqual(code, 201, body)
        return body

    def report(self, resource, query="", client=None):
        opener = client[0] if client else self.opener
        try:
            response = opener.open(self.base_url + f"/reports/{resource}.csv" + query, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def rows(self, resource, query="", client=None):
        code, headers, data = self.report(resource, query, client)
        self.assertEqual(code, 200, data)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), delimiter=";"))

    def test_empty_headers_format_and_controlled_download_names(self):
        for resource in fixtures.app_main.CSV_HEADERS:
            code, headers, data = self.report(resource, '?filename=evil.csv&organization_id=999')
            self.assertEqual(code, 200)
            self.assertEqual(headers["Content-Type"], "text/csv; charset=utf-8")
            self.assertEqual(headers["Content-Disposition"], f'attachment; filename="securityops-{resource}.csv"')
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(data, (";".join(fixtures.app_main.CSV_HEADERS[resource]) + "\r\n").encode("utf-8-sig"))
            self.assertEqual(self.rows(resource), [])

    def test_content_links_latest_residual_and_excluded_secrets(self):
        text = 'Descripción española; "comillas"\ny segunda línea'
        assets = [self.create('/assets', self.asset_payload(name=name, description=text))
                  for name in ('Servidor ñ', '=SUM(1;2)')]
        incident = self.create('/incidents', self.payload(title='Investigación ñ', description=text))
        for asset in assets:
            self.create(f'/incidents/{incident["id"]}/assets', {'asset_id': asset['id']})
        self.request('PATCH', f'/incidents/{incident["id"]}/assignee', {'assignee_id': 1})
        self.create(f'/incidents/{incident["id"]}/notes', {'content': 'SECRET NOTE'})
        risk = self.create('/risks', self.risk_payload(asset_id=assets[1]['id'], description=text))
        self.request('PATCH', f'/risks/{risk["id"]}/assignee', {'assignee_id': 1})
        self.create('/risks', self.risk_payload(title='Sin residual'))
        assessments = [self.create(f'/risks/{risk["id"]}/assessments', {
            'residual_probability': p, 'residual_impact': i, 'justification': 'SECRET JUSTIFICATION'})
            for p, i in ((1, 1), (5, 5), (2, 3))]
        with closing(fixtures.app_main.connect()) as connection, connection:
            # Equal dates exercise the ID tie-break; an earlier ID has a higher score.
            connection.execute('UPDATE risk_assessments SET created_at = ?', ('2026-10-08T12:00:00+00:00',))
        for name in ('Control ñ', 'Segundo control'):
            control = self.create('/controls', self.control_payload(name=name, description=text))
            self.create(f'/risks/{risk["id"]}/controls', {'control_id': control['id']})
        incidents = self.rows('incidents')
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]['Descripción'], text)
        self.assertEqual(incidents[0]['Responsable (ID)'], '1')
        self.assertEqual(incidents[0]['Responsable'], 'Test Administrator')
        self.assertEqual(incidents[0]['Activos afectados (IDs)'], ' | '.join(str(a['id']) for a in assets))
        self.assertEqual(incidents[0]['Activos afectados'], "Servidor ñ | '=SUM(1;2)")
        self.assertEqual(incidents[0]['Severidad'], 'Alta')
        risks = self.rows('risks')
        self.assertEqual(len(risks), 2)
        self.assertEqual(risks[0]['Puntaje original'], '12')
        self.assertEqual(risks[0]['Nivel original'], 'Alto')
        self.assertEqual(risks[0]['Activo'], "'=SUM(1;2)")
        self.assertEqual(risks[0]['Última evaluación residual (ID)'], str(assessments[-1]['id']))
        self.assertEqual(risks[0]['Puntaje residual'], '6')
        self.assertEqual(risks[0]['Nivel residual'], 'Medio')
        self.assertEqual(risks[0]['Fecha de evaluación residual (UTC)'], '2026-10-08T12:00:00+00:00')
        self.assertTrue(all(risks[1][heading] == '' for heading in fixtures.app_main.CSV_HEADERS['risks'][-6:]))
        self.assertEqual(self.rows('assets')[0]['Tipo'], 'Hardware')
        self.assertEqual(self.rows('controls')[0]['Tipo'], 'Correctivo')
        for resource in fixtures.app_main.CSV_HEADERS:
            data = self.report(resource)[2].decode('utf-8-sig')
            for secret in ('SECRET NOTE', 'SECRET JUSTIFICATION', 'password_hash', 'admin@example.test', 'csrf_token', 'session', 'cookie', 'audit_logs'):
                self.assertNotIn(secret, data)
            for row in self.rows(resource):
                self.assertEqual(datetime.fromisoformat(row['Fecha de creación (UTC)']).utcoffset(), timedelta(0))

    def test_formula_protection_and_csv_roundtrip(self):
        dangerous = ['=1+1', '+SUM(1;2)', '-1+2', '@SUM(A1)', '  =1', '\t+1', '\r\n@x', '\x00=1', '\u200b=1', '\u00a0 -1', '\tordinary']
        harmless = ['Español ñ; "texto"\nlínea', 'ordinary =1', "'already", '  ordinary', '']
        for text in dangerous + harmless:
            expected = "'" + text if text in dangerous else text
            self.assertEqual(fixtures.app_main.csv_safe(text), expected)
            self.create('/assets', self.asset_payload(description=text))
        self.assertEqual([a['Descripción'] for a in self.rows('assets')],
                         ["'" + s for s in dangerous] + harmless)
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute('UPDATE users SET display_name = ? WHERE id = 1', (' \t@actor',))
        incident = self.create('/incidents', self.payload(title='=title', description='\u200b=description'))
        self.request('PATCH', f'/incidents/{incident["id"]}/assignee', {'assignee_id': 1})
        row = self.rows('incidents')[0]
        self.assertEqual(row['Título'], "'=title")
        self.assertEqual(row['Descripción'], "'\u200b=description")
        self.assertEqual(row['Responsable'], "' \t@actor")
        self.assertEqual(fixtures.app_main.csv_safe(12), 12)
        self.assertEqual(fixtures.app_main.csv_safe(None), '')

    def test_filters_validation_and_stable_order_match_lists(self):
        asset = self.create('/assets', self.asset_payload())
        self.create('/assets', self.asset_payload(type='data', criticality='low'))
        self.create('/incidents', self.payload())
        self.create('/incidents', self.payload(status='resolved', severity='low'))
        self.create('/risks', self.risk_payload(asset_id=asset['id']))
        self.create('/risks', self.risk_payload(status='accepted', probability=1, impact=1))
        self.create('/controls', self.control_payload())
        self.create('/controls', self.control_payload(type='preventive', status='implemented'))
        queries = {
            'assets': ['', '?type=hardware', '?criticality=low', '?type=hardware&criticality=low'],
            'incidents': ['', '?status=open', '?severity=low', '?status=resolved&severity=high', '?assignee_id=1'],
            'risks': ['', '?status=identified', '?level=high', f'?asset_id={asset["id"]}', '?assignee_id=1', '?status=accepted&level=high'],
            'controls': ['', '?type=preventive', '?status=planned', '?type=preventive&status=planned'],
        }
        invalid = {'assets': ['?type=bad', '?criticality=high%27%20OR%201=1--'],
                   'incidents': ['?status=bad', '?severity=bad', '?assignee_id=0', '?assignee_id=bad', '?assignee_id=99999'],
                   'risks': ['?status=bad', '?level=bad', '?asset_id=-1', '?asset_id=99999', '?assignee_id=99999'],
                   'controls': ['?status=bad', '?type=bad']}
        for resource, filters in queries.items():
            for query in filters:
                expected = self.request('GET', '/' + resource + query)[1]
                self.assertEqual([int(row['ID']) for row in self.rows(resource, query)], [r['id'] for r in expected])
            for query in invalid[resource]:
                expected = self.request('GET', '/' + resource + query)[0]
                self.assertIn(expected, (422, 404))
                self.assertEqual(self.report(resource, query)[0], expected)

    def test_roles_and_organization_isolation(self):
        foreign = self.second_organization()
        anonymous = (build_opener(HTTPCookieProcessor(CookieJar())), None)
        clients = {}
        for role in ('analista', 'lector'):
            self.create('/users', {'display_name': role, 'email': role+'@example.test', 'password': 'reports password', 'role': role})
            clients[role] = self.login_client(role+'@example.test', 'reports password')
        for resource, payload in [('assets', self.asset_payload()), ('incidents', self.payload()),
                                  ('risks', self.risk_payload()), ('controls', self.control_payload())]:
            local = self.create('/'+resource, payload)
            self.assertEqual(self.rows(resource, client=foreign), [])
            other = self.create('/'+resource, payload, foreign)
            self.assertEqual([int(r['ID']) for r in self.rows(resource, '?organization_id=2')], [local['id']])
            self.assertEqual([int(r['ID']) for r in self.rows(resource, '?organization_id=1', foreign)], [other['id']])
            self.assertEqual(self.report(resource, client=anonymous)[0], 401)
            self.assertEqual(self.report(resource, client=clients['lector'])[0], 403)
            self.assertEqual(self.rows(resource, client=clients['analista']), self.rows(resource))
            if resource == 'assets':
                foreign_asset = other
        self.assertEqual(self.report('risks', f'?asset_id={foreign_asset["id"]}')[0], 404)
        self.assertEqual(self.report('incidents', '?assignee_id=2')[0], 404)

    def test_relations_and_assessments_remain_in_own_organization(self):
        foreign = self.second_organization()
        for client, name in ((None, 'LOCAL'), (foreign, 'FOREIGN')):
            asset = self.create('/assets', self.asset_payload(name=name), client)
            incident = self.create('/incidents', self.payload(title=name), client)
            risk = self.create('/risks', self.risk_payload(title=name, asset_id=asset['id']), client)
            self.create(f'/incidents/{incident["id"]}/assets', {'asset_id': asset['id']}, client)
            for probability in (1, 5):
                self.create(f'/risks/{risk["id"]}/assessments', {
                    'residual_probability': probability, 'residual_impact': 2, 'justification': name+' SECRET'}, client)
        for client, own, other in ((None, 'LOCAL', 'FOREIGN'), (foreign, 'FOREIGN', 'LOCAL')):
            incident = self.rows('incidents', client=client)[0]
            risk = self.rows('risks', client=client)[0]
            self.assertEqual(incident['Activos afectados'], own)
            self.assertEqual(risk['Activo'], own)
            self.assertEqual(risk['Puntaje residual'], '10')
            for resource in ('incidents', 'risks'):
                self.assertNotIn(other, self.report(resource, client=client)[2].decode('utf-8-sig'))

    def test_residual_snapshot_and_date_precedes_id_order(self):
        risk = self.create('/risks', self.risk_payload())
        older_id = self.create(f'/risks/{risk["id"]}/assessments', {
            'residual_probability': 5, 'residual_impact': 5, 'justification': 'Not exported'})
        self.create(f'/risks/{risk["id"]}/assessments', {
            'residual_probability': 1, 'residual_impact': 1, 'justification': 'Not exported'})
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.execute('UPDATE risk_assessments SET created_at = ? WHERE id = ?',
                               ('2099-01-01T00:00:00+00:00', older_id['id']))
        with closing(fixtures.app_main.connect()) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        interleaved = False
        test = self

        class InterleavingConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                nonlocal interleaved
                cursor = super().execute(sql, parameters)
                if 'FROM risks r' in sql and not interleaved:
                    interleaved = True
                    new = test.create(f'/risks/{risk["id"]}/assessments', {
                        'residual_probability': 2, 'residual_impact': 2, 'justification': 'Concurrent'})
                    with closing(sqlite3.connect(test.database)) as writer, writer:
                        writer.execute('UPDATE risk_assessments SET created_at = ? WHERE id = ?',
                                       ('2100-01-01T00:00:00+00:00', new['id']))
                return cursor

        def connect():
            connection = sqlite3.connect(self.database, factory=InterleavingConnection)
            connection.row_factory = sqlite3.Row
            return connection

        with patch.object(fixtures.app_main, 'connect', connect):
            response = fixtures.app_main.export_csv('risks', {'organization_id': 1})
        row = next(csv.DictReader(io.StringIO(response.body.decode('utf-8-sig')), delimiter=';'))
        self.assertTrue(interleaved)
        self.assertEqual(row['Última evaluación residual (ID)'], str(older_id['id']))
        self.assertEqual(row['Puntaje residual'], '25')
        self.assertEqual(self.rows('risks')[0]['Puntaje residual'], '4')

    def test_no_truncation_or_database_writes(self):
        with closing(fixtures.app_main.connect()) as connection, connection:
            connection.executemany('INSERT INTO assets (name,type,criticality,created_at,organization_id) VALUES (?,?,?,?,?)',
                                   [(f'Activo {i}', 'hardware', 'low', '2026-01-01T00:00:00+00:00', 1) for i in range(175)])
            tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            before = {t: connection.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables}
        rows = self.rows('assets')
        self.assertEqual([int(r['ID']) for r in rows], list(range(1, 176)))
        for resource in fixtures.app_main.CSV_HEADERS:
            self.rows(resource)
        with closing(fixtures.app_main.connect()) as connection:
            after = {t: connection.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables}
        self.assertEqual(before, after)

    def test_consistent_snapshot_for_resources_and_relations(self):
        incident = self.create('/incidents', self.payload())
        asset = self.create('/assets', self.asset_payload())
        with closing(fixtures.app_main.connect()) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        interleaved = False
        statements = []
        test = self

        class InterleavingConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                nonlocal interleaved
                statements.append((sql, parameters))
                cursor = super().execute(sql, parameters)
                if 'FROM incidents i' in sql and not interleaved:
                    interleaved = True
                    test.create(f'/incidents/{incident["id"]}/assets', {'asset_id': asset['id']})
                    test.create('/incidents', test.payload())
                return cursor

        def connect():
            connection = sqlite3.connect(self.database, factory=InterleavingConnection)
            connection.row_factory = sqlite3.Row
            return connection

        with patch.object(fixtures.app_main, 'connect', connect):
            response = fixtures.app_main.export_csv('incidents', {'organization_id': 1})
        rows = list(csv.DictReader(io.StringIO(response.body.decode('utf-8-sig')), delimiter=';'))
        self.assertTrue(interleaved)
        self.assertEqual(statements[0][0], 'BEGIN')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Activos afectados (IDs)'], '')
        fresh = self.rows('incidents')
        self.assertEqual(len(fresh), 2)
        self.assertEqual(fresh[0]['Activos afectados (IDs)'], str(asset['id']))


if __name__ == '__main__':
    unittest.main()
