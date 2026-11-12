"""Read-only reconciliation between C3 tracking and integrated daily logs."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class Component3ReconciliationError(RuntimeError):
    """Raised when the databases cannot be safely audited."""


COMPARISON_FIELDS = (
    "working_day_no",
    "plant_daily_output",
    "daily_damage_qty",
    "max_daily_damage_qty",
    "machine_breakdown_count",
    "worker_shortage_count",
    "cumulative_completed_qty",
)


def _read_only_connection(path: str | Path) -> sqlite3.Connection:
    database_path = Path(path).expanduser().resolve()
    if not database_path.is_file():
        raise Component3ReconciliationError(f"Database does not exist: {database_path}")
    try:
        connection = sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro",
            uri=True,
            timeout=10,
        )
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as error:
        raise Component3ReconciliationError(
            f"Could not open database for reconciliation: {database_path}"
        ) from error


def _key(order_id: object, plant_id: object, production_date: object) -> tuple[str, str, str]:
    return (str(order_id), str(plant_id), str(production_date)[:10])


def _key_payload(key: tuple[str, str, str]) -> dict[str, str]:
    return {
        "bulk_order_id": key[0],
        "plant_id": key[1],
        "production_date": key[2],
    }


def _tracking_rows(database_path: str | Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    try:
        with closing(_read_only_connection(database_path)) as connection:
            rows = connection.execute(
                """SELECT bulk_order_id, plant_key, production_date,
                          prediction_input_json, analysis_json, data_origin
                   FROM component3_daily_monitoring
                   WHERE data_origin = 'live_monitoring'"""
            ).fetchall()
    except sqlite3.Error as error:
        raise Component3ReconciliationError(
            "Component 3 tracking database has no readable monitoring table"
        ) from error

    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        try:
            prediction_input = json.loads(row["prediction_input_json"])
            analysis = json.loads(row["analysis_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise Component3ReconciliationError(
                "Component 3 tracking database contains invalid JSON"
            ) from error
        integrated_plant_id = str(prediction_input.get("integrated_plant_id") or "").strip()
        if not integrated_plant_id:
            continue
        key = _key(row["bulk_order_id"], integrated_plant_id, row["production_date"])
        result[key] = {
            "values": {field: prediction_input.get(field) for field in COMPARISON_FIELDS},
            "model_version": analysis.get("model_version"),
            "prediction_contract_version": analysis.get("prediction_contract_version"),
            "risk_type": (analysis.get("risk_detection") or {}).get("risk_type"),
        }
    return result


def _operational_rows(
    database_path: str | Path,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    try:
        with closing(_read_only_connection(database_path)) as connection:
            rows = connection.execute(
                """SELECT bulk_order_id, plant_id, log_date, working_day_no,
                          plant_daily_output, daily_damage_qty,
                          max_daily_damage_qty, machine_breakdown_count,
                          worker_shortage_count, cumulative_completed_qty,
                          c3_result_json
                   FROM daily_logs
                   WHERE c3_result_json IS NOT NULL"""
            ).fetchall()
    except sqlite3.Error as error:
        raise Component3ReconciliationError(
            "Operational database has no readable daily_logs table"
        ) from error

    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        try:
            analysis = json.loads(row["c3_result_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise Component3ReconciliationError(
                "Operational daily_logs contains invalid C3 JSON"
            ) from error
        key = _key(row["bulk_order_id"], row["plant_id"], row["log_date"])
        result[key] = {
            "values": {field: row[field] for field in COMPARISON_FIELDS},
            "model_version": analysis.get("model_version"),
            "prediction_contract_version": analysis.get("prediction_contract_version"),
            "risk_type": (analysis.get("risk_detection") or {}).get("risk_type"),
        }
    return result


def audit_component3_persistence(
    tracking_database: str | Path,
    operational_database: str | Path,
) -> dict[str, Any]:
    """Compare only integrated live C3 records; never mutate either database."""
    tracking = _tracking_rows(tracking_database)
    operational = _operational_rows(operational_database)
    tracking_keys = set(tracking)
    operational_keys = set(operational)
    shared_keys = tracking_keys & operational_keys

    mismatches: list[dict[str, Any]] = []
    metadata_fields = (
        "model_version",
        "prediction_contract_version",
        "risk_type",
    )
    for key in sorted(shared_keys):
        differing_fields: dict[str, dict[str, Any]] = {}
        for field in COMPARISON_FIELDS:
            tracking_value = tracking[key]["values"].get(field)
            operational_value = operational[key]["values"].get(field)
            if tracking_value != operational_value:
                differing_fields[field] = {
                    "tracking": tracking_value,
                    "operational": operational_value,
                }
        for field in metadata_fields:
            if tracking[key].get(field) != operational[key].get(field):
                differing_fields[field] = {
                    "tracking": tracking[key].get(field),
                    "operational": operational[key].get(field),
                }
        if differing_fields:
            mismatches.append(
                {
                    **_key_payload(key),
                    "differing_fields": differing_fields,
                }
            )

    missing_in_operational = [
        _key_payload(key) for key in sorted(tracking_keys - operational_keys)
    ]
    missing_in_tracking = [
        _key_payload(key) for key in sorted(operational_keys - tracking_keys)
    ]
    issue_count = len(mismatches) + len(missing_in_operational) + len(missing_in_tracking)
    return {
        "status": "consistent" if issue_count == 0 else "inconsistent",
        "read_only": True,
        "scope": "integrated live Component 3 monitoring records",
        "summary": {
            "tracking_rows": len(tracking),
            "operational_rows": len(operational),
            "matched_rows": len(shared_keys) - len(mismatches),
            "mismatched_rows": len(mismatches),
            "missing_in_operational": len(missing_in_operational),
            "missing_in_tracking": len(missing_in_tracking),
            "issue_count": issue_count,
        },
        "mismatches": mismatches,
        "missing_in_operational": missing_in_operational,
        "missing_in_tracking": missing_in_tracking,
    }
