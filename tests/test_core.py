import httpx
import pytest

from literature_evidence_mcp.core import (
    CROSSREF,
    OPENALEX,
    EvidenceLedger,
    ProviderError,
    ResearchClient,
    _as_paper,
    _update_rows,
    compare_metadata,
    evidence_graph,
    normalize_doi,
    screen_methodology,
    verify_quote,
)


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("doi:10.1186/xyz-1") == "10.1186/xyz-1"
    for value in ["not a doi", "10.1000/a?x=1", "https://evil.com/10.1000/a", "10.1000/a\\b"]:
        with pytest.raises(ValueError):
            normalize_doi(value)


def test_abstract_reconstruction():
    paper = _as_paper({"id": "https://openalex.org/W123", "doi": "https://doi.org/10.1000/a",
                       "abstract_inverted_index": {"world": [1], "Hello": [0]},
                       "display_name": "Title", "publication_year": 2024}, "openalex")
    assert paper["abstract"] == "Hello world"


def test_claim_quote_never_scientific_verdict():
    yes = verify_quote("Randomized trial", "A RANDOMIZED   trial used 14 patients.", "x")
    assert yes["status"] == "TEXTUAL_MATCH_ONLY"
    assert yes["scientific_claim_verified"] is False
    assert verify_quote("placebo", "Randomized trial", "x")["status"] == "NOT_VERIFIED"
    with pytest.raises(ValueError):
        verify_quote("", "text", "x")


def test_methodology_screening_protects_against_overclaim():
    out = screen_methodology("We reported a power analysis and 95% CI.", "abc")
    assert out["features"]["power_analysis"]["status"] == "TERM_MENTIONED"
    assert out["features"]["blinding"]["status"] == "NOT_ASSESSED"
    assert out["scientific_quality_assessed"] is False


def test_evidence_graph_never_infers_edges():
    nodes = [{"id": "a"}, {"id": "b"}]
    with pytest.raises(ValueError):
        evidence_graph(nodes, [{"source": "a", "target": "b"}])
    graph = evidence_graph(nodes, [{"source": "a", "target": "b", "evidence_id": "doi:10.1/test"}])
    assert graph["status"].endswith("UNVERIFIED")
    with pytest.raises(ValueError):
        evidence_graph([{"id": "a"}, {"id": "a"}], [])


def test_compare_metadata():
    assert compare_metadata([{"doi": "a"}, {"doi": "b"}])["conflict_verdict"] == "NOT_VERIFIED"
    with pytest.raises(ValueError):
        compare_metadata([{"doi": "a"}])


@pytest.mark.asyncio
async def test_search_dedupe_and_errors():
    def handler(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": [{"id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/test", "display_name": "Experiment", "publication_year": 2025}]})
        if request.url.host == "www.ebi.ac.uk":
            return httpx.Response(503)
        return httpx.Response(200, json={"message": {"items": [{"DOI": "10.1000/test",
            "title": ["Experiment"], "published": {"date-parts": [[2025]]}}]}})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        ResearchClient(http) as client,
    ):
        out = await client.search("consciousness", 4)
    assert len(out["papers"]) == 1
    assert set(out["papers"][0]["sources"]) == {"openalex", "crossref"}
    assert out["provider_status"]["europepmc"]["status"] == "ERROR"
    assert out["coverage"] == "NON_EXHAUSTIVE"


@pytest.mark.asyncio
async def test_crossref_retraction_and_absence():
    def handler(request):
        suffix = str(request.url).lower()
        if "notice" in suffix:
            return httpx.Response(200, json={"message": {"DOI": "10.1234/notice",
                "title": ["Retraction notice"], "update-to": [
                    {"type": "retraction", "DOI": "10.1234/retracted",
                     "updated": {"date-parts": [[2010, 2, 2]]}}]}})
        update = ([{"type": "retraction", "DOI": "10.1234/notice",
                    "source": "retraction-watch"}]
                  if "retracted" in suffix else [])
        return httpx.Response(200, json={"message": {"DOI": "10.1234/sample",
            "title": ["Study"], "updated-by": update}})
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        ResearchClient(http) as client,
    ):
        retracted = await client.retraction("10.1234/retracted")
        assert retracted["status"] == "RETRACTION_REPORTED"
        assert retracted["updated_by"][0]["type"] == "retraction"
        assert retracted["updates"] == []
        notice = await client.retraction("10.1234/notice")
        assert notice["status"] == "RETRACTION_NOTICE_REPORTED"
        assert notice["updates"][0]["date"] == [[2010, 2, 2]]
        assert notice["updated_by"] == []
        assert (await client.retraction("10.1234/clear"))["status"] == "NO_UPDATE_IN_CHECKED_METADATA"


@pytest.mark.parametrize("value", [None, "retraction", 7, [None, "x", 5]])
def test_malformed_update_relations_are_ignored(value):
    assert _update_rows(value) == []


def test_update_relation_without_date_or_type_is_normalized():
    assert _update_rows([{"DOI": "10.1000/x", "updated": "not-an-object"}]) == [
        {"type": "", "doi": "10.1000/x", "source": None, "date": None}]


@pytest.mark.asyncio
async def test_crossref_not_found_returns_unverified():
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as http,
        ResearchClient(http) as client,
    ):
        assert (await client.retraction("10.1234/nope"))["status"] == "NOT_VERIFIED"
        with pytest.raises(ProviderError):
            await client.paper("10.1234/nope")


@pytest.mark.asyncio
async def test_fixed_hosts_and_routes():
    async with (
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))) as http,
        ResearchClient(http) as client,
    ):
        for base, path in [("http://169.254.169.254", "/works"),
                           (CROSSREF, "//evil.com/works"),
                           (CROSSREF, "/evil"),
                           (OPENALEX, "/works/../secrets")]:
            with pytest.raises(ValueError):
                await client._get(base, path)


@pytest.mark.asyncio
async def test_ledger_chain_integrity_and_tampering(tmp_path):
    p = tmp_path / "log.jsonl"
    ledger = EvidenceLedger(p)
    assert ledger.verify()["status"] == "VALID_EMPTY"
    await ledger.append("paper", {"doi": "10.1000/x"})
    await ledger.append("review_search", {"query": "q"})
    assert ledger.verify()["count"] == 2
    text = p.read_text()
    p.write_text(text.replace("10.1000/x", "10.1000/y"))
    assert ledger.verify()["status"] == "TAMPER_DETECTED"
    with pytest.raises(ValueError):
        await ledger.append("paper", {"doi": "new"})


@pytest.mark.asyncio
async def test_ledger_rejects_unsafe_inputs(tmp_path):
    ledger = EvidenceLedger(tmp_path / "log.jsonl")
    for kind in ["../bad", "X", "UPPER"]:
        with pytest.raises(ValueError):
            await ledger.append(kind, {})
    with pytest.raises(ValueError):
        await ledger.append("paper", {"large": "X" * 100_001})

@pytest.mark.asyncio
async def test_fulltext_xml_with_provenance():
    xml = b'''<?xml version="1.0"?>
    <article><front><article-meta><title-group><article-title>Measured result</article-title>
    </title-group></article-meta></front><body><sec><title>Methods</title>
    <p>Three measurements.</p></sec><sec><title>Results</title><p>Null result.</p></sec>
    </body></article>'''
    def handler(request):
        return httpx.Response(200, content=xml)
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http,
        ResearchClient(http) as client,
    ):
        out = await client.fulltext("PMC12345")
        assert "Null result" in out["content"]
        assert out["title"] == "Measured result"
        assert len(out["sha256_xml"]) == 64
        assert out["truncated"] is False
        with pytest.raises(ValueError):
            await client.fulltext("http://evil.test/")


@pytest.mark.asyncio
async def test_fulltext_rejects_entity_expansion():
    xml = b'''<!DOCTYPE x [<!ENTITY attack "exfil">]><article><body>
    <sec><p>&attack;</p></sec></body></article>'''
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=xml))) as http, ResearchClient(http) as client:
        import defusedxml.common
        with pytest.raises(defusedxml.common.EntitiesForbidden):
            await client.fulltext("PMC12345")
