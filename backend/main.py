import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


DATABASE_PATH = Path(__file__).resolve().parent / "securityops.db"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    with closing(connect()) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                description TEXT NOT NULL CHECK (length(trim(description)) > 0),
                severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
                status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'resolved')),
                created_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS incident_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL REFERENCES incidents(id),
                previous_status TEXT NOT NULL CHECK (previous_status IN ('open', 'investigating', 'resolved')),
                new_status TEXT NOT NULL CHECK (new_status IN ('open', 'investigating', 'resolved')),
                changed_at TEXT NOT NULL,
                CHECK (previous_status <> new_status)
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_incident_history "
            "ON incident_status_history (incident_id, id)"
        )
    yield


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, pattern=r"\S")
    description: str = Field(min_length=1, pattern=r"\S")
    severity: Literal["low", "medium", "high", "critical"]
    status: Literal["open", "investigating", "resolved"] = "open"


class Incident(IncidentCreate):
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


app = FastAPI(title="SecurityOps", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/incidents", response_model=Incident, status_code=201)
def create_incident(incident: IncidentCreate):
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect()) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO incidents (title, description, severity, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (incident.title, incident.description, incident.severity, incident.status, created_at),
        )
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


@app.patch("/incidents/{incident_id}/status", response_model=Incident)
def update_incident_status(incident_id: int, update: IncidentStatusUpdate):
    with closing(connect()) as connection, connection:
        # Lock writers before reading so concurrent changes record the correct previous state.
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        if row["status"] != update.status:
            connection.execute(
                "UPDATE incidents SET status = ? WHERE id = ?",
                (update.status, incident_id),
            )
            connection.execute(
                "INSERT INTO incident_status_history "
                "(incident_id, previous_status, new_status, changed_at) VALUES (?, ?, ?, ?)",
                (incident_id, row["status"], update.status, datetime.now(timezone.utc).isoformat()),
            )
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
    return dict(row)


@app.get("/incidents/{incident_id}/history", response_model=list[IncidentStatusHistory])
def get_incident_history(incident_id: int):
    with closing(connect()) as connection:
        incident = connection.execute(
            "SELECT id FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        rows = connection.execute(
            "SELECT * FROM incident_status_history WHERE incident_id = ? ORDER BY id",
            (incident_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/incidents", response_model=list[Incident])
def list_incidents(
    status: Literal["open", "investigating", "resolved"] | None = None,
    severity: Literal["low", "medium", "high", "critical"] | None = None,
):
    conditions = []
    parameters = []
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
def get_incident(incident_id: int):
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)
