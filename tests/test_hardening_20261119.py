"""Regression proofs for retraction-type coverage, the O(1) append gate and
full-text quote scanning beyond body paragraphs (abstracts, tables, figures)."""

from __future__ import annotations

import json

import httpx
import pytest

from literature_evidence_mcp import server
from literature_evidence_mcp.core import EvidenceLedger, ResearchClient

RETRACTION_KINDS = ["retraction", "withdrawal", "removed", "partial_retraction", "removal"]


@pytest.mark.parametrize(
    ("kind", "field", "expected"),
    [(kind, "updated-by", "RETRACTION_REPORTED") for kind in RETRACTION_KINDS]
    + [(kind, "update-to", "RETRACTION_NOTICE_REPORTED") for kind in RETRACTION_KINDS]
    + [(kind, "updated-by", "UPDATE_REPORTED")
       for kind in ("correction", "addendum", "expression_of_concern")],
)
async def test_update_type_status_mapping(kind, field, expected):
    def handler(request):
        return httpx.Response(200, json={"message": {
            "DOI": "10.1234/sample", "title": ["Study"],
            field: [{"type": kind, "DOI": "10.1234/other",
                     "updated": {"date-parts": [[2020, 1, 1]]}}]}})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        ResearchClient(http) as client,
    ):
        out = await client.retraction("10.1234/sample")
    assert out["status"] == expected


async def _seed_ledger(tmp_path, count):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    for index in range(count):
        await ledger.append("record", {"index": index})
    return ledger


def _rewrite_line(ledger, position, transform):
    lines = ledger.file.read_text(encoding="utf-8").splitlines()
    lines[position] = transform(lines[position])
    ledger.file.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def test_append_hashes_only_the_newest_link(tmp_path, monkeypatch):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    calls = {"count": 0}
    real_hash = EvidenceLedger._hash

    def counting_hash(entry):
        calls["count"] += 1
        return real_hash(entry)

    monkeypatch.setattr(EvidenceLedger, "_hash", staticmethod(counting_hash))
    for index in range(40):
        receipt = await ledger.append("record", {"index": index})
        assert receipt["entry_number"] == index + 1
    # The old gate re-hashed the whole chain per append (40*41/2 = 820 hashes).
    # The new gate hashes at most the two tail entries plus the new entry.
    assert calls["count"] <= 40 * 3
    check = ledger.verify()
    assert check["status"] == "VALID"
    assert check["count"] == 40


async def test_append_refuses_tampered_newest_entry(tmp_path):
    ledger = await _seed_ledger(tmp_path, 3)
    _rewrite_line(ledger, -1, lambda line: line.replace('"index": 2', '"index": 9'))
    with pytest.raises(ValueError, match="corrupt"):
        await ledger.append("record", {"index": 3})
    assert ledger.verify()["status"] == "TAMPER_DETECTED"


async def test_append_refuses_tampered_predecessor_of_newest_link(tmp_path):
    ledger = await _seed_ledger(tmp_path, 4)
    _rewrite_line(ledger, 2, lambda line: line.replace('"index": 2', '"index": 8'))
    with pytest.raises(ValueError, match="corrupt"):
        await ledger.append("record", {"index": 4})
    assert ledger.verify()["status"] == "TAMPER_DETECTED"


async def test_append_gate_leaves_older_tampering_to_full_verify(tmp_path):
    ledger = await _seed_ledger(tmp_path, 4)
    _rewrite_line(ledger, 0, lambda line: line.replace('"index": 0', '"index": 7'))
    # The newest link is intact, so the append gate records the entry; the
    # full-chain audit API remains responsible for older links.
    receipt = await ledger.append("record", {"index": 4})
    assert receipt["entry_number"] == 5
    check = ledger.verify()
    assert check["status"] == "TAMPER_DETECTED"
    assert check["line"] == 1


async def test_append_refuses_broken_link_with_valid_tail_hash(tmp_path):
    ledger = await _seed_ledger(tmp_path, 3)

    def break_link(line):
        record = json.loads(line)
        record["previous_hash"] = "0" * 64
        del record["entry_hash"]
        record["entry_hash"] = EvidenceLedger._hash(record)
        return json.dumps(record, sort_keys=True, ensure_ascii=False)

    _rewrite_line(ledger, -1, break_link)
    with pytest.raises(ValueError, match="corrupt"):
        await ledger.append("record", {"index": 3})


async def test_append_refuses_single_entry_with_broken_root_link(tmp_path):
    ledger = await _seed_ledger(tmp_path, 1)

    def break_root(line):
        record = json.loads(line)
        record["previous_hash"] = "f" * 64
        del record["entry_hash"]
        record["entry_hash"] = EvidenceLedger._hash(record)
        return json.dumps(record, sort_keys=True, ensure_ascii=False)

    _rewrite_line(ledger, 0, break_root)
    with pytest.raises(ValueError, match="corrupt"):
        await ledger.append("record", {"index": 1})


async def test_append_accepts_empty_file_and_rejects_corrupt_tail_variants(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.file.write_text("", encoding="utf-8")
    receipt = await ledger.append("record", {"index": 0})
    assert receipt["entry_number"] == 1
    valid = ledger.file.read_text(encoding="utf-8")
    for bad in ("bad json\n", '"just a string"\n', '{"kind": "x"}\n', "[1, 2]\n",
                valid + "\n"):
        ledger.file.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError, match="corrupt"):
            await ledger.append("record", {"index": 1})


async def test_append_refuses_unreadable_ledger(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.mkdir()  # a directory cannot be read as a ledger file
    ledger = EvidenceLedger(path)
    with pytest.raises(ValueError, match="corrupt"):
        await ledger.append("record", {"index": 0})


def test_verify_locked_guard_handles_absent_file(tmp_path):
    # verify() checks existence before locking; the inner guard still covers
    # the file disappearing between that check and lock acquisition.
    ledger = EvidenceLedger(tmp_path / "missing.jsonl")
    assert ledger._verify_locked() == {"status": "VALID_EMPTY", "count": 0, "head": "0" * 64}


FLOAT_XML = (
    b'<article><front><article-meta><title-group><article-title>Study</article-title>'
    b'</title-group><abstract><p>Background sentence in abstract.</p></abstract>'
    b'</article-meta></front>'
    b'<body><sec><title>Methods</title><p>Body paragraph one.</p></sec></body>'
    b'<back><table-wrap><label>Table 1</label><caption><p>Caption of table.</p></caption>'
    b'<table><tr><td>Cell value alpha</td>\n<td>Cell value beta</td></tr></table>'
    b'<table-wrap-foot><p>Footnote of table.</p></table-wrap-foot></table-wrap>'
    b'<fig><label>Figure 1</label><caption><p>Caption of figure.</p></caption></fig>'
    b'</back></article>'
)


def _xml_client(xml):
    return httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=xml)))


async def test_fulltext_scans_abstract_table_and_figure_caption():
    async with _xml_client(FLOAT_XML) as http, ResearchClient(http) as client:
        out = await client.fulltext("PMC100")
    pairs = [(span["section"], span["text"]) for span in out["spans"]]
    assert ("Abstract", "Background sentence in abstract.") in pairs
    assert ("Methods", "Body paragraph one.") in pairs
    assert ("Table 1", "Caption of table.") in pairs
    assert ("Table 1", "Footnote of table.") in pairs
    assert ("Table 1", "Cell value alpha Cell value beta") in pairs
    assert ("Figure 1", "Caption of figure.") in pairs
    assert out["paragraph_count"] == 6
    assert [span["span_id"] for span in out["spans"]] == [
        f"PMC100:p{index}" for index in range(1, 7)]
    assert out["truncated"] is False


async def test_source_quote_matches_abstract_table_and_figure_text():
    async with _xml_client(FLOAT_XML) as http, ResearchClient(http) as client:
        abstract = await client.source_quote("PMC100", "Background sentence in abstract")
        table = await client.source_quote("PMC100", "Cell value alpha")
        figure = await client.source_quote("PMC100", "Caption of figure")
    assert abstract["status"] == "TEXTUAL_MATCH_ONLY"
    assert abstract["matched_spans"][0]["section"] == "Abstract"
    assert abstract["matched_spans"][0]["span_id"] == "PMC100:p1"
    assert table["status"] == "TEXTUAL_MATCH_ONLY"
    assert table["matched_spans"][0]["section"] == "Table 1"
    assert figure["status"] == "TEXTUAL_MATCH_ONLY"
    assert figure["matched_spans"][0]["section"] == "Figure 1"


async def test_source_quote_max_chars_is_configurable():
    xml = (b'<article><body><sec><title>Results</title>'
           b'<p>The treatment was ineffective in this group.</p>'
           b'<p>A statistically significant change occurred for the other group.</p>'
           b'</sec></body></article>')
    async with _xml_client(xml) as http, ResearchClient(http) as client:
        full = await client.source_quote("PMC75", "statistically significant change")
        assert full["status"] == "TEXTUAL_MATCH_ONLY"
        tight = await client.source_quote(
            "PMC75", "statistically significant change", max_chars=55)
        assert tight["status"] == "NOT_VERIFIED_SOURCE_TRUNCATED"
        assert tight["retrieval_truncated"] is True
        for bad in (0, 30001, True, "500"):
            with pytest.raises(ValueError):
                await client.source_quote("PMC75", "some quote", max_chars=bad)


async def test_fulltext_floats_inside_body_are_not_double_counted():
    xml = (b'<article><body><sec><title>Results</title><p>Main text.</p>'
           b'<fig><label>Figure 2</label><caption><p>Inline figure caption.</p></caption></fig>'
           b'<table-wrap><caption><p>Inline table caption.</p></caption>'
           b'<table><tr><td>Inline cell</td></tr></table></table-wrap>'
           b'</sec></body></article>')
    async with _xml_client(xml) as http, ResearchClient(http) as client:
        out = await client.fulltext("PMC101")
    texts = [span["text"] for span in out["spans"]]
    assert texts == ["Main text.", "Inline figure caption.", "Inline table caption.",
                     "Inline cell"]
    assert texts.count("Inline figure caption.") == 1
    assert out["spans"][1]["section"] == "Results"
    assert out["spans"][3]["section"] == "Table"
    assert out["paragraph_count"] == 4


async def test_fulltext_float_labels_fall_back_when_missing_or_empty():
    xml = (b'<article><back>'
           b'<table-wrap><label>   </label><caption><p> </p></caption></table-wrap>'
           b'<table-wrap><table><tr><td>Only cell text</td></tr></table></table-wrap>'
           b'<fig><label></label><caption><p></p></caption></fig>'
           b'<fig><caption><p>Real figure caption.</p></caption></fig>'
           b'</back></article>')
    async with _xml_client(xml) as http, ResearchClient(http) as client:
        out = await client.fulltext("PMC102")
    pairs = [(span["section"], span["text"]) for span in out["spans"]]
    assert pairs == [("Table", "Only cell text"), ("Figure", "Real figure caption.")]


async def test_fulltext_abstract_inside_body_is_emitted_once():
    xml = (b'<article><body><abstract><p>Abstract inside body.</p></abstract>'
           b'<sec><title>S</title><p>Regular paragraph.</p></sec></body></article>')
    async with _xml_client(xml) as http, ResearchClient(http) as client:
        out = await client.fulltext("PMC103")
    pairs = [(span["section"], span["text"]) for span in out["spans"]]
    assert pairs == [("Abstract", "Abstract inside body."), ("S", "Regular paragraph.")]


async def test_server_verify_source_quote_forwards_max_chars(monkeypatch):
    seen = {}

    class Capturing:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def source_quote(self, pmcid, quote, max_chars=30000):
            seen["args"] = (pmcid, quote, max_chars)
            return {"status": "TEXTUAL_MATCH_ONLY"}

    monkeypatch.setattr(server, "ResearchClient", Capturing)
    out = await server.verify_source_quote("PMC9", "quoted text", max_chars=1234)
    assert seen["args"] == ("PMC9", "quoted text", 1234)
    assert out["status"] == "TEXTUAL_MATCH_ONLY"
    await server.verify_source_quote("PMC9", "quoted text")
    assert seen["args"][2] == 30000
