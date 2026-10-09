"""Local fictitious dataset. Business changes reuse the application's operations."""
import os
import sys
import warnings
from contextlib import closing
from datetime import datetime, timezone
from getpass import GetPassWarning, getpass
from pathlib import Path


ACCOUNTS = (
    (1, "administrador", "Alba Demo", "admin@aurora.example.test"),
    (1, "analista", "Bruno Demo", "analista@aurora.example.test"),
    (1, "lector", "Clara Demo", "lector@aurora.example.test"),
    (2, "administrador", "Dalia Demo", "admin@delta.example.test"),
)


class DemoInputError(ValueError):
    """Safe, fixed user-facing diagnostic; never includes supplied values."""


def windows_console_available():
    """Windows getpass reads the console, independently of stdin.isatty()."""
    if sys.platform != "win32" or sys.stdin is not sys.__stdin__:
        return False
    import ctypes
    import msvcrt
    from ctypes import wintypes
    try:
        with open("CONIN$", "rb", buffering=0) as console:
            mode = wintypes.DWORD()
            get_mode = ctypes.WinDLL("kernel32", use_last_error=True).GetConsoleMode
            get_mode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            get_mode.restype = wintypes.BOOL
            return bool(get_mode(msvcrt.get_osfhandle(console.fileno()), ctypes.byref(mode)))
    except OSError:
        return False


def validate_destination(app, destination):
    raw = Path(destination).expanduser()
    target = raw.resolve()
    default = Path(app.__file__).resolve().parent / "securityops.db"
    # Protect the configured usual DB, the default DB and its legacy backup family.
    for usual in (default, app.DATABASE_PATH.resolve()):
        if target == usual or (target.parent == usual.parent and
                              target.name.casefold().startswith(usual.name.casefold())):
            raise DemoInputError("Ruta protegida: corresponde a la base habitual o a sus auxiliares.")
    if target.parent == default.parent and target.name.casefold().startswith("securityops-before-"):
        raise DemoInputError("Ruta protegida: corresponde a un respaldo de la base habitual.")
    if os.path.lexists(raw) or target.exists():
        raise DemoInputError("Ruta existente: el destino ya existe; elegí un archivo nuevo. No se sobrescribe ningún archivo.")
    if target.suffix.casefold() != ".db":
        raise DemoInputError("Ruta inválida: usá un archivo con extensión .db (excluido de Git).")
    if not target.parent.is_dir():
        raise DemoInputError("Ruta inválida: el directorio de destino debe existir.")
    for suffix in ("-journal", "-wal", "-shm"):
        if os.path.lexists(str(target) + suffix):
            raise DemoInputError("Ruta existente: ya existen archivos auxiliares del destino.")
    return target


def prompt_passwords(app):
    interactive = windows_console_available() if sys.platform == "win32" else sys.stdin.isatty()
    if not interactive:
        raise DemoInputError("Entrada no interactiva: no hay una consola disponible para leer contraseñas ocultas. Ejecutá el comando directamente en una terminal PowerShell.")
    passwords = {}
    # Abort rather than falling back to an echoed password prompt.
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        for _, _, _, email in ACCOUNTS:
            password = getpass(f"Contraseña para {email} (12–128 caracteres): ")
            confirmation = getpass("Confirmá la contraseña: ")
            if not app.PASSWORD_MIN_LENGTH <= len(password) <= 128:
                raise DemoInputError("Contraseña inválida: debe contener entre 12 y 128 caracteres.")
            if password != confirmation:
                raise DemoInputError("Confirmación incorrecta: las contraseñas no coinciden.")
            passwords[email] = password
    return passwords


def seed_demo(app, passwords):
    app.migrate_database()
    now = datetime.now(timezone.utc).isoformat()
    admins = {}
    # Only organizational/bootstrap administration lacks an authenticated actor.
    with closing(app.connect()) as connection, connection:
        connection.execute("UPDATE organizations SET name = 'Aurora Laboratorio (ficticia)' WHERE id = 1")
        connection.execute("INSERT INTO organizations (id, name, created_at) VALUES (2, ?, ?)",
                           ("Delta Taller (ficticia)", now))
        for org, role, name, email in ACCOUNTS:
            if role != "administrador":
                continue
            cursor = connection.execute(
                "INSERT INTO users (organization_id, role, display_name, email, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (org, role, name, email, app.hash_password(passwords[email]), now))
            admins[org] = dict(id=cursor.lastrowid, organization_id=org, role=role, display_name=name)
    members = {}
    for org, role, name, email in ACCOUNTS:
        if role != "administrador":
            member = app.create_user(app.UserCreate(display_name=name, email=email,
                                     password=passwords[email], role=role), admins[org])
            members[role] = member | {"organization_id": org}
    admin, analyst = admins[1], members["analista"]
    assets = [app.create_asset(app.AssetCreate(name=name, type=kind, criticality=criticality,
              description="Recurso completamente ficticio para la demostración."), analyst)
              for name, kind, criticality in (
                  ("Servidor Atlas", "hardware", "high"),
                  ("Portal Boreal", "software", "medium"),
                  ("Correo Nube Clara", "service", "critical"),
                  ("Catálogo de muestras sintéticas", "data", "low"))]
    for title, severity, states, asset_indices in (
        ("Correo sospechoso en Nube Clara", "high", ["investigating"], [1, 2]),
        ("Interrupción simulada de Atlas", "critical", [], [0]),
        ("Acceso de prueba revisado", "low", ["investigating", "resolved"], [3])):
        item = app.create_incident(app.IncidentCreate(title=title, severity=severity,
                                  description="Escenario inventado; sin evidencia ni personas reales."), analyst)
        for index in asset_indices:
            app.link_incident_asset(item["id"], app.IncidentAssetCreate(asset_id=assets[index]["id"]), analyst)
        if states:
            app.assign_incident(item["id"], app.AssigneeUpdate(assignee_id=analyst["id"]), admin)
        for state in states:
            app.update_incident_status(item["id"], app.IncidentStatusUpdate(status=state), analyst)
        app.create_incident_note(item["id"], app.IncidentNoteCreate(
            content="Simulación: se revisaron registros sintéticos; se documentó el siguiente paso de investigación."), analyst)
    controls = [app.create_control(app.ControlCreate(name=name, type=kind, status=status), analyst)
                for name, kind, status in (
                    ("Segundo factor simulado", "preventive", "implemented"),
                    ("Revisión de alertas sintéticas", "detective", "planned"),
                    ("Restauración de laboratorio", "corrective", "retired"))]
    for title, probability, impact, status, index in (
        ("Acceso indebido al correo ficticio", 4, 5, "treating", 2),
        ("Indisponibilidad del servidor ficticio", 3, 4, "identified", 0),
        ("Pérdida de muestras sintéticas", 1, 2, "accepted", 3)):
        risk = app.create_risk(app.RiskCreate(title=title, probability=probability, impact=impact,
                              status=status, asset_id=assets[index]["id"]), analyst)
        if status == "treating":
            app.assign_risk(risk["id"], app.AssigneeUpdate(assignee_id=analyst["id"]), admin)
            for control in controls[:2]:
                app.link_risk_control(risk["id"], app.RiskControlCreate(control_id=control["id"]), analyst)
            for residual in (3, 2):
                app.create_risk_assessment(risk["id"], app.RiskAssessmentCreate(
                    residual_probability=residual, residual_impact=4,
                    justification="Estimación manual ficticia para comparar instantáneas; no demuestra eficacia de controles."), analyst)
    other = admins[2]
    asset = app.create_asset(app.AssetCreate(name="Estación Delta exclusiva", type="hardware", criticality="medium"), other)
    incident = app.create_incident(app.IncidentCreate(title="Revisión exclusiva de Delta", severity="medium",
                                  description="Escenario ficticio de la segunda organización."), other)
    app.link_incident_asset(incident["id"], app.IncidentAssetCreate(asset_id=asset["id"]), other)
    app.assign_incident(incident["id"], app.AssigneeUpdate(assignee_id=other["id"]), other)
    app.create_incident_note(incident["id"], app.IncidentNoteCreate(content="Nota ficticia visible únicamente en Delta."), other)


def create_demo(app, destination):
    original = app.DATABASE_PATH
    reserved = False
    try:
        target = validate_destination(app, destination)
        passwords = prompt_passwords(app)
        # Exclusive creation also closes the race between validation and creation.
        with target.open("xb"):
            pass
        reserved = True
        app.DATABASE_PATH = target
        seed_demo(app, passwords)
        print(f"Demo ficticia creada en {target}")
        return 0
    except DemoInputError as error:
        print(str(error), file=sys.stderr)
        return 1
    except FileExistsError:
        print("Ruta existente: el destino fue creado por otro proceso; no se sobrescribió.", file=sys.stderr)
        return 1
    except (GetPassWarning, EOFError):
        print("Entrada no interactiva: no se pudo leer una contraseña oculta. Usá una consola PowerShell.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Creación cancelada por el usuario.", file=sys.stderr)
        return 1
    except Exception:
        # Exception messages/tracebacks may contain Pydantic inputs or credentials.
        print("Fallo interno al crear la demo; no se muestran detalles que puedan contener secretos."
              + (" El archivo nuevo puede haber quedado parcialmente creado; elegí otra ruta para reintentar." if reserved else
                 " No se creó la base de demostración."), file=sys.stderr)
        return 1
    finally:
        app.DATABASE_PATH = original
