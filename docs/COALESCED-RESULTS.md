# Coalesced field reads: measured results

Complete normalized snapshot difference plus validated cache transaction. Page parsing, native builders and event acquisition excluded.

| Change | Full ms | P API ms | C API ms | Diff + C ms | Full / combined | Owners P=C |
|---|---:|---:|---:|---:|---:|---:|
| Local canonical | 226.00 | 0.238 | 0.201 | 80.72 | 2.80 | 1 |
| Page deletion | 266.65 | 0.504 | 0.318 | 102.35 | 2.61 | 3 |
| Unused alias | 258.87 | 8.136 | 42.508 | 119.26 | 2.17 | 0 |
| Global link policy | 259.09 | 1585.980 | 790.604 | 879.36 | 0.29 | 10,000 |
| Hub canonical | 229.03 | 0.257 | 0.192 | 98.29 | 2.33 | 1 |
| Hub status | 247.84 | 1465.599 | 753.300 | 832.02 | 0.30 | 10,000 |

12 alternating paired updates per kind/size; rotating core and safe-engine order; median and inclusive IQR in one process, not independent-site estimates.

Separate tracemalloc measurements including owned fact copies and cache; existing input excluded. Neither process RSS nor browser memory.

Record (R) / 90,000 / 46.83
Field (P) / 560,000 / 238.47
Coalesced (C) / 90,000 / 75.51

C retains 560,000 expanded field reads in 90,000 owner/fact edges and 10,006 interned footprints.
Live allocation reduction relative to P: 68.33%. No constant-space claim.
The unused-alias update is a negative result for C versus P; both broad-update cases remain slower than full checking. No automatic switching is implemented.
