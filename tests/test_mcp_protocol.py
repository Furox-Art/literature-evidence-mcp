"""In-process protocol regression; skipped only when SDK is absent in dev environment.
CI installs mcp and MUST execute this test.
"""
import pytest

pytest.importorskip("mcp")

from mcp.client import Client
from literature_evidence_mcp.server import mcp


@pytest.mark.asyncio
async def test_protocol_lists_and_executes_tools():
    async with Client(mcp) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert len(names) == 35
        assert {"nli_assess_challenger_evidence", "search_literature", "bm25_rank_evidence", "verify_source_quote", "verify_claim",
                "audit_methodology", "audit_pmc_methodology", "check_statistical_reporting",
                "export_evidence", "verify_evidence_ledger", "export_bibliography",
                "search_literature_extended", "expand_citation_chain"} <= names
        call = await client.call_tool("verify_claim", {
            "quote": "null result", "source_text": "The null result was retained.",
            "source_id": "test:direct"})
        assert not call.is_error
        assert call.content
