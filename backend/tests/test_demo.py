"""Safety and consistency checks, exclusively on disposable databases."""
import secrets
import io
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_incidents import app_main
import demo


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        original = app_main.DATABASE_PATH
        self.addCleanup(setattr, app_main, "DATABASE_PATH", original)
        app_main.DATABASE_PATH = self.root / "usual.db"
        app_main.migrate_database()
        self.before = app_main.DATABASE_PATH.read_bytes()
        self.destination = self.root / "demo.db"
        self.passwords = {email: secrets.token_urlsafe(24) for _, _, _, email in demo.ACCOUNTS}

    def create(self):
        with patch.object(demo, "prompt_passwords", return_value=self.passwords):
            return demo.create_demo(app_main, self.destination)

    def test_creation_audit_isolation_and_usual_preserved(self):
        usual = app_main.DATABASE_PATH
        self.assertEqual(self.create(), 0)
        self.assertEqual(app_main.DATABASE_PATH, usual)
        self.assertEqual(usual.read_bytes(), self.before)
        app_main.DATABASE_PATH = self.destination
        with closing(app_main.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            for table, count in (("organizations", 2), ("users", 4), ("assets", 5),
                                 ("incidents", 4), ("risks", 3), ("security_controls", 3),
                                 ("risk_assessments", 2), ("incident_status_history", 3)):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], count)
            for row in connection.execute("SELECT * FROM users"):
                self.assertTrue(app_main.verify_password(self.passwords[row["email"]], row["password_hash"]))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            events = connection.execute("SELECT * FROM audit_logs").fetchall()
            self.assertGreater(len(events), 25)
            self.assertEqual({e["organization_id"] for e in events}, {1, 2})
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_logs a JOIN users u ON a.actor_id=u.id WHERE a.organization_id != u.organization_id").fetchone()[0], 0)
            self.assertEqual([tuple(r) for r in connection.execute("SELECT original_score, residual_probability * residual_impact FROM risk_assessments ORDER BY id")], [(20, 12), (20, 8)])
        for org, counts in ((1, (3, 4)), (2, (1, 1))):
            user = dict(organization_id=org)
            dashboard = app_main.dashboard(user)
            self.assertEqual((dashboard["incidents"]["total"], dashboard["assets"]["total"]), counts)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            app_main.get_incident(1, dict(organization_id=2))
        self.assertEqual(error.exception.status_code, 404)

    def test_unsafe_paths_rejected_before_password_prompt(self):
        default = Path(app_main.__file__).resolve().parent / "securityops.db"
        existing = self.root / "existing.db"
        existing.write_bytes(b"must survive")
        (self.root / "aux.db-wal").write_bytes(b"must survive too")
        for path in (app_main.DATABASE_PATH, default, default.with_name("securityops-before-organizations.bak"),
                     str(app_main.DATABASE_PATH) + "-wal", existing, self.root / "aux.db",
                     self.root / "missing" / "demo.db", self.root / "demo.txt",
                     self.root / "nested" / ".." / "usual.db"):
            with self.subTest(path=path), patch.object(demo, "prompt_passwords") as prompt:
                self.assertEqual(demo.create_demo(app_main, path), 1)
                prompt.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"must survive")
        self.assertEqual(app_main.DATABASE_PATH.read_bytes(), self.before)

    def test_no_overwrite_race_and_repeat(self):
        def competing_writer(app):
            self.destination.write_bytes(b"created by another process")
            return self.passwords
        with patch.object(demo, "prompt_passwords", side_effect=competing_writer):
            self.assertEqual(demo.create_demo(app_main, self.destination), 1)
        self.assertEqual(self.destination.read_bytes(), b"created by another process")
        self.assertEqual(app_main.DATABASE_PATH.read_bytes(), self.before)

    def test_prompt_requires_terminal_and_valid_confirmation(self):
        with patch.object(demo.sys.stdin, "isatty", return_value=False), patch.object(demo, "windows_console_available", return_value=False):
            with self.assertRaises(ValueError):
                demo.prompt_passwords(app_main)
        for responses in (("short", "short"), (secrets.token_urlsafe(20), "different")):
            with patch.object(demo.sys.stdin, "isatty", return_value=True), patch.object(demo, "windows_console_available", return_value=True), patch.object(demo, "getpass", side_effect=responses):
                with self.assertRaises(ValueError):
                    demo.prompt_passwords(app_main)
        self.assertFalse(self.destination.exists())

    def test_windows_console_with_non_tty_stdin(self):
        responses = [value for password in self.passwords.values() for value in (password, password)]
        with patch.object(demo.sys, "platform", "win32"), patch.object(demo.sys.stdin, "isatty", return_value=False), patch.object(demo, "windows_console_available", return_value=True), patch.object(demo, "getpass", side_effect=responses):
            self.assertEqual(demo.prompt_passwords(app_main), self.passwords)

    def test_specific_diagnostics_and_no_secret_disclosure(self):
        from getpass import GetPassWarning
        cases = (
            (demo.DemoInputError("Contraseña inválida: debe contener entre 12 y 128 caracteres."), "Contraseña inválida"),
            (demo.DemoInputError("Confirmación incorrecta: las contraseñas no coinciden."), "Confirmación incorrecta"),
            (demo.DemoInputError("Entrada no interactiva: consola no disponible."), "Entrada no interactiva"),
            (GetPassWarning("SECRET_WARNING"), "Entrada no interactiva"),
            (RuntimeError("SECRET_INTERNAL"), "Fallo interno"),
        )
        for error, expected in cases:
            with self.subTest(expected=expected), patch.object(demo, "prompt_passwords", side_effect=error), patch.object(demo.sys, "stderr", new_callable=io.StringIO) as output:
                self.assertEqual(demo.create_demo(app_main, self.destination), 1)
                self.assertIn(expected, output.getvalue())
                self.assertNotIn("SECRET", output.getvalue())
                self.assertFalse(self.destination.exists())
        self.destination.write_bytes(b"existing partial database")
        with patch.object(demo.sys, "stderr", new_callable=io.StringIO) as output:
            self.assertEqual(self.create(), 1)
            self.assertIn("Ruta existente", output.getvalue())
        self.assertEqual(self.destination.read_bytes(), b"existing partial database")

    def test_internal_failure_preserves_partial_file_and_usual_database(self):
        original = app_main.DATABASE_PATH
        def fail_seed(app, passwords):
            app.DATABASE_PATH.write_bytes(b"partial demo")
            raise ValueError("SECRET_VALIDATION_INPUT")
        with patch.object(demo, "seed_demo", side_effect=fail_seed), patch.object(demo.sys, "stderr", new_callable=io.StringIO) as output:
            self.assertEqual(self.create(), 1)
            self.assertIn("Fallo interno", output.getvalue())
            self.assertIn("parcialmente", output.getvalue())
            self.assertNotIn("SECRET", output.getvalue())
        self.assertEqual(self.destination.read_bytes(), b"partial demo")
        self.assertEqual(app_main.DATABASE_PATH, original)
        self.assertEqual(original.read_bytes(), self.before)
