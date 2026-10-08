import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from getpass import fallback_getpass, getpass
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


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


AuditAction = Literal["created", "status_changed", "note_created", "linked", "unlinked",
                      "assignee_changed", "role_changed", "deactivated", "reactivated",
                      "password_reset", "user_updated", "updated", "assessed"]
AuditResource = Literal["incident", "asset", "risk", "control", "user"]
# Each event has an explicit allowlist; free text and credentials are never details.
AUDIT_DETAIL_KEYS = {
    "assessed": {"assessment_id", "original_probability", "original_impact", "original_score",
                 "residual_probability", "residual_impact", "residual_score"},
    "created": {"asset_id"}, "status_changed": {"previous_status", "new_status"},
    "note_created": {"note_id"}, "linked": {"asset_id", "control_id"},
    "unlinked": {"asset_id", "control_id"},
    "assignee_changed": {"previous_assignee_id", "new_assignee_id", "automatic", "user_id"},
    "role_changed": {"previous_role", "new_role"},
    "deactivated": {"previous_is_active", "new_is_active"},
    "reactivated": {"previous_is_active", "new_is_active"},
    "password_reset": set(), "user_updated": {"display_name_changed", "email_changed"},
    "updated": {"name_changed", "title_changed", "description_changed",
                "previous_type", "new_type", "previous_status", "new_status",
                "previous_criticality", "new_criticality", "previous_probability", "new_probability",
                "previous_impact", "new_impact", "previous_asset_id", "new_asset_id"},
}


def record_audit(connection, actor, action, resource_type, resource_id, **details):
    if action not in AUDIT_DETAIL_KEYS or set(details) - AUDIT_DETAIL_KEYS[action]:
        raise ValueError("Unsupported audit details")
    # Only identifiers, fixed enumerations and flags supplied by these call sites.
    connection.execute(
        "INSERT INTO audit_logs (organization_id, actor_id, actor_name, action, "
        "resource_type, resource_id, occurred_at, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (actor["organization_id"], actor["id"], actor["display_name"], action,
         resource_type, resource_id, datetime.now(timezone.utc).isoformat(),
         json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


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


class PartialResourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nullable_fields: ClassVar[set[str]] = {"description"}

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide fields to update")
        if any(getattr(self, field) is None for field in self.model_fields_set - self.nullable_fields):
            raise ValueError("Only optional fields accept null")
        return self


class AssetUpdate(PartialResourceUpdate):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    description: str | None = None
    type: Literal["hardware", "software", "service", "data"] | None = None
    criticality: Literal["low", "medium", "high", "critical"] | None = None


class ControlUpdate(PartialResourceUpdate):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    description: str | None = None
    type: Literal["preventive", "detective", "corrective"] | None = None
    status: Literal["planned", "implemented", "retired"] | None = None


class Asset(AssetCreate):
    model_config = ConfigDict(extra="ignore")

    id: int
    created_at: datetime


class IncidentAssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: int = Field(strict=True, gt=0)


class ControlCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    description: str | None = None
    type: Literal["preventive", "detective", "corrective"]
    status: Literal["planned", "implemented", "retired"] = "planned"


class SecurityControl(ControlCreate):
    model_config = ConfigDict(extra="ignore")

    id: int
    created_at: datetime


class RiskControlCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_id: int = Field(strict=True, gt=0)


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


class RiskUpdate(PartialResourceUpdate):
    nullable_fields: ClassVar[set[str]] = {"description", "asset_id"}
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    description: str | None = None
    probability: int | None = Field(default=None, strict=True, ge=1, le=5)
    impact: int | None = Field(default=None, strict=True, ge=1, le=5)
    status: RiskStatus | None = None
    asset_id: int | None = Field(default=None, strict=True, gt=0)


class RiskAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    residual_probability: int = Field(strict=True, ge=1, le=5)
    residual_impact: int = Field(strict=True, ge=1, le=5)
    justification: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class RiskAssessment(RiskAssessmentCreate):
    model_config = ConfigDict(extra="ignore")
    id: int
    risk_id: int
    evaluator_id: int
    evaluator_name: str
    created_at: datetime
    original_probability: int
    original_impact: int
    original_score: int
    original_level: RiskLevel
    residual_score: int
    residual_level: RiskLevel


def public_assessment(row):
    result = dict(row)
    result["original_level"] = risk_level(result["original_score"])
    result["residual_score"] = result["residual_probability"] * result["residual_impact"]
    result["residual_level"] = risk_level(result["residual_score"])
    return result


class Risk(RiskCreate):
    model_config = ConfigDict(extra="ignore")

    id: int
    created_at: datetime
    score: int
    level: RiskLevel
    asset_name: str | None = None
    assignee_id: int | None = None
    assignee_name: str | None = None


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
    "SELECT r.*, a.name AS asset_name, u.display_name AS assignee_name FROM risks r LEFT JOIN assets a "
    "ON a.id = r.asset_id AND a.organization_id = r.organization_id "
    "LEFT JOIN users u ON u.id = r.assignee_id AND u.organization_id = r.organization_id "
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
    assignee_id: int | None = None
    assignee_name: str | None = None


class AssigneeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee_id: int | None = Field(strict=True, gt=0)


class AssigneeCandidate(BaseModel):
    id: int
    display_name: str


INCIDENT_SELECT = (
    "SELECT i.*, u.display_name AS assignee_name FROM incidents i "
    "LEFT JOIN users u ON u.id = i.assignee_id AND u.organization_id = i.organization_id "
)


def require_assignee(connection, assignee_id, organization_id, eligible=False):
    if assignee_id is None:
        return
    row = connection.execute(
        "SELECT role, is_active FROM users WHERE id = ? AND organization_id = ?",
        (assignee_id, organization_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    if eligible and (not row["is_active"] or row["role"] not in ("administrador", "analista")):
        raise HTTPException(status_code=422, detail="Assignee must be an active administrator or analyst")


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


@app.get("/dashboard")
def dashboard(user: dict = Depends(require_user)):
    organization = (user["organization_id"],)

    def distribution(connection, table, column, categories):
        # Table/column names are constants from the calls below, never client input.
        counts = dict.fromkeys(categories, 0)
        for row in connection.execute(
            f"SELECT {column} AS category, COUNT(*) AS amount FROM {table} "
            f"WHERE organization_id = ? GROUP BY {column}", organization,
        ):
            counts[row["category"]] = row["amount"]
        return counts

    with closing(connect()) as connection, connection:
        connection.execute("BEGIN")
        incident_states = distribution(connection, "incidents", "status", ("open", "investigating", "resolved"))
        incident_severities = distribution(connection, "incidents", "severity", ("low", "medium", "high", "critical"))
        pending_unassigned = connection.execute(
            "SELECT COUNT(*) FROM incidents WHERE organization_id = ? "
            "AND status IN ('open', 'investigating') AND assignee_id IS NULL", organization,
        ).fetchone()[0]
        recent = connection.execute(
            "SELECT id, title, status, severity, created_at FROM incidents WHERE organization_id = ? "
            "AND status IN ('open', 'investigating') ORDER BY created_at DESC, id DESC LIMIT 5", organization,
        ).fetchall()
        asset_criticalities = distribution(connection, "assets", "criticality", ("low", "medium", "high", "critical"))
        risk_states = distribution(connection, "risks", "status", ("identified", "treating", "accepted"))
        risk_levels = dict.fromkeys(RISK_LEVEL_RANGES, 0)
        for row in connection.execute(
            "SELECT probability * impact AS score, COUNT(*) AS amount FROM risks "
            "WHERE organization_id = ? GROUP BY probability * impact", organization,
        ):
            risk_levels[risk_level(row["score"])] += row["amount"]
        risk_unassigned = connection.execute(
            "SELECT COUNT(*) FROM risks WHERE organization_id = ? "
            "AND status IN ('identified', 'treating') AND assignee_id IS NULL", organization,
        ).fetchone()[0]
        priority = connection.execute(
            "SELECT id, title, status, probability, impact, probability * impact AS score, created_at "
            "FROM risks WHERE organization_id = ? AND status IN ('identified', 'treating') "
            "ORDER BY score DESC, id DESC LIMIT 5", organization,
        ).fetchall()
        control_states = distribution(connection, "security_controls", "status", ("planned", "implemented", "retired"))
        generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": generated_at,
        "incidents": {"total": sum(incident_states.values()), "by_status": incident_states,
                      "by_severity": incident_severities,
                      "pending": {"total": incident_states["open"] + incident_states["investigating"],
                                  "unassigned": pending_unassigned, "recent": [dict(row) for row in recent]}},
        "assets": {"total": sum(asset_criticalities.values()), "by_criticality": asset_criticalities},
        "risks": {"total": sum(risk_states.values()), "by_status": risk_states, "by_level": risk_levels,
                  "unassigned_pending": risk_unassigned,
                  "priority": [dict(row) | {"level": risk_level(row["score"])} for row in priority]},
        "controls": {"total": sum(control_states.values()), "by_status": control_states},
    }


@app.get("/audit-logs")
def list_audit_logs(
    actor_id: Annotated[int | None, Query(gt=0)] = None,
    action: AuditAction | None = None,
    resource_type: AuditResource | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: Annotated[int, Query(ge=1, le=1000000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    actor: dict = Depends(require_roles("administrador")),
):
    for value in (date_from, date_to):
        if value is not None and value.utcoffset() is None:
            raise HTTPException(status_code=422, detail="Audit dates must include a timezone")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not exceed date_to")
    conditions = ["organization_id = ?"]
    parameters = [actor["organization_id"]]
    for column, value in (("actor_id", actor_id), ("action", action), ("resource_type", resource_type)):
        if value is not None:
            conditions.append(column + " = ?")
            parameters.append(value)
    for operator, value in ((">=", date_from), ("<=", date_to)):
        if value is not None:
            conditions.append("occurred_at " + operator + " ?")
            parameters.append(value.astimezone(timezone.utc).isoformat())
    where = " AND ".join(conditions)
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN")
        total = connection.execute("SELECT COUNT(*) FROM audit_logs WHERE " + where, parameters).fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM audit_logs WHERE " + where + " ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?",
            (*parameters, page_size, (page - 1) * page_size),
        ).fetchall()
    return {"items": [dict(row) | {"details": json.loads(row["details"])} for row in rows],
            "total": total, "page": page, "page_size": page_size}


@app.get("/users")
def list_users(actor: dict = Depends(require_roles("administrador"))):
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT id, display_name, email, role, is_active, created_at "
            "FROM users WHERE organization_id = ? ORDER BY id",
            (actor["organization_id"],),
        ).fetchall()
    return [public_user(row) for row in rows]


@app.get("/assignees", response_model=list[AssigneeCandidate])
def list_assignees(user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT id, display_name FROM users WHERE organization_id = ? "
            "AND is_active = 1 AND role IN ('administrador', 'analista') ORDER BY id",
            (user["organization_id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@app.patch("/incidents/{incident_id}/assignee", response_model=Incident)
def assign_incident(incident_id: int, update: AssigneeUpdate,
                    user: dict = Depends(require_roles("administrador"))):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT assignee_id FROM incidents WHERE id = ? AND organization_id = ?",
                              (incident_id, user["organization_id"])).fetchone()
        if previous is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        require_assignee(connection, update.assignee_id, user["organization_id"], eligible=True)
        connection.execute("UPDATE incidents SET assignee_id = ? WHERE id = ? AND organization_id = ?",
                           (update.assignee_id, incident_id, user["organization_id"]))
        if previous["assignee_id"] != update.assignee_id:
            record_audit(connection, user, "assignee_changed", "incident", incident_id,
                         previous_assignee_id=previous["assignee_id"], new_assignee_id=update.assignee_id)
        row = connection.execute(INCIDENT_SELECT + "WHERE i.id = ? AND i.organization_id = ?",
                                 (incident_id, user["organization_id"])).fetchone()
    return dict(row)


@app.patch("/risks/{risk_id}/assignee", response_model=Risk)
def assign_risk(risk_id: int, update: AssigneeUpdate,
                user: dict = Depends(require_roles("administrador"))):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT assignee_id FROM risks WHERE id = ? AND organization_id = ?",
                              (risk_id, user["organization_id"])).fetchone()
        if previous is None:
            raise HTTPException(status_code=404, detail="Risk not found")
        require_assignee(connection, update.assignee_id, user["organization_id"], eligible=True)
        connection.execute("UPDATE risks SET assignee_id = ? WHERE id = ? AND organization_id = ?",
                           (update.assignee_id, risk_id, user["organization_id"]))
        if previous["assignee_id"] != update.assignee_id:
            record_audit(connection, user, "assignee_changed", "risk", risk_id,
                         previous_assignee_id=previous["assignee_id"], new_assignee_id=update.assignee_id)
        row = connection.execute(RISK_SELECT + "WHERE r.id = ? AND r.organization_id = ?",
                                 (risk_id, user["organization_id"])).fetchone()
    return public_risk(row)


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
            record_audit(connection, actor, "created", "user", cursor.lastrowid)
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
        changes = {key: value for key, value in changes.items() if value != target[key]}
        if not changes:
            return public_user(target)
        removed_assignments = []
        if not will_be_active or changes.get("role", target["role"]) == "lector":
            for table, resource_type in (("incidents", "incident"), ("risks", "risk")):
                removed_assignments.extend((resource_type, row["id"]) for row in connection.execute(
                    f"SELECT id FROM {table} WHERE assignee_id = ? AND organization_id = ? ORDER BY id",
                    (user_id, actor["organization_id"]),
                ))
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
        if "role" in changes:
            record_audit(connection, actor, "role_changed", "user", user_id,
                         previous_role=target["role"], new_role=changes["role"])
        if "is_active" in changes:
            record_audit(connection, actor, "reactivated" if will_be_active else "deactivated", "user", user_id,
                         previous_is_active=bool(target["is_active"]), new_is_active=bool(will_be_active))
        profile_changes = {key + "_changed": True for key in ("display_name", "email") if key in changes}
        if profile_changes:
            record_audit(connection, actor, "user_updated", "user", user_id, **profile_changes)
        for resource_type, resource_id in removed_assignments:
            record_audit(connection, actor, "assignee_changed", resource_type, resource_id,
                         previous_assignee_id=user_id, new_assignee_id=None, automatic=True, user_id=user_id)
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
        connection.execute("BEGIN IMMEDIATE")
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
        record_audit(connection, actor, "password_reset", "user", user_id)
    return {"status": "ok"}


def edit_resource(resource_type, resource_id, update, user):
    # Identifiers and SELECTs are internal constants; values are always bound.
    table, select = {
        "asset": ("assets", "SELECT * FROM assets WHERE id = ? AND organization_id = ?"),
        "risk": ("risks", RISK_SELECT + "WHERE r.id = ? AND r.organization_id = ?"),
        "control": ("security_controls", "SELECT * FROM security_controls WHERE id = ? AND organization_id = ?"),
    }[resource_type]
    parameters = (resource_id, user["organization_id"])
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(select, parameters).fetchone()
        if previous is None:
            raise HTTPException(status_code=404, detail=resource_type.capitalize() + " not found")
        supplied = update.model_dump(exclude_unset=True)
        if resource_type == "risk" and "asset_id" in supplied:
            require_risk_asset(connection, supplied["asset_id"], user["organization_id"])
        changes = {key: value for key, value in supplied.items() if previous[key] != value}
        if changes:
            assignments = ", ".join(field + " = ?" for field in changes)
            connection.execute(f"UPDATE {table} SET {assignments} WHERE id = ? AND organization_id = ?",
                               (*changes.values(), *parameters))
            details = {}
            for field, value in changes.items():
                if field in {"name", "title", "description"}:
                    details[field + "_changed"] = True
                else:
                    details["previous_" + field] = previous[field]
                    details["new_" + field] = value
            record_audit(connection, user, "updated", resource_type, resource_id, **details)
        row = connection.execute(select, parameters).fetchone()
    return public_risk(row) if resource_type == "risk" else dict(row)


@app.patch("/assets/{asset_id}", response_model=Asset)
def update_asset(asset_id: int, update: AssetUpdate,
                 user: dict = Depends(require_roles("administrador", "analista"))):
    return edit_resource("asset", asset_id, update, user)


@app.patch("/risks/{risk_id}", response_model=Risk)
def update_risk(risk_id: int, update: RiskUpdate,
                user: dict = Depends(require_roles("administrador", "analista"))):
    return edit_resource("risk", risk_id, update, user)


@app.patch("/controls/{control_id}", response_model=SecurityControl)
def update_control(control_id: int, update: ControlUpdate,
                   user: dict = Depends(require_roles("administrador", "analista"))):
    return edit_resource("control", control_id, update, user)


@app.post("/controls", response_model=SecurityControl, status_code=201)
def create_control(control: ControlCreate, user: dict = Depends(require_roles("administrador", "analista"))):
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect()) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO security_controls (organization_id, name, description, type, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user["organization_id"], control.name, control.description, control.type, control.status, created_at),
        )
        record_audit(connection, user, "created", "control", cursor.lastrowid)
        row = connection.execute(
            "SELECT * FROM security_controls WHERE id = ? AND organization_id = ?",
            (cursor.lastrowid, user["organization_id"]),
        ).fetchone()
    return dict(row)


@app.get("/controls", response_model=list[SecurityControl])
def list_controls(type: Literal["preventive", "detective", "corrective"] | None = None,
                  status: Literal["planned", "implemented", "retired"] | None = None,
                  user: dict = Depends(require_user)):
    conditions = ["organization_id = ?"]
    parameters = [user["organization_id"]]
    if type is not None:
        conditions.append("type = ?")
        parameters.append(type)
    if status is not None:
        conditions.append("status = ?")
        parameters.append(status)
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM security_controls WHERE " + " AND ".join(conditions) + " ORDER BY id",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/controls/{control_id}", response_model=SecurityControl)
def get_control(control_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM security_controls WHERE id = ? AND organization_id = ?",
            (control_id, user["organization_id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Control not found")
    return dict(row)


def require_risk_control_resources(connection, risk_id, organization_id, control_id=None):
    if connection.execute(
        "SELECT id FROM risks WHERE id = ? AND organization_id = ?", (risk_id, organization_id),
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    if control_id is not None and connection.execute(
        "SELECT id FROM security_controls WHERE id = ? AND organization_id = ?", (control_id, organization_id),
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Control not found")


@app.get("/risks/{risk_id}/controls", response_model=list[SecurityControl])
def list_risk_controls(risk_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        require_risk_control_resources(connection, risk_id, user["organization_id"])
        rows = connection.execute(
            "SELECT c.* FROM security_controls c JOIN risk_controls rc "
            "ON c.id = rc.control_id AND c.organization_id = rc.organization_id "
            "WHERE rc.risk_id = ? AND rc.organization_id = ? ORDER BY c.id",
            (risk_id, user["organization_id"]),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/risks/{risk_id}/controls", status_code=201)
def link_risk_control(risk_id: int, link: RiskControlCreate,
                      user: dict = Depends(require_roles("administrador", "analista"))):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        require_risk_control_resources(connection, risk_id, user["organization_id"], link.control_id)
        if connection.execute(
            "SELECT 1 FROM risk_controls WHERE risk_id = ? AND control_id = ? AND organization_id = ?",
            (risk_id, link.control_id, user["organization_id"]),
        ).fetchone():
            raise HTTPException(status_code=409, detail="Control already linked")
        connection.execute(
            "INSERT INTO risk_controls (risk_id, control_id, organization_id) VALUES (?, ?, ?)",
            (risk_id, link.control_id, user["organization_id"]),
        )
        record_audit(connection, user, "linked", "risk", risk_id, control_id=link.control_id)
    return {"risk_id": risk_id, "control_id": link.control_id}


@app.delete("/risks/{risk_id}/controls/{control_id}", status_code=204)
def unlink_risk_control(risk_id: int, control_id: int,
                        user: dict = Depends(require_roles("administrador", "analista"))):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        require_risk_control_resources(connection, risk_id, user["organization_id"], control_id)
        cursor = connection.execute(
            "DELETE FROM risk_controls WHERE risk_id = ? AND control_id = ? AND organization_id = ?",
            (risk_id, control_id, user["organization_id"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Link not found")
        record_audit(connection, user, "unlinked", "risk", risk_id, control_id=control_id)
    return Response(status_code=204)


@app.post("/risks/{risk_id}/assessments", response_model=RiskAssessment, status_code=201)
def create_risk_assessment(risk_id: int, assessment: RiskAssessmentCreate,
                           user: dict = Depends(require_roles("administrador", "analista"))):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        risk = connection.execute("SELECT probability, impact FROM risks WHERE id = ? AND organization_id = ?",
                                  (risk_id, user["organization_id"])).fetchone()
        if risk is None:
            raise HTTPException(status_code=404, detail="Risk not found")
        original_score = risk["probability"] * risk["impact"]
        residual_score = assessment.residual_probability * assessment.residual_impact
        cursor = connection.execute(
            "INSERT INTO risk_assessments (organization_id, risk_id, evaluator_id, evaluator_name, created_at, "
            "residual_probability, residual_impact, justification, original_probability, original_impact, original_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user["organization_id"], risk_id, user["id"], user["display_name"], datetime.now(timezone.utc).isoformat(),
             assessment.residual_probability, assessment.residual_impact, assessment.justification,
             risk["probability"], risk["impact"], original_score),
        )
        record_audit(connection, user, "assessed", "risk", risk_id, assessment_id=cursor.lastrowid,
                     original_probability=risk["probability"], original_impact=risk["impact"], original_score=original_score,
                     residual_probability=assessment.residual_probability, residual_impact=assessment.residual_impact,
                     residual_score=residual_score)
        row = connection.execute("SELECT * FROM risk_assessments WHERE id = ? AND organization_id = ?",
                                 (cursor.lastrowid, user["organization_id"])).fetchone()
    return public_assessment(row)


@app.get("/risks/{risk_id}/assessments", response_model=list[RiskAssessment])
def list_risk_assessments(risk_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection, connection:
        connection.execute("BEGIN")
        if connection.execute("SELECT id FROM risks WHERE id = ? AND organization_id = ?",
                              (risk_id, user["organization_id"])).fetchone() is None:
            raise HTTPException(status_code=404, detail="Risk not found")
        rows = connection.execute(
            "SELECT * FROM risk_assessments WHERE risk_id = ? AND organization_id = ? ORDER BY created_at DESC, id DESC",
            (risk_id, user["organization_id"]),
        ).fetchall()
    return [public_assessment(row) for row in rows]


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
        record_audit(connection, user, "created", "risk", cursor.lastrowid, asset_id=risk.asset_id)
        row = connection.execute(RISK_SELECT + "WHERE r.id = ? AND r.organization_id = ?",
                                 (cursor.lastrowid, user["organization_id"])).fetchone()
    return public_risk(row)


@app.get("/risks", response_model=list[Risk])
def list_risks(status: RiskStatus | None = None, level: RiskLevel | None = None,
               asset_id: Annotated[int | None, Query(gt=0)] = None,
               assignee_id: Annotated[int | None, Query(gt=0)] = None,
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
    if assignee_id is not None:
        conditions.append("r.assignee_id = ?")
        parameters.append(assignee_id)
    with closing(connect()) as connection:
        require_risk_asset(connection, asset_id, user["organization_id"])
        require_assignee(connection, assignee_id, user["organization_id"])
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
        record_audit(connection, user, "created", "asset", cursor.lastrowid)
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
        record_audit(connection, user, "linked", "incident", incident_id, asset_id=link.asset_id)
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
        record_audit(connection, user, "unlinked", "incident", incident_id, asset_id=asset_id)
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
        record_audit(connection, user, "created", "incident", cursor.lastrowid)
        row = connection.execute(INCIDENT_SELECT + "WHERE i.id = ?", (cursor.lastrowid,)).fetchone()
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
            INCIDENT_SELECT + "WHERE i.id = ? AND i.organization_id = ?",
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
            record_audit(connection, user, "status_changed", "incident", incident_id,
                         previous_status=row["status"], new_status=update.status)
        row = connection.execute(
            INCIDENT_SELECT + "WHERE i.id = ? AND i.organization_id = ?",
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
        record_audit(connection, user, "note_created", "incident", incident_id, note_id=cursor.lastrowid)
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
    assignee_id: Annotated[int | None, Query(gt=0)] = None,
    user: dict = Depends(require_user),
):
    conditions = ["i.organization_id = ?"]
    parameters = [user["organization_id"]]
    if status is not None:
        conditions.append("i.status = ?")
        parameters.append(status)
    if severity is not None:
        conditions.append("i.severity = ?")
        parameters.append(severity)
    if assignee_id is not None:
        conditions.append("i.assignee_id = ?")
        parameters.append(assignee_id)
    query = INCIDENT_SELECT
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY i.id"
    with closing(connect()) as connection:
        require_assignee(connection, assignee_id, user["organization_id"])
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: int, user: dict = Depends(require_user)):
    with closing(connect()) as connection:
        row = connection.execute(
            INCIDENT_SELECT + "WHERE i.id = ? AND i.organization_id = ?",
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
