"""Versioned artifact manifest and integrity checks for Component 3 models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "component3_model_manifest.json"
SHA256_HEX_LENGTH = 64


class ModelArtifactIntegrityError(RuntimeError):
    """Raised when the Component 3 model contract or artifact is invalid."""


def _safe_artifact_path(models_directory: Path, filename: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise ModelArtifactIntegrityError(
            f"Model manifest contains an unsafe artifact filename: {filename!r}"
        )
    return models_directory / filename


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def load_model_manifest(models_directory: str | Path) -> dict[str, Any]:
    """Load and validate the structure of the active model manifest."""
    models_path = Path(models_directory)
    manifest_path = models_path / MANIFEST_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelArtifactIntegrityError(
            f"Missing Component 3 model manifest: {manifest_path}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ModelArtifactIntegrityError(
            f"Could not read Component 3 model manifest: {manifest_path}"
        ) from error

    if not isinstance(manifest, dict):
        raise ModelArtifactIntegrityError("Component 3 model manifest must be a JSON object")
    if manifest.get("component") != "component3":
        raise ModelArtifactIntegrityError("Component 3 model manifest has the wrong component")
    if manifest.get("manifest_schema_version") != "1.0":
        raise ModelArtifactIntegrityError("Unsupported Component 3 manifest schema version")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ModelArtifactIntegrityError("Component 3 model manifest has no artifacts")

    seen_roles: set[str] = set()
    seen_filenames: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ModelArtifactIntegrityError("Model manifest artifacts must be objects")
        role = artifact.get("role")
        filename = artifact.get("filename")
        checksum = artifact.get("sha256")
        if not isinstance(role, str) or not role.strip():
            raise ModelArtifactIntegrityError("Every model artifact requires a role")
        if role in seen_roles:
            raise ModelArtifactIntegrityError(f"Duplicate model artifact role: {role}")
        if not isinstance(filename, str):
            raise ModelArtifactIntegrityError(f"Model artifact {role} has no filename")
        _safe_artifact_path(models_path, filename)
        if filename in seen_filenames:
            raise ModelArtifactIntegrityError(f"Duplicate model artifact filename: {filename}")
        if not _valid_sha256(checksum):
            raise ModelArtifactIntegrityError(f"Model artifact {role} has an invalid SHA-256")
        if not isinstance(artifact.get("required"), bool):
            raise ModelArtifactIntegrityError(f"Model artifact {role} has no required flag")
        seen_roles.add(role)
        seen_filenames.add(filename)

    feature_versions = manifest.get("feature_schema_versions")
    if not isinstance(feature_versions, dict) or not feature_versions:
        raise ModelArtifactIntegrityError("Model manifest has no feature schema versions")
    if not isinstance(manifest.get("prediction_contract_version"), str):
        raise ModelArtifactIntegrityError("Model manifest has no prediction contract version")
    return manifest


def sha256_file(path: str | Path) -> str:
    """Return a streaming SHA-256 digest without loading the artifact into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_by_role(manifest: dict[str, Any], role: str) -> dict[str, Any]:
    for artifact in manifest["artifacts"]:
        if artifact["role"] == role:
            return artifact
    raise ModelArtifactIntegrityError(f"Model manifest has no artifact for role: {role}")


def verify_model_artifact(
    models_directory: str | Path,
    role: str,
    *,
    expected_filename: str | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify one artifact and return non-sensitive audit metadata."""
    models_path = Path(models_directory)
    active_manifest = manifest or load_model_manifest(models_path)
    artifact = _artifact_by_role(active_manifest, role)
    filename = str(artifact["filename"])
    if expected_filename is not None and filename != expected_filename:
        raise ModelArtifactIntegrityError(
            f"Model manifest filename mismatch for {role}: expected {expected_filename}"
        )
    artifact_path = _safe_artifact_path(models_path, filename)
    if not artifact_path.is_file():
        raise ModelArtifactIntegrityError(f"Missing Component 3 model artifact: {filename}")
    actual_checksum = sha256_file(artifact_path)
    expected_checksum = str(artifact["sha256"]).lower()
    if actual_checksum != expected_checksum:
        raise ModelArtifactIntegrityError(
            f"Component 3 model artifact checksum mismatch: {filename}"
        )
    return {
        "role": role,
        "filename": filename,
        "sha256": actual_checksum,
        "verified": True,
    }


def audit_model_artifacts(
    models_directory: str | Path,
    roles: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Verify a selected set of roles, or every required active artifact."""
    manifest = load_model_manifest(models_directory)
    selected_roles = list(roles) if roles is not None else [
        str(artifact["role"])
        for artifact in manifest["artifacts"]
        if artifact["required"]
    ]
    artifacts = [
        verify_model_artifact(models_directory, role, manifest=manifest)
        for role in selected_roles
    ]
    return {
        "status": "verified",
        "manifest_schema_version": manifest["manifest_schema_version"],
        "runtime_model_version": manifest["runtime_model_version"],
        "prediction_contract_version": manifest["prediction_contract_version"],
        "feature_schema_versions": dict(manifest["feature_schema_versions"]),
        "verified_artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
