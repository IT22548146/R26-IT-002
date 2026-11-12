import json
import tempfile
import unittest
from pathlib import Path

from components.component3_model_registry import (
    ModelArtifactIntegrityError,
    audit_model_artifacts,
    load_model_manifest,
    sha256_file,
    verify_model_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Component3ModelRegistryTests(unittest.TestCase):
    def test_active_runtime_artifacts_match_the_committed_manifest(self):
        audit = audit_model_artifacts(PROJECT_ROOT / "models")

        self.assertEqual(audit["status"], "verified")
        self.assertEqual(audit["runtime_model_version"], "v3")
        self.assertEqual(audit["verified_artifact_count"], 5)
        self.assertTrue(all(item["verified"] for item in audit["artifacts"]))

    def test_modified_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            models_directory = Path(directory)
            artifact_path = models_directory / "model.pkl"
            artifact_path.write_bytes(b"original model")
            manifest = {
                "manifest_schema_version": "1.0",
                "component": "component3",
                "runtime_model_version": "test",
                "prediction_contract_version": "test-contract",
                "feature_schema_versions": {"risk_type": "test-features"},
                "artifacts": [
                    {
                        "role": "risk_type_classifier",
                        "filename": artifact_path.name,
                        "sha256": sha256_file(artifact_path),
                        "required": True,
                    }
                ],
            }
            (models_directory / "component3_model_manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            load_model_manifest(models_directory)
            artifact_path.write_bytes(b"tampered model")

            with self.assertRaisesRegex(
                ModelArtifactIntegrityError,
                "checksum mismatch",
            ):
                verify_model_artifact(
                    models_directory,
                    "risk_type_classifier",
                )

    def test_unsafe_manifest_filename_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            models_directory = Path(directory)
            manifest = {
                "manifest_schema_version": "1.0",
                "component": "component3",
                "runtime_model_version": "test",
                "prediction_contract_version": "test-contract",
                "feature_schema_versions": {"risk_type": "test-features"},
                "artifacts": [
                    {
                        "role": "risk_type_classifier",
                        "filename": "../outside.pkl",
                        "sha256": "0" * 64,
                        "required": True,
                    }
                ],
            }
            (models_directory / "component3_model_manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ModelArtifactIntegrityError, "unsafe"):
                load_model_manifest(models_directory)


if __name__ == "__main__":
    unittest.main()
