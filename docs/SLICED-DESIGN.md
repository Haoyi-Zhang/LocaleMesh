# Obligation-sliced incremental evaluation

`localemesh.sliced.SlicedIncremental` is the production-oriented incremental path used by the current paper. It preserves the same release obligations as the independent full evaluator while changing the cached unit from an entire route predicate to six semantic slices.

## Cached slices

Each active route has a `gate` slice. A published, unambiguous route with both a declaration and an observation additionally has five live slices:

- `route`: publication status, document language, optional content marker, and sitemap membership;
- `canonical`: required/allowed canonical relations and canonical-target resolution;
- `discovery`: selected HTML, HTTP, or sitemap alternate relations, identity, locale/fallback, publication, and reciprocity;
- `agreement`: consistency among explicitly selected discovery channels;
- `links`: enabled ordinary local-link reachability.

The gate owns early-return semantics. It decides whether the other slices should exist. Changes to a declaration, observation presence, publication state, ambiguity flag, or identity bucket therefore reconcile the live slice family before affected slices are refreshed.

## Exact reads and invalidation

A read is represented by a primary fact, a nested mapping path, and an observation mode (`value`, `present`, or `keys`). Missing lookups are observations. For each slice and fact, equal sets of observations are interned as immutable footprints. The reverse index maps `(fact, footprint)` to the slices that used it.

Before a transaction is installed, the engine compares every old footprint attached to a changed fact against the prospective value. A slice is invalidated exactly when at least one observation in its old footprint changes. This retains dependencies that disappear in the new state, including removed targets and previously absent records. It does not use hashes, approximate summaries, diagnostic equality, or the new graph as a substitute for old reads.

The result set is reference-counted because two slices can report the same structured issue. Removing one slice must not remove a still-supported issue from another slice. Interned footprints are also reference-counted and reclaimed when their last reader disappears.

## Preservation conditions

The usual trace-reuse argument applies under the implementation's explicit conditions:

1. the owned snapshot is immutable during a check;
2. every predicate observation is mediated, including absence, membership, and key iteration;
3. the transaction contains the complete normalized primary change set;
4. identity buckets and the route-owner universe are maintained from both old and new declarations;
5. slice predicates are deterministic and side-effect free; and
6. gate reconciliation occurs before live slices are reused.

If an old slice is not invalidated, each observation on its old execution path has the same value. A first divergence in the new execution would have to occur at an observation reached after an identical prefix, contradicting the unchanged old footprint. Changed and newly enabled slices are recomputed; disabled and removed slices are discarded. This establishes conditional reuse of the sliced predicate, not editorial truth or universal correctness of the Web contract.

## Independent checks

The implementation is checked at four levels:

- unit tests compare issue sets, exact read unions, invalidated readers, deletion/reinsertion, dynamic gate transitions, reference counts, transaction rollback, and input ownership;
- all 321 retained release snapshots compare the full evaluator, route-wide caches, obligation-sliced cache, and validated transactions;
- a bounded state space enumerates 5,120 structurally valid two-locale states in a one- or two-fact Gray-order sequence, comparing 5,119 incremental transitions and 20 cold reconstructions;
- every timing repetition materializes and compares the complete issue set before its measurement is retained.

These checks are stronger than implementation agreement alone because the full evaluator is separately written and parser behavior is also tested against literal expectations and native Chromium tree construction. They remain bounded tests rather than a formal proof or an independent human oracle.

## Cost model and trade-off

Let `J` be the exact old observations attached to changed facts, `A` the invalidated slices, and `D'_a` each refreshed slice's new read set. Ignoring the size of copied values, an update costs

```
O(|J| + sum(a in A) (check(a) + |D_a| + |D'_a|)).
```

Slicing reduces repeated rule work when a broad fact affects one obligation per route rather than an entire route predicate. It adds reader records, reverse memberships, and issue-reference bookkeeping. A configuration change that alters no observed projection can still require traversal of many distinct footprints, and full snapshot differencing remains a separate linear cost. The delivered benchmark therefore reports route-wide and sliced transactions, full checking, differencing, retained-object memory, adverse changes, and scale separately.
