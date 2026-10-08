#!/usr/bin/env python3
"""Record whether pinned native integration dependencies are available locally.

The probe is deliberately offline. Dependency absence is a measured capability
boundary, not a successful integration and not a reason for the reproduction
runner to fail.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "results" / "integration-probes.json"


def run(command: list[str], cwd: Path | None = None, timeout: int = 30) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "NEXT_TELEMETRY_DISABLED": "1", "ASTRO_TELEMETRY_DISABLED": "1"},
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "wall_s": time.perf_counter() - started,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "command": command,
            "error": str(error),
            "wall_s": time.perf_counter() - started,
        }


def npm_probe(family: str) -> dict:
    source = ROOT / "integrations" / family / "package.json"
    with tempfile.TemporaryDirectory(prefix=f"localemesh-{family}-probe-") as temporary:
        directory = Path(temporary)
        shutil.copy2(source, directory / "package.json")
        observation = run(
            ["npm", "install", "--offline", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=directory,
        )
    observation.update({
        "family": family,
        "mode": "offline package-resolution probe in an isolated temporary directory",
        "native_status": (
            "DEPENDENCIES_AVAILABLE_NOT_BUILT"
            if observation.get("returncode") == 0
            else "NOT_EXECUTED_DEPENDENCIES_UNAVAILABLE"
        ),
    })
    return observation


def main() -> None:
    observations = [npm_probe("astro")]
    hugo = run(["hugo", "version"])
    hugo.update({
        "family": "hugo",
        "mode": "installed executable version probe",
        "native_status": (
            "DEPENDENCY_AVAILABLE_NOT_BUILT"
            if hugo.get("returncode") == 0
            else "NOT_EXECUTED_DEPENDENCIES_UNAVAILABLE"
        ),
    })
    observations.append(hugo)
    observations.append(npm_probe("nextjs"))
    payload = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "offline_only": True,
        "probes": observations,
        "successful_native_builds": 0,
        "scope": (
            "Availability probe only. A source kit, cached dependency, or installed executable "
            "is not counted as a native build; successful build-and-check evidence must come "
            "from build_integration.py and is absent here."
        ),
    }
    RESULT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
