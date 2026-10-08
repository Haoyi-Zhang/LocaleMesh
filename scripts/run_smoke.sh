#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
python -m unittest discover -s tests -v
python scripts/evaluate_state_space.py
python -m localemesh.cli inputs/A1/manifest.json inputs/A1/build --output results/smoke-findings.json
