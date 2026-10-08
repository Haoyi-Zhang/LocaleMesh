# LocaleMesh

Contract-aware, obligation-sliced checking of multilingual Web releases.
The checker compares declared content identity, locale and discovery contracts
with emitted HTML, headers, sitemaps and publication state. It does not infer
translation identity from text similarity.

## Run

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

The current suite contains 74 tests. `inputs/`, `integrations/`,
`independent_sources/`, and `results/` retain the study inputs and measurements.
`RESULTS-SUMMARY.json` gives the paired timing calculation and measurement
scope. Combined-cost medians are computed from paired samples, not by adding
unrelated medians. The current offline browser-tree projection is separately
recorded under `results/local-validation/`; it is not a new Chromium run.

Browser reconstruction, Pandoc compilation, and full timing experiments have
additional dependencies documented with their scripts. The portable CI tests
the checker; it does not silently substitute model checks for those experiments.
Third-party sources retain their licenses and `THIRD-PARTY-NOTICES.md`.
