"""Persistent incident and recovery-outcome tracking for Component 3."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


INCIDENT_STATUSES = ("Pending", "Approved", "In Progress", "Completed")
STATUS_TRANSITIONS = {
    "Pending": {"Approved"},
    "Approved": {"In Progress"},
    "In Progress": {"Completed"},
    "Completed": set(),
}


class TrackingNotFoundError(LookupError):
    """Raised when a requested incident does not exist."""


class TrackingConflictError(RuntimeError):
    """Raised when a requested workflow operation conflicts with current state."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def normalize_status(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"status must be one of {list(INCIDENT_STATUSES)}")
    lookup = {status.lower(): status for status in INCIDENT_STATUSES}
    normalized = lookup.get(value.strip().lower())
    if normalized is None:
        raise ValueError(f"status must be one of {list(INCIDENT_STATUSES)}")
    return normalized


class Component3TrackingStore:
    """Small SQLite repository with an auditable recovery workflow."""

    def __init__(self, database_path: str):
        if not database_path:
            raise ValueError("A tracking database path is required")
        self.database_path = os.path.abspath(database_path)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS component3_incidents (
                    incident_id TEXT PRIMARY KEY,
                    bulk_order_id TEXT NOT NULL,
                    style_id TEXT NOT NULL,
                    buyer_name TEXT NOT NULL,
                    allocated_bulk_plant TEXT NOT NULL,
                    production_date TEXT NOT NULL,
                    risk_type TEXT NOT NULL,
                    order_risk_level TEXT NOT NULL,
                    severity TEXT,
                    workflow_status TEXT NOT NULL,
                    recommended_option_id TEXT,
                    selected_option_id TEXT,
                    selected_option_json TEXT,
                    approved_by TEXT,
                    approval_notes TEXT,
                    prediction_input_json TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_component3_incidents_order
                    ON component3_incidents (bulk_order_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_component3_incidents_status
                    ON component3_incidents (workflow_status, created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_component3_incidents_daily_order
                    ON component3_incidents (bulk_order_id, production_date);

                CREATE TABLE IF NOT EXISTS component3_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    outcome_date TEXT NOT NULL,
                    actual_daily_output INTEGER NOT NULL,
                    target_daily_output REAL,
                    output_variance REAL,
                    effectiveness_pct REAL,
                    recovery_gap_closed_pct REAL,
                    cumulative_completed_qty INTEGER,
                    actual_completion_date TEXT,
                    notes TEXT,
                    recorded_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (incident_id)
                        REFERENCES component3_incidents (incident_id)
                        ON DELETE CASCADE,
                    UNIQUE (incident_id, outcome_date)
                );

                CREATE INDEX IF NOT EXISTS idx_component3_outcomes_incident
                    ON component3_outcomes (incident_id, outcome_date);

                CREATE TABLE IF NOT EXISTS component3_incident_events (
                    event_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (incident_id)
                        REFERENCES component3_incidents (incident_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_component3_events_incident
                    ON component3_incident_events (incident_id, created_at);
                """
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _option_map(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
        recovery_plan = analysis.get("recovery_plan") or {}
        options = []
        recommended = recovery_plan.get("recommended_option")
        if isinstance(recommended, dict):
            options.append(recommended)
        alternatives = recovery_plan.get("alternatives") or []
        options.extend(option for option in alternatives if isinstance(option, dict))
        return {
            option["option_id"]: option
            for option in options
            if isinstance(option.get("option_id"), str)
        }

    def _add_event(
        self,
        connection: sqlite3.Connection,
        *,
        incident_id: str,
        event_type: str,
        actor: str,
        details: dict[str, Any],
        created_at: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO component3_incident_events (
                event_id, incident_id, event_type, actor, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                incident_id,
                event_type,
                actor,
                self._json(details),
                created_at or utc_now(),
            ),
        )

    def create_incident(
        self,
        prediction_input: dict[str, Any],
        analysis: dict[str, Any],
        *,
        created_by: str,
    ) -> dict[str, Any]:
        incident_id = str(uuid.uuid4())
        now = utc_now()
        recovery_plan = analysis.get("recovery_plan") or {}
        recommended = recovery_plan.get("recommended_option") or {}
        recommended_option_id = recommended.get("option_id")
        risk_detection = analysis.get("risk_detection") or {}

        with self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO component3_incidents (
                        incident_id, bulk_order_id, style_id, buyer_name,
                        allocated_bulk_plant, production_date, risk_type,
                        order_risk_level, severity, workflow_status,
                        recommended_option_id, prediction_input_json,
                        analysis_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        incident_id,
                        str(analysis["bulk_order_id"]),
                        str(analysis["style_id"]),
                        str(analysis["buyer_name"]),
                        str(analysis["allocated_bulk_plant"]),
                        str(analysis["production_date"]),
                        str(risk_detection.get("risk_type", "Unknown")),
                        str(risk_detection.get("order_risk_level", "Unknown")),
                        risk_detection.get("severity"),
                        "Pending",
                        recommended_option_id,
                        self._json(prediction_input),
                        self._json(analysis),
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise TrackingConflictError(
                    "An incident already exists for this bulk order and "
                    "production date"
                ) from exc
            self._add_event(
                connection,
                incident_id=incident_id,
                event_type="Incident Created",
                actor=created_by,
                details={
                    "recommended_option_id": recommended_option_id,
                    "risk_type": risk_detection.get("risk_type"),
                    "order_risk_level": risk_detection.get("order_risk_level"),
                },
                created_at=now,
            )

        return self.get_incident(incident_id)

    def list_incidents(
        self,
        *,
        bulk_order_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where = []
        params: list[Any] = []
        if bulk_order_id:
            where.append("bulk_order_id = ?")
            params.append(bulk_order_id)
        if status:
            where.append("workflow_status = ?")
            params.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        with self._connection() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM component3_incidents {clause}",
                params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM component3_incidents
                {clause}
                ORDER BY created_at DESC, incident_id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return {
            "items": [self._incident_summary(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM component3_incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise TrackingNotFoundError(f"Incident {incident_id} was not found")

            outcomes = connection.execute(
                """
                SELECT * FROM component3_outcomes
                WHERE incident_id = ?
                ORDER BY outcome_date, created_at
                """,
                (incident_id,),
            ).fetchall()
            events = connection.execute(
                """
                SELECT * FROM component3_incident_events
                WHERE incident_id = ?
                ORDER BY created_at, event_id
                """,
                (incident_id,),
            ).fetchall()

        incident = self._incident_summary(row)
        incident.update(
            {
                "prediction_input": json.loads(row["prediction_input_json"]),
                "analysis": json.loads(row["analysis_json"]),
                "selected_option": (
                    json.loads(row["selected_option_json"])
                    if row["selected_option_json"]
                    else None
                ),
                "outcomes": [self._outcome(row) for row in outcomes],
                "timeline": [self._event(row) for row in events],
            }
        )
        return incident

    def approve_decision(
        self,
        incident_id: str,
        *,
        selected_option_id: str,
        approved_by: str,
        notes: str | None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM component3_incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise TrackingNotFoundError(f"Incident {incident_id} was not found")
            if row["workflow_status"] != "Pending":
                raise TrackingConflictError(
                    "A recovery decision can only be approved while the incident is Pending"
                )

            analysis = json.loads(row["analysis_json"])
            options = self._option_map(analysis)
            selected_option = options.get(selected_option_id)
            if selected_option is None:
                raise ValueError(
                    f"selected_option_id must be one of {sorted(options)}"
                )

            connection.execute(
                """
                UPDATE component3_incidents
                SET selected_option_id = ?, selected_option_json = ?,
                    approved_by = ?, approval_notes = ?,
                    workflow_status = 'Approved', updated_at = ?
                WHERE incident_id = ?
                """,
                (
                    selected_option_id,
                    self._json(selected_option),
                    approved_by,
                    notes,
                    now,
                    incident_id,
                ),
            )
            self._add_event(
                connection,
                incident_id=incident_id,
                event_type="Recovery Decision Approved",
                actor=approved_by,
                details={
                    "selected_option_id": selected_option_id,
                    "notes": notes,
                    "status": "Approved",
                },
                created_at=now,
            )

        return self.get_incident(incident_id)

    def update_status(
        self,
        incident_id: str,
        *,
        new_status: str,
        updated_by: str,
        notes: str | None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT workflow_status FROM component3_incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise TrackingNotFoundError(f"Incident {incident_id} was not found")

            current_status = row["workflow_status"]
            if current_status == "Pending":
                raise TrackingConflictError(
                    "Approve a recovery option through the decision endpoint before "
                    "changing this incident's status"
                )
            if new_status not in STATUS_TRANSITIONS[current_status]:
                allowed = sorted(STATUS_TRANSITIONS[current_status])
                raise TrackingConflictError(
                    f"Cannot change status from {current_status} to {new_status}; "
                    f"allowed next statuses: {allowed}"
                )
            if new_status == "Completed":
                outcome_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM component3_outcomes
                    WHERE incident_id = ?
                    """,
                    (incident_id,),
                ).fetchone()[0]
                if outcome_count == 0:
                    raise TrackingConflictError(
                        "Record at least one actual production outcome before "
                        "completing the incident"
                    )

            connection.execute(
                """
                UPDATE component3_incidents
                SET workflow_status = ?, updated_at = ?
                WHERE incident_id = ?
                """,
                (new_status, now, incident_id),
            )
            self._add_event(
                connection,
                incident_id=incident_id,
                event_type="Status Changed",
                actor=updated_by,
                details={
                    "from_status": current_status,
                    "to_status": new_status,
                    "notes": notes,
                },
                created_at=now,
            )

        return self.get_incident(incident_id)

    def record_outcome(
        self,
        incident_id: str,
        *,
        outcome_date: str,
        actual_daily_output: int,
        cumulative_completed_qty: int | None,
        actual_completion_date: str | None,
        notes: str | None,
        recorded_by: str,
    ) -> dict[str, Any]:
        now = utc_now()
        outcome_id = str(uuid.uuid4())
        with self._connection() as connection:
            incident = connection.execute(
                "SELECT * FROM component3_incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if incident is None:
                raise TrackingNotFoundError(f"Incident {incident_id} was not found")
            if incident["workflow_status"] not in {"In Progress", "Completed"}:
                raise TrackingConflictError(
                    "Outcomes can only be recorded for In Progress or Completed incidents"
                )
            if outcome_date <= incident["production_date"]:
                raise ValueError(
                    "outcome_date must be after the incident production_date"
                )

            analysis = json.loads(incident["analysis_json"])
            full_order_qty = analysis.get("order_summary", {}).get("full_order_qty")
            if (
                cumulative_completed_qty is not None
                and full_order_qty is not None
                and cumulative_completed_qty > int(full_order_qty)
            ):
                raise ValueError(
                    "cumulative_completed_qty cannot exceed the incident order quantity"
                )
            recovery_plan = analysis.get("recovery_plan") or {}
            selected_option = (
                json.loads(incident["selected_option_json"])
                if incident["selected_option_json"]
                else recovery_plan.get("recommended_option") or {}
            )
            target = selected_option.get("daily_capacity")
            if target is None:
                target = recovery_plan.get("required_daily_rate")
            target = float(target) if target is not None else None

            output_variance = (
                round(actual_daily_output - target, 2) if target is not None else None
            )
            effectiveness = (
                round(actual_daily_output / target * 100, 2)
                if target is not None and target > 0
                else None
            )
            current_capacity = recovery_plan.get("current_daily_capacity")
            required_rate = recovery_plan.get("required_daily_rate")
            gap_closed = None
            if current_capacity is not None and required_rate is not None:
                original_gap = float(required_rate) - float(current_capacity)
                if original_gap > 0:
                    gap_closed = round(
                        (actual_daily_output - float(current_capacity))
                        / original_gap
                        * 100,
                        2,
                    )

            try:
                connection.execute(
                    """
                    INSERT INTO component3_outcomes (
                        outcome_id, incident_id, outcome_date,
                        actual_daily_output, target_daily_output,
                        output_variance, effectiveness_pct,
                        recovery_gap_closed_pct, cumulative_completed_qty,
                        actual_completion_date, notes, recorded_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outcome_id,
                        incident_id,
                        outcome_date,
                        actual_daily_output,
                        target,
                        output_variance,
                        effectiveness,
                        gap_closed,
                        cumulative_completed_qty,
                        actual_completion_date,
                        notes,
                        recorded_by,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise TrackingConflictError(
                    f"An outcome already exists for {outcome_date}"
                ) from exc

            self._add_event(
                connection,
                incident_id=incident_id,
                event_type="Outcome Recorded",
                actor=recorded_by,
                details={
                    "outcome_id": outcome_id,
                    "outcome_date": outcome_date,
                    "actual_daily_output": actual_daily_output,
                    "target_daily_output": target,
                    "effectiveness_pct": effectiveness,
                    "recovery_gap_closed_pct": gap_closed,
                },
                created_at=now,
            )
            outcome = connection.execute(
                "SELECT * FROM component3_outcomes WHERE outcome_id = ?",
                (outcome_id,),
            ).fetchone()

        return self._outcome(outcome)

    @staticmethod
    def _incident_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "incident_id": row["incident_id"],
            "bulk_order_id": row["bulk_order_id"],
            "style_id": row["style_id"],
            "buyer_name": row["buyer_name"],
            "allocated_bulk_plant": row["allocated_bulk_plant"],
            "production_date": row["production_date"],
            "risk_type": row["risk_type"],
            "order_risk_level": row["order_risk_level"],
            "severity": row["severity"],
            "workflow_status": row["workflow_status"],
            "recommended_option_id": row["recommended_option_id"],
            "selected_option_id": row["selected_option_id"],
            "approved_by": row["approved_by"],
            "approval_notes": row["approval_notes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _outcome(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "outcome_id": row["outcome_id"],
            "outcome_date": row["outcome_date"],
            "actual_daily_output": row["actual_daily_output"],
            "target_daily_output": row["target_daily_output"],
            "output_variance": row["output_variance"],
            "effectiveness_pct": row["effectiveness_pct"],
            "recovery_gap_closed_pct": row["recovery_gap_closed_pct"],
            "cumulative_completed_qty": row["cumulative_completed_qty"],
            "actual_completion_date": row["actual_completion_date"],
            "notes": row["notes"],
            "recorded_by": row["recorded_by"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _event(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "actor": row["actor"],
            "details": json.loads(row["details_json"]),
            "created_at": row["created_at"],
        }
