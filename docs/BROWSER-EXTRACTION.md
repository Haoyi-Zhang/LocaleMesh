# Native offline HTML tree extraction

The optional `BrowserExtractor` uses Chromium's actual HTML `DOMParser` through a local DevTools connection. The measured binary is Chromium 144.0.7559.96. It is an independent implementation of tree construction relative to Python's event parser; the JavaScript selectors, profile and common URL normalizer remain authored by this project.

Input strings are parsed inertly from an `about:blank` context and are never navigated. Resource URLs are blocked and external host resolution is disabled. The measured comparison records no `Network.requestWillBeSent` events, and input-script sentinel checks remain false. This is not a general browser sandbox or security claim: the container launches Chromium with `--no-sandbox` for the local bounded corpus. Do not use this artifact's launch settings as a production isolation configuration for untrusted adversarial inputs.

Because DOMParser uses its context's document URL, URL references are normalized against the explicitly supplied response URL and first eligible base. This also means the comparison is not an independent test of the common URI normalizer. The selected profile excludes template content, non-HTML namespace nodes and noscript descendants; noscript introduces a diagnostic rather than an invented scripting mode. It selects document language, content markers, head canonicals/alternates, anchors and supported zero-delay refreshes. It does not execute client hydration, Liquid, routing middleware or translation logic.

The benchmark's 30 boundary cases include recovery, raw text, templates, foreign content, duplicate attributes, relative bases, qualified links and conflicting content markers. Five selected-fact differences from the lightweight parser are all diagnosed by that parser. Eighteen native results also have literal expected canonical outputs. All 53 retained Pandoc outputs agree on selected facts, and all 11 actual compiled release-gate results agree. These are correlated inputs, not additional independent sites.

To run the comparison after rebuilding the Pandoc cases:

```sh
python scripts/evaluate_pandoc.py
python scripts/evaluate_browser.py
```

The CLI's `--browser` option explicitly selects native HTML extraction. Missing Chromium or websocket-client fails that request; it never silently falls back to the event parser. Tests of pure `normalize_dom` do not require Chromium. See `python -m localemesh.cli --help` for argument positions. Browser dependencies are optional for smoke testing but required by the complete reproduction runner.
