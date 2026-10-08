# Exact coalescing of field-read traces

## Representation

`FacetedIncremental` (P) records triples `(fact, path, mode)` for each owner. `CoalescedIncremental` (C) groups the owner's reads by fact, interns each immutable set of `(path, mode)`, and maintains reverse `fact -> footprint -> owners` groups. Both execute the unchanged `check_owner` predicate. Hash tables use ordinary collision-resolving object equality; no digest, approximate membership filter, or cached success value substitutes for an observation.

A changed group affects exactly its old readers when at least one old projection differs between the old and future fact. The union over groups is therefore the same affected-owner set as P. Directly changed route owners are added in both. Deletion uses the missing sentinel, not an empty record. Missing reads, container type/existence, dictionary membership and keys remain observations. Atomic lists and output normalization follow the P implementation.

The representation proof is an equality of sets, not a claim that the predicate implements every Web requirement. The conditional reuse argument additionally requires owned snapshots, read-only deterministic evaluation, mediated reads and complete primary changes. It preserves the implemented owner predicate, not editorial correctness.

## Storage lifetime and transaction boundary

An owner replacement removes its old reverse memberships and decrements footprint reference counts. Zero-reference entries are removed. `expanded_reads(owner)` is a test-only inspection that reconstructs the precise P trace. The supported transaction API derives old/new identity groups and owns copied facts. Lower-level cache updates expect normalized complete deltas; they do not discover missing filesystem events or recover arbitrary client mutations of internal indices.

The publication contract has strict field names at configuration, page-policy and nested discovery-policy boundaries. `extensions` is an explicit nonsemantic object at those boundaries. Other top-level artifact metadata and extra observation fields are not advertised as globally prohibited. Redirect states require an explicit target or nonempty allowed-target list. Schema validation finishes before any transaction is installed.

## Tests

The additional six coalescing test methods exercise every named case forward/reverse on small versions of all six configurations, 600 sequential changes, 150 distinct alias insertions/restorations, complete owner deletion/reinsertion, caller ownership/rollback, and the local hub canonical case. Expanded traces, findings, edge counters and pool references are checked. These deterministic bounded tests do not establish unrestricted browser or arbitrary-code conformance.

## Evaluation

`benchmark_coalesced.py` compares F/P/C core execution in rotating order and safe P/C transactions in alternating order, with two directional warmups and 12 retained updates per change/size. Every comparison materializes the full finding set. All P/C pairs must agree on affected-owner and expanded-read counts. Memory is separately traced for R/P/C and includes owned input copies; it is neither RSS nor total browser allocation. Complete snapshot difference is separately measured and then charged per pair. No event acquisition, HTML parse or native builder work is hidden in the cache timing.

`analyze_coalesced.py` generates all headline numbers, tables and vector figures from the raw files. The negative unused-alias result and broad-update losses to full scanning remain in the main paper. Compression is data-dependent; no constant memory, universal speedup or automatically selected mode is claimed.

## Closest methods

Fine-grained incremental consistency checking, dynamic dependency traces, and memory-conscious consistency checking predate this implementation. In particular, Falleri et al., *Incremental inconsistency detection with low memory overhead*, Software: Practice and Experience 44(5), 621–641 (2014), DOI 10.1002/spe.2171, use pre-instantiated impact lists obtained by static rule analysis rather than this exact dynamic trace grouping. That paper is cited in the manuscript; it is not an executed comparator. The contribution here is the release-specific realization, exact representation relation and measured costs, not the first use of grouping or low-memory consistency checking.
