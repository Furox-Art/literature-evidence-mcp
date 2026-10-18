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
        assert len(names) == 14
        assert {"search_literature", "verify_source_quote", "verify_claim",
                "export_evidence", "verify_evidence_ledger"} <= names
        call = await client.call_tool("verify_claim", {
            "quote": "null result", "source_text": "The null result was retained.",
            "source_id": "test:direct"})
        assert not call.is_error
        assert call.content
