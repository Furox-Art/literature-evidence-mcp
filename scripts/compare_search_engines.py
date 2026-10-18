"""Opt-in same-query competitor search smoke; NOT gold-labeled relevance testing.

Install each project in a separate venv, run once per engine:
    python scripts/compare_search_engines.py own > /tmp/own.json
    python scripts/compare_search_engines.py athenaeum > /tmp/athenaeum.json
    python scripts/compare_search_engines.py paper_search > /tmp/paper_search.json

All engines use the same three public providers and top-k 5 per provider.
Do not call returned-record volume a relevance/quality score.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

QUERIES = [
    "cortical predictive processing",
    "randomized controlled trial childhood anxiety",
    "quantum entanglement bell inequalities",
]
PROVIDERS = ["openalex", "crossref", "europepmc"]


async def one(engine: str, query: str) -> dict:
    start = time.monotonic()
    doi: set[str] = set()
    count = 0
    source_errors: dict = {}
    try:
        if engine == "own":
            from literature_evidence_mcp.core import ResearchClient
            async with ResearchClient() as client:
                result = await client.search(query, 5)
            count = len(result["papers"])
            doi = {p["doi"] for p in result["papers"] if p.get("doi")}
            source_errors = {k: v for k, v in result["provider_status"].items()
                             if v["status"] != "OK"}
        elif engine == "athenaeum":
            from athenaeum_mcp.service import meta_search
            works = await meta_search(query, limit=15, providers=PROVIDERS)
            count = len(works)
            doi = {w.doi.lower() for w in works if w.doi}
            source_errors = {"warning": "athenaeum meta_search suppresses provider exceptions"}
        elif engine == "paper_search":
            from paper_search_mcp.server import search_papers
            result = await search_papers(
                query, max_results_per_source=5,
                sources="openalex,crossref,europepmc",
            )
            count = len(result.get("papers", []))
            doi = {str(x["doi"]).lower() for x in result.get("papers", [])
                   if isinstance(x, dict) and x.get("doi")}
            source_errors = result.get("errors", {})
        else:
            raise ValueError("unknown engine")
        status = "OK"
    except Exception as e:  # noqa: BLE001 - competitor errors must be reported, not swallowed
        status = "ERROR"
        source_errors = {"fatal": f"{type(e).__name__}: {str(e)[:140]}"}
    return {"query": query, "status": status, "seconds": round(time.monotonic() - start, 3),
            "deduped_record_count": count, "doi_count": len(doi),
            "dois": sorted(doi), "errors": source_errors}


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("engine", choices=("own", "athenaeum", "paper_search"))
    args = p.parse_args()
    results = []
    for query in QUERIES:
        results.append(await one(args.engine, query))
    print(json.dumps({
        "engine": args.engine,
        "query_set": "non-expert-labeled shared-query smoke",
        "providers": PROVIDERS, "per_provider_limit": 5,
        "results": results,
        "not_evaluated": ["precision", "recall", "claim_accuracy", "risk_of_bias_accuracy",
                          "statistical_significance", "robust latency ranking"],
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
