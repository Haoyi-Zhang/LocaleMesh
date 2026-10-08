#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
if [[ $# -ne 0 ]]; then echo "usage: bash scripts/run_full.sh (fresh rerun; no cached stages)" >&2; exit 2; fi
python scripts/run_all.py
