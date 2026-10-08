#!/usr/bin/env python3
"""Fresh sequential reproduction with no trusted checkpoints.

Every stage is executed and must return zero. Tool versions, resource bounds, wall
time, commands, logs, and completion are recorded even when a stage fails.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
PYTHON = sys.executable
os.environ.update(
    PYTHONHASHSEED="0",
    OPENBLAS_NUM_THREADS="1",
    OMP_NUM_THREADS="1",
    MKL_NUM_THREADS="1",
)

stages: list[tuple[str, list[str]]] = [
    ("coverage-reset", [PYTHON, "-m", "coverage", "erase"]),
    ("tests", [PYTHON, "-m", "coverage", "run", "--source=localemesh", "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ("coverage-json", [PYTHON, "-m", "coverage", "json", "-o", "results/coverage.json"]),
    ("coverage-report", [PYTHON, "-m", "coverage", "report", "--fail-under=85"]),
    ("integration-capability", [PYTHON, "scripts/probe_integrations.py"]),
    ("evaluate", [PYTHON, "scripts/evaluate.py"]),
    ("evaluate-independent", [PYTHON, "scripts/evaluate_independent.py"]),
    ("evaluate-state-space", [PYTHON, "scripts/evaluate_state_space.py"]),
    ("ingestion-replay", [PYTHON, "scripts/evaluate_ingestion.py"]),
    ("external-page", [PYTHON, "scripts/evaluate_external.py"]),
    ("pandoc", [PYTHON, "scripts/evaluate_pandoc.py"]),
    ("contract-boundary", [PYTHON, "scripts/evaluate_contract_boundary.py"]),
    ("browser-differential", [PYTHON, "scripts/evaluate_browser.py"]),
]
for routes in (100, 1_000, 10_000):
    for kind in ("local_canonical", "deleted_page", "global_alias_policy", "hub_observation"):
        stages.append((
            f"benchmark-{routes}-{kind}",
            [PYTHON, "scripts/benchmark.py", "--routes", str(routes), "--kind", kind, "--repeats", "12"],
        ))
stages.append(("fanout-sweep", [PYTHON, "scripts/fanout_sweep.py"]))
for routes in (100, 1_000, 10_000):
    stages.append((f"projected-{routes}", [PYTHON, "scripts/benchmark_faceted.py", "--routes", str(routes), "--repeats", "12"]))
for routes in (100, 1_000, 10_000):
    stages.append((f"coalesced-{routes}", [PYTHON, "scripts/benchmark_coalesced.py", "--routes", str(routes), "--repeats", "12"]))
for routes in (100, 1_000, 10_000):
    stages.append((f"sliced-{routes}", [PYTHON, "scripts/benchmark_sliced.py", "--routes", str(routes), "--repeats", "12"]))
stages.extend([
    ("analysis", [PYTHON, "scripts/analyze.py", "--plots"]),
    ("field-analysis", [PYTHON, "scripts/analyze_revision.py", "--plots"]),
    ("coalesced-analysis", [PYTHON, "scripts/analyze_coalesced.py", "--plots"]),
    ("sliced-analysis", [PYTHON, "scripts/analyze_sliced.py", "--plots"]),
    ("reference-audit", [PYTHON, "scripts/audit_references.py"]),
    ("result-audit", [PYTHON, "scripts/audit_results.py"]),
    ("paper-build", [PYTHON, "../paper/build.py"]),
    ("pdf-preflight", [PYTHON, "scripts/pdf_preflight.py"]),
])

started = time.perf_counter()


def read_text(path: str):
    try:
        return Path(path).read_text(encoding="utf8").strip()
    except OSError:
        return None


report = {
    "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "python": platform.python_version(),
    "platform": platform.platform(),
    "cpu_affinity": sorted(os.sched_getaffinity(0)),
    "cpu_quota": read_text("/sys/fs/cgroup/cpu.max"),
    "memory_limit": read_text("/sys/fs/cgroup/memory.max"),
    "disk_free_bytes": shutil.disk_usage(ROOT).free,
    "stages": [],
    "execution_mode": "fresh sequential; every stage executed; no checkpoint skips",
    "hash_seed": os.environ["PYTHONHASHSEED"],
    "numeric_threads": 1,
    "single_command_full_run_verified": False,
    "complete": False,
}


def save():
    report["wall_s"] = time.perf_counter() - started
    (RESULTS / "execution-status.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")


save()
try:
    for name, command in stages:
        print("START", name, flush=True)
        stage_started = time.perf_counter()
        log = RESULTS / f"{name}.log"
        with log.open("w", encoding="utf8") as stream:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=False,
                env=os.environ.copy(),
            )
        duration = time.perf_counter() - stage_started
        report["stages"].append({
            "name": name,
            "command": command,
            "returncode": completed.returncode,
            "wall_s": duration,
            "log": str(log.relative_to(ROOT)),
        })
        save()
        print("END", name, completed.returncode, round(duration, 2), flush=True)
        if completed.returncode:
            raise RuntimeError(f"{name} failed; inspect {log}")
    report["complete"] = True
    report["single_command_full_run_verified"] = True
    report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["counts"] = json.loads((RESULTS / "result-audit.json").read_text(encoding="utf8"))
    report["scope"] = (
        "Executed laboratory reproduction. Production deployment, independent human "
        "adjudication, and unavailable native i18n-framework builds are outside this run."
    )
    save()
    print("FULL RUN COMPLETE", round(report["wall_s"], 2), "seconds", flush=True)
except BaseException as error:
    report["error"] = str(error)
    save()
    raise
