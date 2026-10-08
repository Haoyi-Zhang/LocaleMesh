"""Emit a local HTML adaptation of selected Jekyll Polyglot front matter.

This is deliberately not a Jekyll build.  It preserves the externally sourced
content identities, locale labels, and translated permalink shapes recorded in
``source-index.json`` while using the small independent LocaleMesh emitter.
"""
from __future__ import annotations
from pathlib import Path
import json
from .common import reset, route_file, html_page


def _route(origin: str, default_locale: str, record: dict) -> str:
    prefix = "" if record["locale"] == default_locale else record["locale"] + "/"
    return origin.rstrip("/") + "/" + prefix + record["permalink"].lstrip("/")


def build(source_root: Path, build_root: Path) -> None:
    data = json.loads((source_root / "source-index.json").read_text(encoding="utf8"))
    origin = data["adapted_origin"]
    locales = data["config"]["selected_locales"]
    default_locale = data["config"]["upstream_default_locale"]
    reset(build_root)

    grouped: dict[str, dict[str, dict]] = {}
    for raw in data["records"]:
        record = dict(raw)
        record["url"] = _route(origin, default_locale, record)
        grouped.setdefault(record["key"], {})[record["locale"]] = record

    order = sorted(grouped)
    for i, key in enumerate(order):
        variants = grouped[key]
        pairs = [(locale, variants[locale]["url"]) for locale in locales]
        next_key = order[(i + 1) % len(order)]
        for locale in locales:
            record = variants[locale]
            next_url = grouped[next_key][locale]["url"]
            dest = route_file(build_root, ".", record["url"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                html_page(
                    lang=locale,
                    key=key,
                    title=record["title"],
                    canonical=record["url"],
                    alternates=pairs,
                    links=[next_url],
                ),
                encoding="utf8",
            )
