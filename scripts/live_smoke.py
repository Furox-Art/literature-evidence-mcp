"""Opt-in live provider smoke test. No persistence. Network use/quotas apply.

Run: python scripts/live_smoke.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from literature_evidence_mcp.core import ResearchClient


async def main():
    async with ResearchClient() as client:
        search = await client.search("human working memory", limit=1)
        assert all(s["status"] == "OK" for s in search["provider_status"].values()), search["provider_status"]
        assert search["papers"], "At least one bibliographic search result expected"
        paper = await client.paper("10.1038/nature12373")
        assert paper["paper"]["doi"] == "10.1038/nature12373"
        retraction = await client.retraction("10.1038/nature12373")
        assert retraction["status"] != "NOT_VERIFIED"
    print(json.dumps({"status": "PASS", "sources": list(search["provider_status"]),
                      "result_count": len(search["papers"]),
                      "citation_status": paper["status"],
                      "retraction_metadata_status": retraction["status"],
                      "scientific_conclusions_verified": False}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
