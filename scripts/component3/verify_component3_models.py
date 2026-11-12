"""Verify every active Component 3 model artifact before deployment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from components.component3_model_registry import (
    ModelArtifactIntegrityError,
    audit_model_artifacts,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Component 3 model manifest and SHA-256 checksums."
    )
    parser.add_argument(
        "--models-directory",
        type=Path,
        default=PROJECT_ROOT / "models",
        help="Directory containing the manifest and active artifacts",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        report = audit_model_artifacts(args.models_directory)
    except ModelArtifactIntegrityError as error:
        print(
            json.dumps(
                {
                    "component": "component3",
                    "status": "failed",
                    "error": str(error),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
