from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from .identity import normalize_email, normalize_phone
from .models import JobStatus


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class LeadStore:
    """Small SQLite system of record for the local demo and its retry queue."""

    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    lead_id TEXT PRIMARY KEY,
                    lead_ref TEXT NOT NULL UNIQUE,
                    session_id TEXT,
                    email TEXT,
                    phone TEXT,
                    full_name TEXT,
                    identity_status TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    route TEXT,
                    qualification_json TEXT,
                    review_required INTEGER NOT NULL DEFAULT 0,
                    human_action TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
                CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
                CREATE INDEX IF NOT EXISTS idx_leads_session ON leads(session_id);

                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    adapter TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_lead ON jobs(lead_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                """
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def find_identity_matches(
        self, *, email: str | None, phone: str | None, session_id: str | None
    ) -> list[dict[str, Any]]:
        normalized_email = normalize_email(email)
        normalized_phone = normalize_phone(phone)
        clauses: list[str] = []
        values: list[str] = []
        if normalized_email:
            clauses.append("email = ?")
            values.append(normalized_email)
        if normalized_phone:
            clauses.append("phone = ?")
            values.append(normalized_phone)
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        if not clauses:
            return []
        query = f"SELECT * FROM leads WHERE {' OR '.join(clauses)} ORDER BY created_at"
        with self._lock:
            rows = self._connection.execute(query, values).fetchall()
        return [dict(row) for row in rows]

    def insert_lead(self, values: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        lead = {
            "lead_id": values.get("lead_id") or str(uuid4()),
            "lead_ref": values["lead_ref"],
            "session_id": values.get("session_id"),
            "email": normalize_email(values.get("email")),
            "phone": normalize_phone(values.get("phone")),
            "full_name": values.get("full_name"),
            "identity_status": values["identity_status"],
            "provenance": values["provenance"],
            "route": values.get("route"),
            "qualification_json": json.dumps(values.get("qualification"))
            if values.get("qualification") is not None
            else None,
            "review_required": int(bool(values.get("review_required", False))),
            "human_action": values.get("human_action"),
            "created_at": now,
            "updated_at": now,
        }
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO leads (
                    lead_id, lead_ref, session_id, email, phone, full_name,
                    identity_status, provenance, route, qualification_json,
                    review_required, human_action, created_at, updated_at
                ) VALUES (
                    :lead_id, :lead_ref, :session_id, :email, :phone, :full_name,
                    :identity_status, :provenance, :route, :qualification_json,
                    :review_required, :human_action, :created_at, :updated_at
                )
                """,
                lead,
            )
        return lead

    def update_lead(self, lead_id: str, **values: Any) -> dict[str, Any]:
        allowed = {
            "session_id",
            "email",
            "phone",
            "full_name",
            "identity_status",
            "provenance",
            "route",
            "qualification",
            "review_required",
            "human_action",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if "email" in updates:
            updates["email"] = normalize_email(updates["email"])
        if "phone" in updates:
            updates["phone"] = normalize_phone(updates["phone"])
        if "qualification" in updates:
            updates["qualification_json"] = json.dumps(updates.pop("qualification"))
        if "review_required" in updates:
            updates["review_required"] = int(bool(updates["review_required"]))
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._lock, self._connection:
            self._connection.execute(
                f"UPDATE leads SET {assignments} WHERE lead_id = ?",
                [*updates.values(), lead_id],
            )
        result = self.get_lead(lead_id)
        if result is None:
            raise KeyError(f"Unknown lead: {lead_id}")
        return result

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM leads WHERE lead_id = ?", (lead_id,)
            ).fetchone()
        return self._hydrate_lead(self._row_to_dict(row))

    def get_lead_by_ref(self, lead_ref: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM leads WHERE lead_ref = ?", (lead_ref,)
            ).fetchone()
        return self._hydrate_lead(self._row_to_dict(row))

    def append_event(
        self, lead_id: str, event_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        event = {
            "lead_id": lead_id,
            "event_type": event_type,
            "payload": payload,
            "created_at": utc_now(),
        }
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO events "
                "(lead_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (lead_id, event_type, json.dumps(payload), event["created_at"]),
            )
        return {"event_id": cursor.lastrowid, **event}

    def list_events(self, lead_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM events WHERE lead_id = ? ORDER BY event_id", (lead_id,)
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "lead_id": row["lead_id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def enqueue_job(
        self, *, lead_id: str, adapter: str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        now = utc_now()
        job = {
            "job_id": str(uuid4()),
            "lead_id": lead_id,
            "adapter": adapter,
            "action": action,
            "status": JobStatus.PENDING.value,
            "attempts": 0,
            "payload": payload,
            "result": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO jobs (
                    job_id, lead_id, adapter, action, status, attempts,
                    payload_json, result_json, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["job_id"],
                    lead_id,
                    adapter,
                    action,
                    job["status"],
                    job["attempts"],
                    json.dumps(payload),
                    None,
                    None,
                    now,
                    now,
                ),
            )
        return job

    def list_jobs(self, lead_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        values: tuple[str, ...] = ()
        if lead_id:
            query += " WHERE lead_id = ?"
            values = (lead_id,)
        query += " ORDER BY created_at, job_id"
        with self._lock:
            rows = self._connection.execute(query, values).fetchall()
        return [self._hydrate_job(dict(row)) for row in rows]

    def claim_job(self, job_id: str) -> dict[str, Any]:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE jobs SET status = ?, attempts = attempts + 1, "
                "updated_at = ? WHERE job_id = ?",
                (JobStatus.RUNNING.value, utc_now(), job_id),
            )
        job = next((job for job in self.list_jobs() if job["job_id"] == job_id), None)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        return job

    def finish_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE jobs SET status = ?, result_json = ?, last_error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status.value,
                    json.dumps(result) if result is not None else None,
                    error,
                    utc_now(),
                    job_id,
                ),
            )
        job = next((job for job in self.list_jobs() if job["job_id"] == job_id), None)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        return job

    @staticmethod
    def _hydrate_lead(lead: dict[str, Any] | None) -> dict[str, Any] | None:
        if lead is None:
            return None
        qualification = lead.pop("qualification_json", None)
        lead["qualification"] = json.loads(qualification) if qualification else None
        lead["review_required"] = bool(lead["review_required"])
        return lead

    @staticmethod
    def _hydrate_job(job: dict[str, Any]) -> dict[str, Any]:
        payload = job.pop("payload_json", None)
        result = job.pop("result_json", None)
        job["payload"] = json.loads(payload) if payload else {}
        job["result"] = json.loads(result) if result else None
        return job
