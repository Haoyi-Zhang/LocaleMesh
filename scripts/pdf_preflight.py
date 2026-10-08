#!/usr/bin/env python3
"""Structural PDF checks for the anonymous and identified manuscript copies."""
from __future__ import annotations

import json
import re
from pathlib import Path

import fitz

PAPER = Path(__file__).resolve().parents[2] / "paper"
RESULTS = PAPER.parent / "artifact" / "results"


def inspect(name: str, *, anonymous: bool):
    pdf = PAPER / f"{name}.pdf"
    document = fitz.open(pdf)
    references = [
        number + 1
        for number, page in enumerate(document)
        if re.search(r"(?m)^References$", page.get_text())
    ]
    assert references == [9], (name, references)
    assert len(document) <= 12, (name, len(document))
    log = (PAPER / f"{name}.log").read_text(errors="replace")
    assert not re.search(r"Citation .* undefined|Reference .* undefined|There were undefined references|Overfull \\hbox", log)
    text = "\n".join(page.get_text() for page in document)
    assert "[?]" not in text
    if anonymous:
        assert "Haoyi Zhang" not in text and "Huaijin Ran" not in text and "Xunzhu Tang" not in text
        assert "Anonymous Author" in text
    else:
        for author in ("Haoyi Zhang", "Huaijin Ran", "Xunzhu Tang"):
            assert author in text
    return {
        "pages": len(document),
        "references_start_page": references[0],
        "main_pages": references[0] - 1,
        "words_per_page": [len(page.get_text().split()) for page in document],
        "anonymous": anonymous,
        "no_overfull_hboxes": True,
        "no_unresolved_references": True,
    }


report = {
    "anonymous_review": inspect("main", anonymous=True),
    "identified_author_copy": inspect("author-copy", anonymous=False),
    "visual_inspection": "Not established by this script; rendered pages are inspected separately.",
}
(RESULTS / "pdf-preflight.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
print(json.dumps(report, indent=2))
