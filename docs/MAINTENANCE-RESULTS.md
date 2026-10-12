# Differential cache-membership maintenance

An invalidated slice still evaluates all of its rules on the new snapshot. The
refresh now retains equal old/new fact footprints and updates only added/removed
finding references. The previous refresh removed and reinserted all memberships.
Neither version substitutes result equality for dependency equality. Old reads,
missing dependencies, gate reconciliation, validation, owned copies and duplicate
finding support remain in use.

## Reproduce the comparison

From `artifact/`, using Python 3.12 or a compatible environment:

```sh
PYTHONHASHSEED=118 python scripts/benchmark_maintenance.py --routes 10000 --repeats 12 --output results/maintenance-new.json
python scripts/verify_maintenance.py --output results/maintenance-replay-new.json
python scripts/evaluate_state_space.py --output results/state-space-maintenance-new.json
python -m unittest discover -s tests -v
```

On PowerShell, set `$env:PYTHONHASHSEED='118'` before invoking Python. Set `TEMP`
and `TMP` to an existing artifact-local `.test-tmp` directory for local test
scratch files. `verify_maintenance.py` uses that directory explicitly. Result
paths supplied to these scripts must be new files inside `artifact/results`.
No native generator or dependency installer is invoked by this comparison.

`results/maintenance-10000-12.json` records Python 3.12.14 on Windows amd64,
hash seed 118, raw samples, inclusive IQRs, checking order, cold costs, source
identities and both refresh routines. The predecessor routine is retained only
as an internal maintenance baseline; it is not an independent competitor.

Each family has two-way warm-up followed by 12 alternating updates. Timing
blocks rotate by family and retain one cache at a time in one process. Methods
share normalized facts and complete deterministic JSON finding export. Cache
times include `ReleaseSession` normalization, identity-bucket updates, owned
copies and apply. Full snapshot difference is measured separately and added
sample by sample. Cold setup/export is also recorded. Fixture construction,
input loading, reference calculation, assertions, warm-up, GC between blocks,
reporting, generation and extraction are outside these timings. Repetitions are
process observations, not independent sites or multi-machine confidence bounds.

## Synthetic 10,000-route results

Medians in ms; ratios are paired old/new transaction medians, not ratios of the
displayed medians. These validated transactions also serialize findings, unlike
the older scale experiment's set materialization. Absolute numbers from the two
runs are not interchangeable.

| Change | Full + JSON | Previous refresh | Retaining refresh | Diff + retaining | Paired old/new |
| --- | ---: | ---: | ---: | ---: | ---: |
| Local canonical | 162.047 | 0.079 | 0.087 | 33.185 | 0.96 |
| Page deletion | 156.532 | 0.201 | 0.212 | 33.953 | 0.96 |
| Unused alias | 156.460 | 18.333 | 19.294 | 46.547 | 0.95 |
| Global link policy | 152.847 | 157.946 | 150.174 | 177.639 | 1.02 |
| Hub canonical | 140.274 | 0.092 | 0.074 | 36.377 | 1.12 |
| Hub status | 166.266 | 166.217 | 131.437 | 163.962 | 1.25 |

Hub-status old/new ratios have IQR 1.21--1.32. Its paired full/(diff + retaining)
ratio has median 1.005 and IQR 0.936--1.090: combined cost is near parity, not a
stable full-scan speedup. Global policy still loses to full scanning by the
paired median (0.891 full/combined, IQR 0.712--1.001). Smaller cases include
regressions. Reduced membership churn therefore does not imply a general
transaction or workflow benefit.

At cold construction, identity-deduplicated `sys.getsizeof` totals including
owned facts are 88,026,497 bytes for the route-wide cache and 149,256,812 bytes
for either sliced routine, a 1.70 ratio. Both sliced routines retain 60,000
readers, 240,000 fact groups and 940,000 logical projection edges. This is not
RSS, peak transient allocation or evidence of memory compression.

## Retained native-output replay

The seven change families load `results/native-hugo-12` candidates. The inputs
remain the same five-file, one-upstream Hugo adaptation. No new build is counted.
Join, full, previous sliced refresh and retaining refresh agree on all findings.
Across cold setup plus 84 checking updates, totals are 3.635 ms for the join,
5.132 ms full, 33.982 ms for previous sliced refresh and 34.129 ms for retaining
refresh; cached totals include differencing. Small transaction changes do not
repay setup here. Generation and extraction were not timed or added from an old
run; these are checking-only totals, not a fresh end-to-end measurement.

The original 92 native commands and whole-workflow negative result remain in
`native-hugo-12/results.json`. The original 321-case, Pandoc, Crawl Cove,
Chromium and multi-scale results remain separate populations and measurements.

## Preservation checks

`results/maintenance-replay.json` records checking of 174 named cases, 96
recorded compositions, 40 secondary-emitter/adaptation cases and 11 retained
Pandoc candidates, plus all 92 retained Hugo candidates. The repaired and
previous sliced traces agree, as do full findings and validated sessions.
Primary/composition inputs are reconstructed from recorded operators; secondary
cases are remutated in temporary copies of retained clean emissions. Composition
records contain counts rather than complete old issue tuples; they additionally
match their stored release-finding counts. These are regression rechecks, not a
fresh holdout or additional independent sites.

`results/state-space-maintenance.json` rechecks 5,120 states, 5,119 transitions
and 20 cold constructions, including route-wide/sliced exact read unions on
that bounded state space. Windows RSS is left unavailable, not invented. The
84-test suite includes changed-trace/equal-result and equal-trace/changed-result
regressions, finding reference counts, reclamation, rollback and ownership.
Agreement does not establish editorial truth, natural-fault recall, arbitrary
state soundness or industrial deployment evidence.
