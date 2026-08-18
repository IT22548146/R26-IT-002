"""Persistent daily monitoring records for Component 3 early-warning data."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from components.component3_tracking import (
    TrackingConflictError,
    TrackingNotFoundError,
    utc_now,
)


MONITORING_LABEL_STATUSES = (
    "Waiting",
    "Ready",
    "Not Eligible",
    "Censored",
    "Incomplete",
)
MONITORING_RISK_STATUSES = ("No Risk", "Risk")
MIN_ROWS_PER_CLASS = 20
MIN_ORDERS_PER_CLASS = 3


def _normalize_choice(value: Any, choices: tuple[str, ...], field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be one of {list(choices)}")
    lookup = {choice.lower(): choice for choice in choices}
    normalized = lookup.get(value.strip().lower())
    if normalized is None:
        raise ValueError(f"{field} must be one of {list(choices)}")
    return normalized


def normalize_monitoring_label_status(value: Any) -> str:
    return _normalize_choice(value, MONITORING_LABEL_STATUSES, "label_status")


def normalize_monitoring_risk_status(value: Any) -> str:
    return _normalize_choice(value, MONITORING_RISK_STATUSES, "risk_status")


class Component3MonitoringStore:
    """SQLite store that derives future labels from consecutive daily records."""

    def __init__(self, database_path: str):
        if not database_path:
            raise ValueError("A monitoring database path is required")
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
                CREATE TABLE IF NOT EXISTS component3_daily_monitoring (
                    record_id TEXT PRIMARY KEY,
                    bulk_order_id TEXT NOT NULL,
                    style_id TEXT NOT NULL,
                    production_date TEXT NOT NULL,
                    working_day_no INTEGER NOT NULL,
                    risk_status TEXT NOT NULL,
                    risk_type TEXT NOT NULL,
                    severity TEXT,
                    is_emergency INTEGER NOT NULL,
                    prediction_input_json TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    recorded_by TEXT NOT NULL,
                    label_status TEXT NOT NULL DEFAULT 'Waiting',
                    emergency_within_1_day INTEGER,
                    emergency_within_3_days INTEGER,
                    first_emergency_type_within_3_days TEXT,
                    first_emergency_lead_days INTEGER,
                    worker_shortage_within_3_days INTEGER,
                    machine_breakdown_within_3_days INTEGER,
                    quality_limit_within_3_days INTEGER,
                    output_schedule_risk_within_3_days INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_c3_monitoring_order_date
                    ON component3_daily_monitoring (
                        bulk_order_id, production_date
                    );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_c3_monitoring_order_day
                    ON component3_daily_monitoring (
                        bulk_order_id, working_day_no
                    );
                CREATE INDEX IF NOT EXISTS idx_c3_monitoring_date
                    ON component3_daily_monitoring (production_date DESC);
                CREATE INDEX IF NOT EXISTS idx_c3_monitoring_label_status
                    ON component3_daily_monitoring (label_status);
                CREATE INDEX IF NOT EXISTS idx_c3_monitoring_risk_status
                    ON component3_daily_monitoring (risk_status);
                """
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _is_emergency(
        prediction_input: dict[str, Any],
        risk_type: str,
    ) -> bool:
        return bool(
            risk_type != "No Issue"
            or int(prediction_input["worker_shortage_count"]) > 0
            or int(prediction_input["machine_breakdown_count"]) > 0
            or int(prediction_input["daily_damage_qty"])
            > int(prediction_input["max_daily_damage_qty"])
        )

    @staticmethod
    def _physical_trigger(prediction_input: dict[str, Any]) -> bool:
        return bool(
            int(prediction_input["worker_shortage_count"]) > 0
            or int(prediction_input["machine_breakdown_count"]) > 0
            or int(prediction_input["daily_damage_qty"])
            > int(prediction_input["max_daily_damage_qty"])
        )

    @staticmethod
    def _first_emergency_type(
        row: sqlite3.Row,
        prediction_input: dict[str, Any],
    ) -> str:
        if row["risk_type"] != "No Issue":
            return str(row["risk_type"])
        if int(prediction_input["machine_breakdown_count"]) > 0:
            return "Machine Breakdown Issue"
        if int(prediction_input["worker_shortage_count"]) > 0:
            return "Worker Issue"
        return "Quality Issue"

    def _validate_order_sequence(
        self,
        connection: sqlite3.Connection,
        prediction_input: dict[str, Any],
    ) -> None:
        order_id = str(prediction_input["bulk_order_id"])
        new_day = int(prediction_input["working_day_no"])
        new_date = str(prediction_input["production_date"])
        new_cumulative = int(prediction_input["cumulative_completed_qty"])
        rows = connection.execute(
            """
            SELECT working_day_no, production_date, prediction_input_json
            FROM component3_daily_monitoring
            WHERE bulk_order_id = ?
            ORDER BY working_day_no
            """,
            (order_id,),
        ).fetchall()

        consistency_fields = (
            "style_id",
            "full_order_qty",
            "total_working_days",
            "buyer_required_date",
        )
        for row in rows:
            existing_input = json.loads(row["prediction_input_json"])
            for field in consistency_fields:
                if str(existing_input[field]) != str(prediction_input[field]):
                    raise TrackingConflictError(
                        f"{field} conflicts with existing records for {order_id}"
                    )

            existing_day = int(row["working_day_no"])
            existing_date = str(row["production_date"])
            existing_cumulative = int(
                existing_input["cumulative_completed_qty"]
            )
            if existing_day < new_day:
                if existing_date >= new_date:
                    raise TrackingConflictError(
                        "production_date must increase with working_day_no"
                    )
                if existing_cumulative > new_cumulative:
                    raise TrackingConflictError(
                        "cumulative_completed_qty cannot decrease on a later day"
                    )
            elif existing_day > new_day:
                if existing_date <= new_date:
                    raise TrackingConflictError(
                        "production_date must increase with working_day_no"
                    )
                if existing_cumulative < new_cumulative:
                    raise TrackingConflictError(
                        "cumulative_completed_qty cannot exceed a later saved day"
                    )

    def create_record(
        self,
        prediction_input: dict[str, Any],
        analysis: dict[str, Any],
        *,
        recorded_by: str,
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        now = utc_now()
        risk = analysis.get("risk_detection") or {}
        risk_type = str(risk.get("risk_type", "Unknown"))
        risk_status = "Risk" if self._is_emergency(
            prediction_input, risk_type
        ) else "No Risk"
        is_emergency = int(risk_status == "Risk")

        with self._connection() as connection:
            self._validate_order_sequence(connection, prediction_input)
            try:
                connection.execute(
                    """
                    INSERT INTO component3_daily_monitoring (
                        record_id, bulk_order_id, style_id, production_date,
                        working_day_no, risk_status, risk_type, severity,
                        is_emergency, prediction_input_json, analysis_json,
                        recorded_by, label_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        str(prediction_input["bulk_order_id"]),
                        str(prediction_input["style_id"]),
                        str(prediction_input["production_date"]),
                        int(prediction_input["working_day_no"]),
                        risk_status,
                        risk_type,
                        risk.get("severity"),
                        is_emergency,
                        self._json(prediction_input),
                        self._json(analysis),
                        recorded_by,
                        "Not Eligible" if is_emergency else "Waiting",
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise TrackingConflictError(
                    "A daily monitoring record already exists for this bulk "
                    "order/date or working day"
                ) from exc

            self._refresh_labels(
                connection,
                str(prediction_input["bulk_order_id"]),
                updated_at=now,
            )

        return self.get_record(record_id)

    def _refresh_labels(
        self,
        connection: sqlite3.Connection,
        bulk_order_id: str,
        *,
        updated_at: str,
    ) -> None:
        rows = connection.execute(
            """
            SELECT * FROM component3_daily_monitoring
            WHERE bulk_order_id = ?
            ORDER BY working_day_no
            """,
            (bulk_order_id,),
        ).fetchall()
        by_day = {int(row["working_day_no"]): row for row in rows}
        max_day = max(by_day, default=0)

        for row in rows:
            day = int(row["working_day_no"])
            current_input = json.loads(row["prediction_input_json"])
            status = "Waiting"
            labels: tuple[Any, ...] = (None,) * 8

            if bool(row["is_emergency"]):
                status = "Not Eligible"
            else:
                future = [by_day.get(day + offset) for offset in (1, 2, 3)]
                if all(future):
                    future_rows = [item for item in future if item is not None]
                    future_inputs = [
                        json.loads(item["prediction_input_json"])
                        for item in future_rows
                    ]
                    future_emergencies = [
                        bool(item["is_emergency"]) for item in future_rows
                    ]
                    first_emergency_type = "No Emergency"
                    first_emergency_lead = None
                    for lead, (future_row, future_input, emergency) in enumerate(
                        zip(future_rows, future_inputs, future_emergencies),
                        start=1,
                    ):
                        if emergency:
                            first_emergency_type = self._first_emergency_type(
                                future_row, future_input
                            )
                            first_emergency_lead = lead
                            break

                    worker = any(
                        int(item["worker_shortage_count"]) > 0
                        for item in future_inputs
                    )
                    machine = any(
                        int(item["machine_breakdown_count"]) > 0
                        for item in future_inputs
                    )
                    quality = any(
                        int(item["daily_damage_qty"])
                        > int(item["max_daily_damage_qty"])
                        for item in future_inputs
                    )
                    schedule = any(
                        future_row["risk_type"] != "No Issue"
                        and not self._physical_trigger(future_input)
                        for future_row, future_input in zip(
                            future_rows, future_inputs
                        )
                    )
                    status = "Ready"
                    labels = (
                        int(future_emergencies[0]),
                        int(any(future_emergencies)),
                        first_emergency_type,
                        first_emergency_lead,
                        int(worker),
                        int(machine),
                        int(quality),
                        int(schedule),
                    )
                else:
                    later_rows = [
                        later for later in rows if int(later["working_day_no"]) > day
                    ]
                    completed = int(current_input["cumulative_completed_qty"]) >= int(
                        current_input["full_order_qty"]
                    ) or any(
                        int(json.loads(later["prediction_input_json"])[
                            "cumulative_completed_qty"
                        ])
                        >= int(json.loads(later["prediction_input_json"])[
                            "full_order_qty"
                        ])
                        for later in later_rows
                    )
                    if completed:
                        status = "Censored"
                    elif max_day >= day + 3:
                        status = "Incomplete"

            connection.execute(
                """
                UPDATE component3_daily_monitoring
                SET label_status = ?, emergency_within_1_day = ?,
                    emergency_within_3_days = ?,
                    first_emergency_type_within_3_days = ?,
                    first_emergency_lead_days = ?,
                    worker_shortage_within_3_days = ?,
                    machine_breakdown_within_3_days = ?,
                    quality_limit_within_3_days = ?,
                    output_schedule_risk_within_3_days = ?, updated_at = ?
                WHERE record_id = ?
                """,
                (status, *labels, updated_at, row["record_id"]),
            )

    def list_records(
        self,
        *,
        bulk_order_id: str | None = None,
        risk_status: str | None = None,
        label_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if bulk_order_id:
            conditions.append("bulk_order_id = ?")
            parameters.append(bulk_order_id)
        if risk_status:
            conditions.append("risk_status = ?")
            parameters.append(risk_status)
        if label_status:
            conditions.append("label_status = ?")
            parameters.append(label_status)
        clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._connection() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM component3_daily_monitoring {clause}",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT * FROM component3_daily_monitoring
                {clause}
                ORDER BY production_date DESC, working_day_no DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            ).fetchall()
        return {
            "items": [self._summary(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_record(self, record_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM component3_daily_monitoring WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise TrackingNotFoundError(
                f"Daily monitoring record {record_id} was not found"
            )
        record = self._summary(row)
        record.update(
            {
                "prediction_input": json.loads(row["prediction_input_json"]),
                "analysis": json.loads(row["analysis_json"]),
            }
        )
        return record

    def readiness_summary(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM component3_daily_monitoring"
            ).fetchall()

        ready = [row for row in rows if row["label_status"] == "Ready"]
        positives = [row for row in ready if row["emergency_within_3_days"] == 1]
        negatives = [row for row in ready if row["emergency_within_3_days"] == 0]
        positive_orders = len({row["bulk_order_id"] for row in positives})
        negative_orders = len({row["bulk_order_id"] for row in negatives})
        rows_sufficient = min(len(positives), len(negatives)) >= MIN_ROWS_PER_CLASS
        orders_sufficient = (
            min(positive_orders, negative_orders) >= MIN_ORDERS_PER_CLASS
        )
        label_counts = {
            status: sum(row["label_status"] == status for row in rows)
            for status in MONITORING_LABEL_STATUSES
        }
        return {
            "total_records": len(rows),
            "stable_records": sum(not bool(row["is_emergency"]) for row in rows),
            "emergency_records": sum(bool(row["is_emergency"]) for row in rows),
            "label_status_counts": label_counts,
            "three_day_target": {
                "ready_rows": len(ready),
                "positive_rows": len(positives),
                "negative_rows": len(negatives),
                "positive_orders": positive_orders,
                "negative_orders": negative_orders,
                "minimum_rows_per_class_required": MIN_ROWS_PER_CLASS,
                "minimum_orders_per_class_required": MIN_ORDERS_PER_CLASS,
                "row_balance_sufficient": rows_sufficient,
                "group_coverage_sufficient": orders_sufficient,
                "general_early_warning_training_ready": (
                    rows_sufficient and orders_sufficient
                ),
            },
        }

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict[str, Any]:
        prediction_input = json.loads(row["prediction_input_json"])
        return {
            "record_id": row["record_id"],
            "bulk_order_id": row["bulk_order_id"],
            "style_id": row["style_id"],
            "production_date": row["production_date"],
            "working_day_no": row["working_day_no"],
            "risk_status": row["risk_status"],
            "risk_type": row["risk_type"],
            "severity": row["severity"],
            "is_emergency": bool(row["is_emergency"]),
            "plant_daily_output": prediction_input["plant_daily_output"],
            "daily_commitment": prediction_input["daily_commitment"],
            "worker_shortage_count": prediction_input["worker_shortage_count"],
            "machine_breakdown_count": prediction_input[
                "machine_breakdown_count"
            ],
            "daily_damage_qty": prediction_input["daily_damage_qty"],
            "max_daily_damage_qty": prediction_input["max_daily_damage_qty"],
            "cumulative_completed_qty": prediction_input[
                "cumulative_completed_qty"
            ],
            "label_status": row["label_status"],
            "emergency_within_1_day": row["emergency_within_1_day"],
            "emergency_within_3_days": row["emergency_within_3_days"],
            "first_emergency_type_within_3_days": row[
                "first_emergency_type_within_3_days"
            ],
            "first_emergency_lead_days": row["first_emergency_lead_days"],
            "worker_shortage_within_3_days": row[
                "worker_shortage_within_3_days"
            ],
            "machine_breakdown_within_3_days": row[
                "machine_breakdown_within_3_days"
            ],
            "quality_limit_within_3_days": row[
                "quality_limit_within_3_days"
            ],
            "output_schedule_risk_within_3_days": row[
                "output_schedule_risk_within_3_days"
            ],
            "recorded_by": row["recorded_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
