# Measured revision results

Retained laboratory releases, a Pandoc pipeline over the same PJ public sources, and an executed dependency-pruned upstream page API. A separate native Hugo adaptation adds equal-information and finite whole-cost results below. There is no deployment evidence.

## 10,000-route matched timings (ms)

| Change | Full | Record | Validated projected API | Full diff + API | Full/combined | Owners record/projected |
|---|---:|---:|---:|---:|---:|---|
| Local canonical | 252.85 | 0.212 | 0.306 | 91.13 | 2.77 | 3 / 1 |
| Page deletion | 260.19 | 0.210 | 0.542 | 94.78 | 2.75 | 3 / 3 |
| Unused alias | 270.53 | 329.530 | 8.651 | 88.24 | 3.07 | 10,000 / 0 |
| Global link policy | 255.88 | 355.008 | 1595.858 | 1674.75 | 0.15 | 10,000 / 10,000 |
| Hub canonical | 230.94 | 326.372 | 0.332 | 98.99 | 2.33 | 10,000 / 1 |
| Hub status | 253.44 | 637.897 | 1453.312 | 1531.64 | 0.17 | 10,000 / 10,000 |

12 paired alternating measurements per size/change in one process; IQR and range, not independent-process confidence intervals.

Memory is the owned live Python allocation measured by tracemalloc, including fact copies; not process RSS.
Record: 46.83 MiB / 90,000 edges. Projected: 238.47 MiB / 560,000 edges.

Pandoc pandoc 3.1.11.1: 11 releases, 53 successful native writer invocations; no native Jekyll build.

External page API: 26634 local page calls; 72848 fixture requests; zero external requests.
Only upstream severity=error is a rejection. Unsupported obligations are not counted as shared misses.

Ingestion: 7 legacy-implementation failures replayed; current expectations pass. This is a same-project regression, not an upstream historical bug.

## Native Hugo adaptation (five supplied public Markdown files)

The native whole-workflow numbers below use the earlier sliced refresh routine.
The current retaining refresh was measured by checking-only replay of these
outputs, reported separately in `MAINTENANCE-RESULTS.md`, without new builds or
reuse of old generation/extraction times in new workflow totals.

Hugo 0.147.9: 92 successful build subprocesses, including 84 measured alternating updates across seven changes. Eight configurations include the clean seed; four injected defects and three legitimate changes are labeled in the runner. Batch contract join, full scan, validated route-wide cache and validated sliced cache agree on every complete finding set. The single coherent translation-group swap yields six identity findings in the equal-information methods and no output-only annotation finding. This is one controlled release, not six natural faults or an external-policy oracle.

| Change | Whole join (ms) | Whole full (ms) | Whole sliced (ms) |
|---|---:|---:|---:|
| Body edit | 74.22 | 74.23 | 74.19 |
| Wrong canonical | 75.93 | 75.94 | 76.01 |
| Missing alternate | 79.03 | 79.05 | 79.36 |
| Omitted source | 75.10 | 75.10 | 75.52 |
| Identity swap | 74.12 | 74.13 | 74.80 |
| Partial translation | 73.15 | 73.26 | 73.67 |
| Canonical exception | 73.88 | 73.89 | 74.00 |

Medians of 12 paired component-accounted samples: native generation, full extraction/normalization, checking and JSON issue export, plus complete differencing/validated apply for caches. Generator medians span 69.27--74.46 ms; extraction spans 4.19--4.61 ms. Including cold setup in each of seven 12-update sequences gives total 6.946849 s join, 6.948246 s full, 6.981114 s route-wide and 6.978221 s sliced. Cold checking/export medians are 0.0478, 0.0704, 0.7546 and 0.8021 ms, respectively. There is no material whole-workflow cache advantage. The initial native build is measured once and reused across seven startup accounts; methods share build/extraction per row. These are not independent pipeline timings or production thresholds. Raw results and inclusive IQRs: `results/native-hugo-12/results.json`; scope and reproduction: `native_hugo/README.md`.
