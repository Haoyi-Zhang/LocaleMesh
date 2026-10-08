#!/usr/bin/env python3
"""Structural checks of the anonymous PDF retained by paper/build.py.

The builder checks its temporary TeX log before installing main.pdf. That log
is not retained, so this script cannot attest to build diagnostics or layout.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz

PAPER = Path(__file__).resolve().parents[2] / "paper"
RESULTS = PAPER.parent / "artifact" / "results"


def inspect(pdf: Path):
    with fitz.open(pdf) as document:
        page_texts = [page.get_text() for page in document]
        references = [
            number + 1
            for number, text in enumerate(page_texts)
            if re.search(r"(?m)^References$", text)
        ]
        assert references == [9], (pdf.name, references)
        assert len(document) <= 12, (pdf.name, len(document))
        text = "\n".join(page_texts)
        assert "[?]" not in text
        assert "Haoyi Zhang" not in text and "Huaijin Ran" not in text and "Xunzhu Tang" not in text
        assert "Anonymous Author" in text
        assert not (document.metadata.get("author") or "").strip()
        return {
            "file": pdf.name,
            "pages": len(document),
            "references_start_page": references[0],
            "main_pages": references[0] - 1,
            "words_per_page": [len(text.split()) for text in page_texts],
            "anonymous": True,
            "author_metadata_empty": True,
            "no_unresolved_reference_markers_in_pdf": True,
        }


def build_report(paper: Path = PAPER):
    return {
        "anonymous_review": inspect(paper / "main.pdf"),
        "tex_log_checks": {
            "verified_by_preflight": False,
            "scope": (
                "paper/build.py checks its transient main.log for undefined references "
                "and overfull horizontal boxes before replacing main.pdf. The log is "
                "not retained; PDF inspection does not establish those checks."
            ),
        },
        "visual_inspection": "Not established by this script; rendered pages are inspected separately.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "pdf-preflight.json",
                        help="Report destination; use a private path for read-only PDF checks.")
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, indent=2)
    args.output.write_text(text + "\n", encoding="utf8")
    print(text)


if __name__ == "__main__":
    main()
