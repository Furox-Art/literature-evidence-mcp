"""Safe bibliographic metadata export; NEVER scientific evidence verification.

Converts caller-supplied search/paper records to BibTeX or RIS without looking
up publications, silently deduplicating DOI-less works or masking conflicts.
"""
from __future__ import annotations

import json
import re
import unicodedata

from literature_evidence_mcp.core import normalize_doi

_REPLACEMENTS = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def _text(value: object, name: str, limit: int, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    # No newlines/control characters that could inject RIS field delimiters.
    clean = " ".join("".join(
        char if not unicodedata.category(char).startswith("C") else " "
        for char in value
    ).split())
    if len(clean) > limit or (required and not clean):
        raise ValueError(f"{name} missing or longer than {limit} characters")
    return clean


def _bib(value: str) -> str:
    return "".join(_REPLACEMENTS.get(char, char) for char in value)


def _year(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError("year must be four decimal digits")
    string = str(value)
    if not re.fullmatch(r"[0-9]{4}", string) or not 1000 <= int(string) <= 2100:
        raise ValueError("year must be a four-digit calendar year")
    return string


def _record(paper: dict, ordinal: int) -> tuple[str, str, dict, dict]:
    if not isinstance(paper, dict):
        raise TypeError("Each paper must be a metadata dictionary")
    title = _text(paper.get("title"), "title", 1200, required=True)
    journal = _text(paper.get("journal"), "journal", 400)
    year = _year(paper.get("year"))
    raw_authors = paper.get("authors")
    if raw_authors is None:
        raw_authors = []
    if not isinstance(raw_authors, list) or len(raw_authors) > 40:
        raise TypeError("authors must be a list of at most 40 names")
    authors = [_text(a, "author", 250, required=True) for a in raw_authors]
    raw_doi = paper.get("doi")
    doi = ""
    doi_status = "MISSING"
    if raw_doi is not None:
        if not isinstance(raw_doi, str):
            raise TypeError("doi must be text or null")
        if raw_doi.strip():
            try:
                doi = normalize_doi(raw_doi)
            except ValueError:
                doi_status = "INVALID_DOI_OMITTED"
            else:
                doi_status = "SYNTAX_VALID_NOT_RESOLVED"
    conflicts = paper.get("metadata_disagreements", [])
    if not isinstance(conflicts, list):
        raise TypeError("metadata_disagreements must be a list")
    # For DOI-less entries, a unique sequence key never pretends titles match.
    citekey = f"lem{ordinal}"
    entry_type = "article" if journal else "misc"
    bibfields = [
        ("title", title), ("author", " and ".join(_bib(a) for a in authors)),
        ("journal", journal), ("year", year), ("doi", doi),
    ]
    lines = [f"@{entry_type}{{{citekey},"]
    for field, value in bibfields:
        if value:
            content = value if field == "author" else _bib(value)
            lines.append(f"  {field} = {{{content}}},")
    lines.append("}")
    bibtex = "\n".join(lines)
    ris = ["TY  - JOUR" if journal else "TY  - GEN", f"TI  - {title}"]
    ris.extend(f"AU  - {author}" for author in authors)
    if journal:
        ris.append(f"JO  - {journal}")
    if year:
        ris.append(f"PY  - {year}")
    if doi:
        ris.append(f"DO  - {doi}")
    ris.extend(["ER  - ", ""])
    csl = {"id": citekey, "type": "article-journal" if journal else "document",
           "title": title}
    if authors:
        csl["author"] = [{"literal": author} for author in authors]
    if journal:
        csl["container-title"] = journal
    if year:
        csl["issued"] = {"date-parts": [[int(year)]]}
    if doi:
        csl["DOI"] = doi
    audit = {
        "key": citekey,
        "doi_status": doi_status,
        "metadata_conflicts_present": bool(conflicts),
        "fields_exported": [
            field for field, value in (("title", title), ("authors", authors),
                                       ("journal", journal), ("year", year), ("doi", doi))
            if value
        ],
        "source_status": "CALLER_SUPPLIED_UNVERIFIED_METADATA",
    }
    return bibtex, "\n".join(ris), csl, audit


def export_bibliography_records(papers: list[dict], output_format: str = "bibtex") -> dict:
    """Offline deterministic BibTeX/RIS/CSL-JSON; validates metadata and preserves conflict alerts."""
    if output_format not in {"bibtex", "ris", "csl-json"}:
        raise ValueError("output_format must be bibtex, ris or csl-json")
    if not isinstance(papers, list) or not 1 <= len(papers) <= 100:
        raise ValueError("papers must contain 1-100 supplied metadata records")
    entries = [_record(paper, i) for i, paper in enumerate(papers, start=1)]
    if output_format == "csl-json":
        content = json.dumps([entry[2] for entry in entries], ensure_ascii=False,
                             sort_keys=True, indent=2)
    else:
        formatted = [entry[0 if output_format == "bibtex" else 1] for entry in entries]
        content = "\n\n".join(formatted) if output_format == "bibtex" else "\n".join(formatted)
    return {
        "format": output_format,
        "record_count": len(entries),
        "content": content,
        "records": [entry[3] for entry in entries],
        "status": "BIBLIOGRAPHY_FROM_UNVERIFIED_METADATA_NOT_SCIENTIFIC_EVIDENCE",
        "scientific_claim_verified": False,
        "doi_resolved": False,
        "notice": (
            "Export formats metadata only; no external DOI resolution, publisher validation, "
            "deduplication, study-quality review or scientific claim verification."
        ),
    }
