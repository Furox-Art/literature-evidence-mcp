"""Bibliography interoperability: deterministic, injection-safe, non-authoritative."""
from __future__ import annotations

import json

import pytest

from literature_evidence_mcp.bibliography import export_bibliography_records
from literature_evidence_mcp.server import export_bibliography


def sample(**updates):
    row = {
        "title": "Effects of A & B_1 in {cells} \\\\ input",
        "authors": ["Ada Lovelace", "René D'Arcy"],
        "year": 2024,
        "journal": "J. Synthetic Methods",
        "doi": "https://doi.org/10.1234/TEST.42",
        "metadata_disagreements": [{"field": "title", "status": "REVIEW_REQUIRED_NOT_RESOLVED"}],
    }
    row.update(updates)
    return row


def test_bibtex_safely_escapes_untrusted_metadata():
    x = export_bibliography_records([sample()])
    assert x["format"] == "bibtex" and x["record_count"] == 1
    assert "@article{lem1," in x["content"]
    assert r"A \& B\_1" in x["content"]
    assert r"\{cells\}" in x["content"]
    assert r"\textbackslash{}" in x["content"]
    assert "author = {Ada Lovelace and René D'Arcy}" in x["content"]
    assert "doi = {10.1234/test.42}" in x["content"]
    assert x["records"][0]["doi_status"] == "SYNTAX_VALID_NOT_RESOLVED"
    assert x["records"][0]["metadata_conflicts_present"] is True
    assert x["scientific_claim_verified"] is False and x["doi_resolved"] is False
    assert "UNVERIFIED" in x["status"]


def test_ris_cannot_inject_new_field_line():
    x = export_bibliography([sample(
        title="A trial\r\nER  - \nTY  - BAD\tcontrol",
        authors=["Smith\nAU  - Injected", "Another"],
        journal="Clinical\nER  - Fake",
    )], "ris")
    s = x["content"]
    assert "TI  - A trial ER - TY - BAD control" in s
    assert "AU  - Smith AU - Injected" in s
    assert "JO  - Clinical ER - Fake" in s
    assert s.count("\nTY  - ") == 0
    assert s.count("\nER  - ") == 1
    assert s.count("\nAU  - ") == 2
    assert x["format"] == "ris"


def test_missing_and_invalid_doi_never_become_verified_or_exported():
    output = export_bibliography_records([
        sample(doi=None, journal=None, year=None, authors=None,
               metadata_disagreements=[]),
        sample(title="Other work", doi="not a valid doi", authors=[]),
        sample(title="Third work", doi=""),
    ])
    assert output["record_count"] == 3
    assert "@misc{lem1," in output["content"]
    assert "@article{lem2," in output["content"]
    assert output["content"].count("  doi =") == 0
    assert [r["doi_status"] for r in output["records"]] == [
        "MISSING", "INVALID_DOI_OMITTED", "MISSING"
    ]
    assert output["records"][0]["metadata_conflicts_present"] is False
    assert output["records"][0]["fields_exported"] == ["title"]
    assert "lem1" in output["content"] and "lem2" in output["content"]


@pytest.mark.parametrize("payload,format,exception", [
    ([], "bibtex", ValueError),
    ([sample()] * 101, "bibtex", ValueError),
    ({}, "bibtex", ValueError),
    ([sample()], "html", ValueError),
    ([None], "bibtex", TypeError),
    ([sample(title=None)], "bibtex", TypeError),
    ([sample(title=123)], "bibtex", TypeError),
    ([sample(title="x" * 1201)], "bibtex", ValueError),
    ([sample(journal=321)], "ris", TypeError),
    ([sample(year=True)], "ris", TypeError),
    ([sample(year=202400)], "ris", ValueError),
    ([sample(year="20A4")], "ris", ValueError),
    ([sample(year=900)], "ris", ValueError),
    ([sample(year=2101)], "ris", ValueError),
    ([sample(authors="Ada")], "bibtex", TypeError),
    ([sample(authors=["x"] * 41)], "bibtex", TypeError),
    ([sample(authors=[123])], "bibtex", TypeError),
    ([sample(authors=[""])], "bibtex", ValueError),
    ([sample(doi=123)], "bibtex", TypeError),
    ([sample(metadata_disagreements="bad")], "bibtex", TypeError),
])
def test_fail_closed_bad_structures(payload, format, exception):
    with pytest.raises(exception):
        export_bibliography_records(payload, format)


def test_old_and_unicode_works_no_doi_not_silently_deduplicated():
    x = export_bibliography_records([
        {"title": "Matched title", "year": "1800", "authors": [],
         "journal": "", "doi": None},
        {"title": "Matched title", "year": "", "authors": ["Dr X"],
         "doi": None},
    ], "ris")
    assert x["record_count"] == 2
    assert x["content"].count("TY  - GEN") == 2
    assert x["content"].count("TI  - Matched title") == 2
    assert "PY  - 1800" in x["content"]
    assert [r["key"] for r in x["records"]] == ["lem1", "lem2"]


def test_special_character_roundtrip_and_ris_no_newlines():
    row = sample(title="Alpha #$% & _ ~ ^ { } \\ test",
                 authors=["A#B%"], journal="")
    output = export_bibliography_records([row])
    for token in [r"\#", r"\$", r"\%", r"\&", r"\_",
                  r"\textasciitilde{}", r"\textasciicircum{}", r"\{", r"\}"]:
        assert token in output["content"]
    assert "@misc{" in output["content"]


@pytest.mark.asyncio
async def test_mcp_v2_tool_roundtrip():
    from mcp.client import Client

    from literature_evidence_mcp.server import mcp
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "export_bibliography" in {t.name for t in tools.tools}
        result = await client.call_tool("export_bibliography", {
            "papers": [{"title": "Sample study", "year": 2025,
                        "doi": "10.9999/demo"}],
            "output_format": "ris",
        })
        assert not result.is_error and result.content


def test_csl_json_importable_without_unsupported_identity_claims():
    result = export_bibliography_records([
        sample(),
        sample(title="DOI-less data", doi="invalid", authors=[], year=None,
               journal=None, metadata_disagreements=[]),
    ], "csl-json")
    entries = json.loads(result["content"])
    assert result["format"] == "csl-json" and len(entries) == 2
    assert entries[0]["type"] == "article-journal"
    assert entries[0]["author"] == [{"literal": "Ada Lovelace"},
                                    {"literal": "René D'Arcy"}]
    assert entries[0]["issued"] == {"date-parts": [[2024]]}
    assert entries[0]["DOI"] == "10.1234/test.42"
    assert entries[0]["container-title"] == "J. Synthetic Methods"
    assert entries[1] == {"id": "lem2", "type": "document",
                          "title": "DOI-less data"}
    assert result["records"][1]["doi_status"] == "INVALID_DOI_OMITTED"
    assert result["doi_resolved"] is False
