# Measured revision results

Authored laboratory releases, one actual Pandoc pipeline over the same PJ public sources, and an executed dependency-pruned upstream page API. No deployment or native i18n-framework result.

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
