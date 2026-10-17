"""Local recovery for one demo account; never creates or migrates a database."""
import sqlite3
import sys
import warnings
from contextlib import closing
from getpass import GetPassWarning, getpass
from pathlib import Path

from demo import windows_console_available
from main import PASSWORD_MIN_LENGTH, hash_password


TARGET = Path(__file__).resolve().with_name("portfolio-demo.db")
EMAIL = "admin@aurora.example.test"


def main():
    try:
        if len(sys.argv) != 1:
            raise ValueError("Este comando no acepta argumentos.")
        usual = TARGET.with_name("securityops.db")
        if (not TARGET.is_file() or TARGET.is_symlink()
                or TARGET.resolve() != TARGET.absolute()
                or (usual.exists() and TARGET.samefile(usual))):
            raise ValueError("La base demo debe existir y no puede apuntar a la base habitual.")
        interactive = windows_console_available() if sys.platform == "win32" else sys.stdin.isatty()
        if not interactive:
            raise ValueError("Ejecutá el comando directamente en una consola con entrada oculta.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Nueva contraseña (12–128 caracteres): ")
            confirmation = getpass("Confirmá la nueva contraseña: ")
        if not PASSWORD_MIN_LENGTH <= len(password) <= 128:
            raise ValueError("La contraseña debe contener entre 12 y 128 caracteres.")
        if password != confirmation:
            raise ValueError("Las contraseñas no coinciden.")
        encoded = hash_password(password)
        # Ignore SECURITYOPS_DATABASE: only this existing demo file is opened.
        with closing(sqlite3.connect(TARGET.as_uri() + "?mode=rw", uri=True)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id, is_active FROM users WHERE email = ? COLLATE NOCASE", (EMAIL,)
            ).fetchall()
            if len(rows) != 1 or rows[0][1] != 1:
                raise ValueError("Debe existir exactamente una cuenta demo activa; no se cambió nada.")
            user_id = rows[0][0]
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (encoded, user_id))
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        print("Contraseña de admin@aurora.example.test restablecida en portfolio-demo.db; sesiones invalidadas.")
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
    except (GetPassWarning, EOFError, KeyboardInterrupt):
        print("Entrada oculta cancelada o no disponible; no se cambió nada.", file=sys.stderr)
    except (sqlite3.Error, OSError):
        print("No se pudo completar la operación; la transacción no se confirmó.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
