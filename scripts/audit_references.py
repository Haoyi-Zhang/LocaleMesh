#!/usr/bin/env python3
"""Structural bibliography audit.

This audit checks reproducible local invariants: every BibTeX entry has one metadata
record and one in-text citation, identifiers are unique, required fields are present,
and no entry repeats a field.  It does not contact publishers and therefore does not
claim independent online verification of bibliographic truth.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT.parent / "paper"
BIB = PAPER / "references.bib"
TEX = PAPER / "manuscript.tex"
META = ROOT / "docs" / "reference-metadata.json"
OUT = ROOT / "results" / "reference-audit.json"

ENTRY = re.compile(r"@(\w+)\{([^,]+),(.*?)(?=\n@\w+\{|\Z)", re.S)
FIELD = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*\{(.*?)\},?\s*$", re.S)
DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)


def parse_bib(text: str):
    entries = []
    for kind, key, body in ENTRY.findall(text):
        fields = []
        for m in FIELD.finditer(body):
            fields.append((m.group(1).lower(), m.group(2).strip()))
        names = [name for name, _ in fields]
        duplicate_fields = sorted({name for name in names if names.count(name) > 1})
        entries.append({"kind": kind.lower(), "key": key.strip(),
                        "fields": dict(fields), "duplicate_fields": duplicate_fields})
    return entries


def main():
    bib_text = BIB.read_text(encoding="utf8")
    tex_text = TEX.read_text(encoding="utf8")
    entries = parse_bib(bib_text)
    metadata = json.loads(META.read_text(encoding="utf8"))

    keys = [entry["key"] for entry in entries]
    assert len(keys) == len(set(keys)), "duplicate BibTeX keys"
    assert len(entries) >= 61, f"expected >60 references, found {len(entries)}"
    assert all(not entry["duplicate_fields"] for entry in entries), {
        entry["key"]: entry["duplicate_fields"] for entry in entries if entry["duplicate_fields"]
    }

    cited = {key.strip() for group in re.findall(r"\\cite\w*\{([^}]+)\}", tex_text)
             for key in group.split(",")}
    assert set(keys) == cited, {"uncited": sorted(set(keys) - cited),
                                "undefined": sorted(cited - set(keys))}

    meta_keys = [row["key"] for row in metadata]
    assert len(meta_keys) == len(set(meta_keys)), "duplicate metadata keys"
    assert set(meta_keys) == set(keys), {
        "metadata_only": sorted(set(meta_keys) - set(keys)),
        "bib_only": sorted(set(keys) - set(meta_keys)),
    }

    doi_values = []
    for entry in entries:
        fields = entry["fields"]
        assert fields.get("author") and fields.get("title"), entry["key"]
        if entry["kind"] in {"article", "inproceedings"}:
            assert fields.get("year"), entry["key"]
        if "doi" in fields:
            assert DOI.match(fields["doi"]), (entry["key"], fields["doi"])
            doi_values.append(fields["doi"].lower())
        if "url" in fields:
            assert fields["url"].startswith("https://"), (entry["key"], fields["url"])
    assert len(doi_values) == len(set(doi_values)), "duplicate DOI"

    # Metadata is the machine-readable mirror used for manual/source review.
    for row in metadata:
        entry = next(item for item in entries if item["key"] == row["key"])
        assert row["kind"].lower() == entry["kind"], row["key"]
        for field in ("author", "title", "year", "pages", "doi", "url"):
            if field in row:
                assert row[field] == entry["fields"].get(field), (row["key"], field)

    report = {
        "bibliography_entries": len(entries),
        "in_text_citations": len(cited),
        "doi_entries": len(doi_values),
        "metadata_records": len(metadata),
        "all_entries_cited_once_or_more": True,
        "duplicate_keys": 0,
        "duplicate_fields": 0,
        "scope": "Local structural audit; publisher/source verification is documented separately and is not inferred from this script.",
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
