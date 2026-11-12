import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Component3ModelVerificationCliTests(unittest.TestCase):
    def test_committed_active_models_pass_deployment_verification(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.component3.verify_component3_models",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["runtime_model_version"], "v3")
        self.assertEqual(report["verified_artifact_count"], 5)

    def test_missing_manifest_fails_with_a_machine_readable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.component3.verify_component3_models",
                    "--models-directory",
                    directory,
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stderr)
        self.assertEqual(report["status"], "failed")
        self.assertIn("manifest", report["error"])


if __name__ == "__main__":
    unittest.main()
