import contextlib
import io
import secrets
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reset_demo_password as recovery
from main import verify_password


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "portfolio-demo.db"
        with contextlib.closing(sqlite3.connect(self.target)) as db, db:
            db.executescript("""
                CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, is_active INTEGER, password_hash TEXT);
                CREATE TABLE sessions (user_id INTEGER, marker TEXT);
                INSERT INTO users VALUES (1, 'admin@aurora.example.test', 1, 'old');
                INSERT INTO users VALUES (2, 'other@example.test', 1, 'untouched');
                INSERT INTO sessions VALUES (1, 'target'), (2, 'other');
            """)
        self.password = secrets.token_urlsafe(24)

    def run_command(self, confirmation=None, interactive=True):
        with patch.object(recovery, "TARGET", self.target), \
             patch.object(sys, "argv", ["reset_demo_password.py"]), \
             patch.object(recovery, "windows_console_available", return_value=interactive), \
             patch.object(sys.stdin, "isatty", return_value=interactive), \
             patch.object(recovery, "getpass", side_effect=[self.password, confirmation or self.password]), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return recovery.main()

    def snapshot(self):
        with contextlib.closing(sqlite3.connect(self.target)) as db, db:
            return (db.execute("SELECT * FROM users ORDER BY id").fetchall(),
                    db.execute("SELECT * FROM sessions ORDER BY user_id").fetchall())

    def test_only_target_password_and_sessions_change(self):
        before = self.snapshot()
        usual = self.target.with_name("securityops.db")
        usual.write_bytes(b"protected sentinel")
        with patch.dict("os.environ", {"SECURITYOPS_DATABASE": str(usual)}):
            self.assertEqual(self.run_command(), 0)
        users, sessions = self.snapshot()
        self.assertTrue(verify_password(self.password, users[0][3]))
        self.assertEqual(users[0][:3], before[0][0][:3])
        self.assertEqual(users[1:], before[0][1:])
        self.assertEqual(sessions, [before[1][1]])
        self.assertEqual(usual.read_bytes(), b"protected sentinel")

    def test_mismatch_and_noninteractive_leave_database_unchanged(self):
        before = self.snapshot()
        self.assertEqual(self.run_command(confirmation="different"), 1)
        self.assertEqual(self.run_command(interactive=False), 1)
        self.assertEqual(self.snapshot(), before)

    def test_failure_deleting_sessions_rolls_back_password(self):
        with contextlib.closing(sqlite3.connect(self.target)) as db, db:
            db.execute("CREATE TRIGGER block_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        before = self.snapshot()
        self.assertEqual(self.run_command(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_missing_database_is_not_created(self):
        self.target.unlink()
        self.assertEqual(self.run_command(), 1)
        self.assertFalse(self.target.exists())

    def test_inactive_or_missing_account_is_not_changed(self):
        for sql in ("UPDATE users SET is_active = 0 WHERE id = 1", "DELETE FROM users WHERE id = 1"):
            with contextlib.closing(sqlite3.connect(self.target)) as db, db:
                db.execute(sql)
            before = self.snapshot()
            self.assertEqual(self.run_command(), 1)
            self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
