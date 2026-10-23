import pytest

from literature_evidence_mcp import graph_audit, server


class FakeResearch:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        return None
    async def retraction(self, doi):
        if doi.endswith("/a"):
            return {"status": "RETRACTION_REPORTED", "updated_by": [
                {"type": "retraction"}, {"type": "correction"},
                {"type": "unrecognized"}]}
        if doi.endswith("/b"):
            return {"status": "NOT_VERIFIED", "updated_by": []}
        return {"status": "NO_UPDATE_IN_CHECKED_METADATA", "updated_by": [
            {"type": "expression-of-concern"}, {"type": "erratum"}]}


@pytest.mark.asyncio
async def test_crossref_source_updates_flag_descendants_not_auto_retract(monkeypatch):
    monkeypatch.setattr("literature_evidence_mcp.core.ResearchClient", FakeResearch)
    out = await server.crossref_update_alerts(
        ["10.1000/a", "10.1000/b", "10.1000/c"],
        [{"cited_id": "10.1000/a", "citing_id": "10.1000/b",
          "source_id": "crossref:cited_by"}])
    assert out["status"] == "CROSSREF_NOTICE_METADATA_WITH_UNVERIFIED_GRAPH_LINKS"
    assert out["unverified_dois"] == ["10.1000/b"]
    assert any(v["paper_id"] == "10.1000/b" and
               v["status"] == "CITING_PAPER_REVIEW_ALERT_ONLY" for v in out["alerts"])
    assert any(v["notice_kind"] == "expression_of_concern" for v in out["alerts"])


@pytest.mark.asyncio
@pytest.mark.parametrize("dois", [[], ["not_a_doi"], ["10.1000/a"] * 2, None])
async def test_crossref_rejects_invalid_requests(dois):
    with pytest.raises((TypeError, ValueError)):
        await graph_audit.crossref_notice_chain(dois, [])
