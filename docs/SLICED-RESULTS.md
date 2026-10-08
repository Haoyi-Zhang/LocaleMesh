# Obligation-sliced incremental evaluation

Complete normalized snapshot difference plus validated transaction and complete issue materialization. HTML parsing, framework builds and event acquisition are excluded.

| Change | Full ms | C txn ms | S txn ms | Diff + S ms | Full / combined | S slices |
|---|---:|---:|---:|---:|---:|---:|
| Local canonical | 249.00 | 0.10 | 0.07 | 85.64 | 2.91 | 1 |
| Page deletion | 220.07 | 0.25 | 0.20 | 82.13 | 2.68 | 8 |
| Unused alias | 253.87 | 37.28 | 60.45 | 132.77 | 1.91 | 0 |
| Global link policy | 244.04 | 873.85 | 312.63 | 400.65 | 0.61 | 10,000 |
| Hub canonical | 214.92 | 0.10 | 0.07 | 87.45 | 2.46 | 1 |
| Hub status | 218.67 | 761.25 | 225.40 | 292.55 | 0.75 | 10,005 |

Twelve alternating paired updates per change and scale; rotating full/core execution order and alternating validated transaction order. Medians and inclusive IQRs are process observations, not independent-site estimates.

Recursive retained-object measurements include each cache's owned fact copy and use identity-deduplicated sys.getsizeof over cache roots; the caller's input, process RSS and browser memory are excluded.

C / 10,000 / 90,000 / 560,000 / 83.95
S / 60,000 / 240,000 / 940,000 / 142.34

Slicing preserves the union of exact field reads in the bounded state-space experiment.
It lowers broad-update recomputation but stores more reader records and can lose on changes that invalidate no reader yet require scanning many footprint groups.
