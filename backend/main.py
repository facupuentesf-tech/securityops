import argparse
import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import sys
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from getpass import fallback_getpass, getpass
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


DATABASE_PATH = Path(
    os.environ.get("SECURITYOPS_DATABASE", Path(__file__).resolve().parent / "securityops.db")
).expanduser().resolve()
MIGRATIONS_PATH = Path(__file__).resolve().parent / "migrations"
SESSION_COOKIE = "securityops_session"
SESSION_LIFETIME = 12 * 60 * 60
PASSWORD_MIN_LENGTH = 12
ROLES = ("administrador", "analista", "lector")
Email = Annotated[str, StringConstraints(
    strip_whitespace=True,
    min_length=3,
    max_length=254,
    pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Password = Annotated[str, StringConstraints(min_length=PASSWORD_MIN_LENGTH, max_length=128)]


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate_database() -> None:
    with closing(connect()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        migrations = sorted(MIGRATIONS_PATH.glob("[0-9][0-9][0-9]_*.sql"))
        for migration in migrations:
            version = int(migration.name[:3])
            if version in applied:
                continue
            script = migration.read_text(encoding="utf-8")
            applied_at = datetime.now(timezone.utc).isoformat()
            transaction = (
                "BEGIN IMMEDIATE;\n"
                + script
                + "\nINSERT INTO schema_migrations (version, applied_at) VALUES ("
                + str(version)
                + ", '"
                + applied_at
                + "');\nCOMMIT;"
            )
            try:
                connection.executescript(transaction)
            except sqlite3.Error:
                if connection.in_transaction:
                    connection.rollback()
                raise


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"scrypt$16384$8$1${salt_text}${digest_text}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = stored_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


def public_user(row: sqlite3.Row | dict) -> dict:
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def session_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with closing(connect()) as connection:
        row = connection.execute(
            """
            SELECT s.csrf_token, s.expires_at, u.id, u.display_name, u.email, u.role,
                   u.is_active, u.organization_id
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
    if row is None or row["expires_at"] <= int(datetime.now(timezone.utc).timestamp()) or not row["is_active"]:
        return None
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied_csrf = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(supplied_csrf, row["csrf_token"]):
            raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "email": row["email"],
        "role": row["role"],
        "organization_id": row["organization_id"],
        "csrf_token": row["csrf_token"],
    }


def require_user(request: Request) -> dict:
    user = session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_roles(*roles: str):
    def dependency(user: dict = Depends(require_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName
    email: Email
    password: Password
    role: Literal["administrador", "analista", "lector"]


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName | None = None
    email: Email | None = None
    role: Literal["administrador", "analista", "lector"] | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: Password


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    type: Literal["hardware", "software", "service", "data"]
    description: str | None = None
    criticality: Literal["low", "medium", "high", "critical"]


class Asset(AssetCreate):
    model_config = ConfigDict(extra="ignore")

    id: int
    created_at: datetime


class IncidentAssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: int = Field(strict=True, gt=0)


RiskLevel = Literal["low", "medium", "high", "critical"]
RiskStatus = Literal["identified", "treating", "accepted"]
RISK_LEVEL_RANGES = {"low": (1, 4), "medium": (5, 9), "high": (10, 16), "critical": (17, 25)}


class RiskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    description: str | None = None
    probability: int = Field(strict=True, ge=1, le=5)
    impact: int = Field(strict=True, ge=1, le=5)
    status: RiskStatus = "identified"
    asset_id: int | None = Field(default=None, strict=True, gt=0)


class Risk(RiskCreate):
    model_config = ConfigDict(extra="ignore")

    id: int
    created_at: datetime
    score: int
    level: RiskLevel
    asset_name: str | None = None


def risk_level(score: int) -> str:
    for level, (minimum, maximum) in RISK_LEVEL_RANGES.items():
        if minimum <= score <= maximum:
            return level
    raise ValueError("Risk score must be between 1 and 25")


def public_risk(row: sqlite3.Row) -> dict:
    risk = dict(row)
    risk["score"] = risk["probability"] * risk["impact"]
    risk["level"] = risk_level(risk["score"])
    return risk


RISK_SELECT = (
    "SELECT r.*, a.name AS asset_name FROM risks r LEFT JOIN assets a "
    "ON a.id = r.asset_id AND a.organization_id = r.organization_id "
)


def require_risk_asset(connection: sqlite3.Connection, asset_id: int | None, organization_id: int) -> None:
    if asset_id is not None and connection.execute(
        "SELECT id FROM assets WHERE id = ? AND organization_id = ?",
        (asset_id, organization_id),
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Asset not found")


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, pattern=r"\S")
    description: str = Field(min_length=1, pattern=r"\S")
    severity: Literal["low", "medium", "high", "critical"]
    status: Literal["open", "investigating", "resolved"] = "open"


class Incident(IncidentCreate):
    model_config = ConfigDict(extra="ignore")

    id: int
    created_at: datetime


class IncidentStatusUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved"]


class IncidentStatusHistory(BaseModel):
    id: int
    incident_id: int
    previous_status: Literal["open", "investigating", "resolved"]
    new_status: Literal["open", "investigating", "resolved"]
    changed_at: datetime
    changed_by: int | None = None
    changed_by_name: str | None = None


class IncidentNoteCreate(BaseModel):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class IncidentNote(IncidentNoteCreate):
    id: int
    incident_id: int
    created_at: datetime
    created_by: int | None = None
    created_by_name: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_database()
    yield


app = FastAPI(title="SecurityOps", lifespan=lifespan)
STATIC_PATH = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_PATH / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/login")
def login(credentials: LoginRequest, request: Request, response: Response):
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            (credentials.email.strip().lower(),),
        ).fetchone()
    if row is None or not row["is_active"] or not verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    csrf_token = secrets.token_urlsafe(32)
    expires_at = int(datetime.now(timezone.utc).timestamp()) + SESSION_LIFETIME
    with closing(connect()) as connection, connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(datetime.now(timezone.utc).timestamp()),))
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash, row["id"], csrf_token, expires_at),
        )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
        max_age=SESSION_LIFETIME,
    )
    return {"user": public_user(row), "csrf_token": csrf_token}


@app.get("/auth/session")
def get_session(request: Request):
    user = session_user(request)
    if user is None:
        return {"user": None, "csrf_token": None}
    return {
        "user": {
            key: value for key, value in user.items()
            if key not in {"csrf_token", "organization_id"}
        },
        "csrf_token": user["csrf_token"],
    }


@app.post("/auth/logout")
def logout(request: Request, response: Response, user: dict = Depends(require_user)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with closing(connect()) as connection, connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
    )
    return {"status": "ok"}


@app.get("/users")
def list_users(actor: dict = Depends(require_roles("administrador"))):
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT id, display_name, email, role, is_active, created_at "
            "FROM users WHERE organization_id = ? ORDER BY id",
            (actor["organization_id"],),
        ).fetchall()
    return [public_user(row) for row in rows]


@app.post("/users", status_code=201)
def create_user(user: UserCreate, actor: dict = Depends(require_roles("administrador"))):
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with closing(connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO users (display_name, email, password_hash, role, created_at, organization_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user.display_name.strip(),
                    user.email.strip().lower(),
                    hash_password(user.password),
                    user.role,
                    created_at,
                    actor["organization_id"],
                ),
            )
            row = connection.execute(
                "SELECT id, display_name, email, role, is_active, created_at FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        if "users.email" in str(error):
            raise HTTPException(status_code=409, detail="A user with this email already exists") from error
        raise
    return public_user(row)


@app.patch("/users/{user_id}")
def update_user(user_id: int, update: UserUpdate, actor: dict = Depends(require_roles("administrador"))):
    changes = update.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Provide non-null user fields to update")
    if "display_name" in changes:
        changes["display_name"] = changes["display_name"].strip()
    if "email" in changes:
        changes["email"] = changes["email"].strip().lower()
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        target = connection.execute(
            "SELECT * FROM users WHERE id = ? AND organization_id = ?",
            (user_id, actor["organization_id"]),
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        will_be_admin = changes.get("role", target["role"]) == "administrador"
        will_be_active = changes.get("is_active", bool(target["is_active"]))
        if target["id"] == actor["id"] and not will_be_active:
            raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
        if target["role"] == "administrador" and target["is_active"] and not (will_be_admin and will_be_active):
            remaining = connection.execute(
                "SELECT COUNT(*) FROM users "
                "WHERE organization_id = ? AND role = 'administrador' AND is_active = 1 AND id <> ?",
                (actor["organization_id"], user_id),
            ).fetchone()[0]
            if remaining == 0:
                raise HTTPException(status_code=409, detail="At least one active administrator is required")
        assignments = ", ".join(f"{field} = ?" for field in changes)
        try:
            connection.execute(
                f"UPDATE users SET {assignments} WHERE id = ? AND organization_id = ?",
                (*changes.values(), user_id, actor["organization_id"]),
            )
        except sqlite3.IntegrityError as error:
            if "users.email" in str(error):
                raise HTTPException(status_code=409, detail="A user with this email already exists") from error
            raise
        row = connection.execute(
            "SELECT id, display_name, email, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return public_user(row)


@app.post("/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    reset: PasswordReset,
    actor: dict = Depends(require_roles("administrador")),
):
    with closing(connect()) as connection, connection:
        target = connection.execute(
            "SELECT id FROM users WHERE id = ? AND organization_id = ?",
            (user_id, actor["organization_id"]),
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ? AND organization_id = ?",
            (hash_password(reset.password), user_id, actor["organization_id"]),
        )
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return {"status": "ok"}


@app.post("/risks", response_model=Risk, status_code=201)
def create_risk(risk: RiskCreate, user: dict = Depends(require_roles("administrador", "analista"))):
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        require_risk_asset(connection, risk.asset_id, user["organization_id"])
        cursor = connection.execute(
            "INSERT INTO risks (organization_id, title, description, probability, impact, status, asset_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user["organization_id"], risk.title, risk.description, risk.probability,
             risk.impact, risk.status, risk.asset_id, created_at),
        )
        row = connection.execute(RISK_SELECT + "WHERE r.id = ? AND r.organization_id = ?",
                                 (cursor.lastrowid, user["organization_id"])).fetchone()
    return public_risk(row)


@app.get("/risks", response_model=list[Risk])
def list_risks(status: RiskStatus | None = None, level: RiskLevel | None = None,
               asset_id: Annotated[int | None, Query(gt=0)] = None,
               user: dict = Depends(require_user)):
    conditions = ["r.organization_id = ?"]
    parameters = [user["organization_id"]]
    if status is not None:
        conditions.append("r.status = ?")
        parameters.append(status)
    if level is not None:
        conditions.append("r.probability * r.impact BETWEEN ? AND ?")
        parameters.extend(RISK_LEVEL_RANGES[level])
    if asset_id is not None:
        conditions.append("r.asset_id = ?")
        parameters.append(asset_id)
    with closing(connect()) as connection:
        require_risk_asset(connection, asset_id, user["organization_id"])
        rows = connection.execute(RISK_SELECT + "WHERE " + " AND ".join(conditions) + " ORDER BY r.id",
                                  parameters).fetchall()
    return [public_risk(row) for row in rows]


@app.get("/risks/{risk_id}", response_model=Risk)
def get_risk(risk_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        row = connection.execute(RISK_SELECT + "WHERE r.id = ? AND r.organization_id = ?",
                                 (risk_id, user["organization_id"])).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    return public_risk(row)


@app.post("/assets", response_model=Asset, status_code=201)
def create_asset(
    asset: AssetCreate,
    user: dict = Depends(require_roles("administrador", "analista")),
):
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect()) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO assets (organization_id, name, type, description, criticality, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user["organization_id"], asset.name, asset.type, asset.description,
             asset.criticality, created_at),
        )
        row = connection.execute(
            "SELECT * FROM assets WHERE id = ? AND organization_id = ?",
            (cursor.lastrowid, user["organization_id"]),
        ).fetchone()
    return dict(row)


@app.get("/assets", response_model=list[Asset])
def list_assets(
    type: Literal["hardware", "software", "service", "data"] | None = None,
    criticality: Literal["low", "medium", "high", "critical"] | None = None,
    user: dict = Depends(require_user),
):
    conditions = ["organization_id = ?"]
    parameters = [user["organization_id"]]
    if type is not None:
        conditions.append("type = ?")
        parameters.append(type)
    if criticality is not None:
        conditions.append("criticality = ?")
        parameters.append(criticality)
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM assets WHERE " + " AND ".join(conditions) + " ORDER BY id",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/assets/{asset_id}", response_model=Asset)
def get_asset(asset_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM assets WHERE id = ? AND organization_id = ?",
            (asset_id, user["organization_id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return dict(row)


def require_incident_asset_resources(connection, incident_id, organization_id, asset_id=None):
    if connection.execute(
        "SELECT id FROM incidents WHERE id = ? AND organization_id = ?",
        (incident_id, organization_id),
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if asset_id is not None and connection.execute(
        "SELECT id FROM assets WHERE id = ? AND organization_id = ?",
        (asset_id, organization_id),
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Asset not found")


@app.get("/incidents/{incident_id}/assets", response_model=list[Asset])
def list_incident_assets(incident_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        require_incident_asset_resources(connection, incident_id, user["organization_id"])
        rows = connection.execute(
            "SELECT a.* FROM assets a JOIN incident_assets ia "
            "ON a.id = ia.asset_id AND a.organization_id = ia.organization_id "
            "WHERE ia.incident_id = ? AND ia.organization_id = ? ORDER BY a.id",
            (incident_id, user["organization_id"]),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/incidents/{incident_id}/assets", status_code=201)
def link_incident_asset(incident_id: int, link: IncidentAssetCreate,
                        user: dict = Depends(require_roles("administrador", "analista"))):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        require_incident_asset_resources(connection, incident_id, user["organization_id"], link.asset_id)
        if connection.execute(
            "SELECT 1 FROM incident_assets WHERE incident_id = ? AND asset_id = ?",
            (incident_id, link.asset_id),
        ).fetchone():
            raise HTTPException(status_code=409, detail="Asset already linked")
        connection.execute(
            "INSERT INTO incident_assets (incident_id, asset_id, organization_id) VALUES (?, ?, ?)",
            (incident_id, link.asset_id, user["organization_id"]),
        )
    return {"incident_id": incident_id, "asset_id": link.asset_id}


@app.delete("/incidents/{incident_id}/assets/{asset_id}", status_code=204)
def unlink_incident_asset(incident_id: int, asset_id: int,
                          user: dict = Depends(require_roles("administrador", "analista"))):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        require_incident_asset_resources(connection, incident_id, user["organization_id"], asset_id)
        cursor = connection.execute(
            "DELETE FROM incident_assets WHERE incident_id = ? AND asset_id = ? AND organization_id = ?",
            (incident_id, asset_id, user["organization_id"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Link not found")
    return Response(status_code=204)


@app.post("/incidents", response_model=Incident, status_code=201)
def create_incident(
    incident: IncidentCreate,
    user: dict = Depends(require_roles("administrador", "analista")),
):
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect()) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO incidents "
            "(title, description, severity, status, created_at, organization_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                incident.title, incident.description, incident.severity, incident.status,
                created_at, user["organization_id"],
            ),
        )
        row = connection.execute("SELECT * FROM incidents WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.patch("/incidents/{incident_id}/status", response_model=Incident)
def update_incident_status(
    incident_id: int,
    update: IncidentStatusUpdate,
    user: dict = Depends(require_roles("administrador", "analista")),
):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ? AND organization_id = ?",
            (incident_id, user["organization_id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        if row["status"] != update.status:
            connection.execute(
                "UPDATE incidents SET status = ? WHERE id = ? AND organization_id = ?",
                (update.status, incident_id, user["organization_id"]),
            )
            connection.execute(
                "INSERT INTO incident_status_history "
                "(incident_id, previous_status, new_status, changed_at, changed_by) VALUES (?, ?, ?, ?, ?)",
                (
                    incident_id,
                    row["status"],
                    update.status,
                    datetime.now(timezone.utc).isoformat(),
                    user["id"],
                ),
            )
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ? AND organization_id = ?",
            (incident_id, user["organization_id"]),
        ).fetchone()
    return dict(row)


@app.get("/incidents/{incident_id}/history", response_model=list[IncidentStatusHistory])
def get_incident_history(incident_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        incident = connection.execute(
            "SELECT id FROM incidents WHERE id = ? AND organization_id = ?",
            (incident_id, user["organization_id"]),
        ).fetchone()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        rows = connection.execute(
            """
            SELECT h.*, u.display_name AS changed_by_name
            FROM incident_status_history h
            LEFT JOIN users u ON u.id = h.changed_by
            WHERE h.incident_id = ? ORDER BY h.id
            """,
            (incident_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/incidents/{incident_id}/notes", response_model=IncidentNote, status_code=201)
def create_incident_note(
    incident_id: int,
    note: IncidentNoteCreate,
    user: dict = Depends(require_roles("administrador", "analista")),
):
    with closing(connect()) as connection, connection:
        incident = connection.execute(
            "SELECT id FROM incidents WHERE id = ? AND organization_id = ?",
            (incident_id, user["organization_id"]),
        ).fetchone()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        cursor = connection.execute(
            "INSERT INTO incident_notes (incident_id, content, created_at, created_by) VALUES (?, ?, ?, ?)",
            (incident_id, note.content, datetime.now(timezone.utc).isoformat(), user["id"]),
        )
        row = connection.execute(
            """
            SELECT n.*, u.display_name AS created_by_name
            FROM incident_notes n
            LEFT JOIN users u ON u.id = n.created_by
            WHERE n.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


@app.get("/incidents/{incident_id}/notes", response_model=list[IncidentNote])
def list_incident_notes(incident_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        incident = connection.execute(
            "SELECT id FROM incidents WHERE id = ? AND organization_id = ?",
            (incident_id, user["organization_id"]),
        ).fetchone()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        rows = connection.execute(
            """
            SELECT n.*, u.display_name AS created_by_name
            FROM incident_notes n
            LEFT JOIN users u ON u.id = n.created_by
            WHERE n.incident_id = ? ORDER BY n.created_at, n.id
            """,
            (incident_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/incidents", response_model=list[Incident])
def list_incidents(
    status: Literal["open", "investigating", "resolved"] | None = None,
    severity: Literal["low", "medium", "high", "critical"] | None = None,
    user: dict = Depends(require_user),
):
    conditions = ["organization_id = ?"]
    parameters = [user["organization_id"]]
    if status is not None:
        conditions.append("status = ?")
        parameters.append(status)
    if severity is not None:
        conditions.append("severity = ?")
        parameters.append(severity)
    query = "SELECT * FROM incidents"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id"
    with closing(connect()) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ? AND organization_id = ?",
            (incident_id, user["organization_id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)


def prompt_admin_details() -> tuple[str, str, str] | None:
    email = input("Correo del administrador: ").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        print("Ingresá una dirección de correo válida.", file=sys.stderr)
        return None
    display_name = input("Nombre del administrador: ").strip()
    if not display_name or len(display_name) > 120:
        print("El nombre debe contener entre 1 y 120 caracteres.", file=sys.stderr)
        return None
    if sys.stdin.isatty():
        password_reader = getpass
    else:
        password_reader = fallback_getpass
    password = password_reader("Contraseña (mínimo 12 caracteres): ")
    confirmation = password_reader("Confirmá la contraseña: ")
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > 128:
        print("La contraseña debe contener entre 12 y 128 caracteres.", file=sys.stderr)
        return None
    if password != confirmation:
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return None
    return email, display_name, password


def create_first_admin() -> int:
    migrate_database()
    with closing(connect()) as connection:
        if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            print("Ya existen usuarios; el administrador inicial solo se puede crear en una base vacía.", file=sys.stderr)
            return 1
    account = prompt_admin_details()
    if account is None:
        return 1
    email, display_name, password = account
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            print("Ya existe un usuario; no se creó otro administrador inicial.", file=sys.stderr)
            return 1
        connection.execute(
            "INSERT INTO users "
            "(display_name, email, password_hash, role, created_at, organization_id) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (
                display_name,
                email,
                hash_password(password),
                "administrador",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    print(f"Administrador creado: {email}")
    return 0


def create_organization() -> int:
    migrate_database()
    with closing(connect()) as connection:
        unadministered = connection.execute(
            """
            SELECT COUNT(*)
            FROM organizations o
            WHERE NOT EXISTS (
                SELECT 1 FROM users u
                WHERE u.organization_id = o.id
                  AND u.role = 'administrador'
                  AND u.is_active = 1
            )
            """
        ).fetchone()[0]
    if unadministered:
        print(
            "Creá primero un administrador para cada organización existente.",
            file=sys.stderr,
        )
        return 1
    name = input("Nombre de la organización: ").strip()
    if not name or len(name) > 120:
        print("El nombre debe contener entre 1 y 120 caracteres.", file=sys.stderr)
        return 1
    account = prompt_admin_details()
    if account is None:
        return 1
    email, display_name, password = account
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with closing(connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            unadministered = connection.execute(
                """
                SELECT COUNT(*)
                FROM organizations o
                WHERE NOT EXISTS (
                    SELECT 1 FROM users u
                    WHERE u.organization_id = o.id
                      AND u.role = 'administrador'
                      AND u.is_active = 1
                )
                """
            ).fetchone()[0]
            if unadministered:
                print(
                    "Creá primero un administrador para cada organización existente.",
                    file=sys.stderr,
                )
                return 1
            if connection.execute(
                "SELECT 1 FROM organizations WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone():
                print("Ya existe una organización con ese nombre.", file=sys.stderr)
                return 1
            cursor = connection.execute(
                "INSERT INTO organizations (name, created_at) VALUES (?, ?)",
                (name, created_at),
            )
            organization_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO users "
                "(display_name, email, password_hash, role, created_at, organization_id) "
                "VALUES (?, ?, ?, 'administrador', ?, ?)",
                (
                    display_name,
                    email,
                    hash_password(password),
                    created_at,
                    organization_id,
                ),
            )
    except sqlite3.IntegrityError as error:
        if "users.email" in str(error):
            print("Ya existe un usuario con ese correo.", file=sys.stderr)
            return 1
        raise
    print(f"Organización y administrador creados: {name} ({email})")
    return 0


def run_cli() -> int:
    parser = argparse.ArgumentParser(description="Herramientas locales de SecurityOps")
    parser.add_argument(
        "command",
        choices=("create-admin", "create-organization"),
        help="crear el primer administrador o una organización con su administrador",
    )
    arguments = parser.parse_args()
    if arguments.command == "create-admin":
        return create_first_admin()
    if arguments.command == "create-organization":
        return create_organization()
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
