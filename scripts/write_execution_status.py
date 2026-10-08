#!/usr/bin/env python3
"""Read the fresh driver's record; never turn component files into a verified run."""
import json
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'results/execution-status.json'
d=json.loads(p.read_text());print(json.dumps(d,indent=2))
if not d.get('complete') or not d.get('single_command_full_run_verified'):raise SystemExit(1)
