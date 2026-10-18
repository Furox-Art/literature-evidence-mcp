# Optional BM25 candidate evidence retrieval (30th MCP tool)

**Purpose:** Rank *only caller-supplied* titles and abstracts against a
hypothesis/query. This is a **lexical retrieval tool**, not a scientific
evidence-verification, entailment, RoB 2, GRADE or PRISMA decision engine.

## Installation

From the repository root:

\`\`\`bash
python -m pip install -e '.[retrieval]'
\`\`\`

The default Python package and other MCP tools do **not** require rank-bm25.
The TypeScript adapter discovers the Python tool automatically; no npm
Registry publication is involved. Without the retrieval extra, the endpoint
returns \`OPTIONAL_BM25_NOT_INSTALLED\` rather than pretending to rank anything.

## MCP call

Tool: \`bm25_rank_evidence\`

Arguments:

\`\`\`json
{
  "query": "neural signal decoding",
  "top_k": 5,
  "documents": [
    {"id": "10.1000/a", "title": "Neural signal decoding", "abstract": "A signal analysis study."},
    {"id": "10.1000/b", "title": "Cardiac measurements", "abstract": "An unrelated heart study."}
  ]
}
\`\`\`

Each document must have a unique string or integer \`id\`, a string \`title\`
and/or a string \`abstract\`. Limits: 1–10,000 candidate records; maximum
8 MB total text bytes; title at most 700 characters, abstract at most
20,000 characters, query 2–1,000 characters, and 1–50 returned results.
BM25 uses Unicode casefolded word tokens of at least two word characters.
It ranks only documents with at least one lexical query-term overlap.

The response exposes a model-specific BM25 score, source ID, truncated
300-character abstract preview, and SHA-256 of the caller-supplied
title/abstract. Matching scores are not probabilities or calibrated evidence
confidence. Ties are deterministic (lexicographic ID). No original text is
persisted, no network is accessed, and no source is authenticated.

## Scientific restrictions

* A rank is **not** a scientific SUPPORT/CONTRADICT judgment.
* A SHA-256 is a fingerprint of *supplied* text, not publisher provenance.
* No risk of bias, study eligibility, statistics, retraction or GRADE judgments
  are inferred from lexical overlap.
* If no query term overlaps, return \`NO_QUERY_TERM_OVERLAP\` with no hits.
* Multiword semantics, synonyms, negation and domain context require separate
  independent evaluation.
* This endpoint is **opt-in**; existing \`search_literature\`,
  \`verify_claim\` and all other scientific tools retain their behavior.
* It cannot fetch SciFact itself; an external caller supplies the corpus.

## Reproducible verification

The frozen SciFact **independent BM25 reference benchmark** ranked 5,183
titles/abstracts and measured 92.64% known-positive Recall@10 on 188
positive-labeled development claims. That is NOT full semantic correctness,
corpus precision, product-wide performance or official SciFact leaderboard
accuracy. See [the full-corpus benchmark](scifact_full_corpus.md).

A dedicated GitHub CI check now compares this MCP endpoint's top-10 document
IDs to a separately assembled reference BM25 ranking over the same 5,183
SciFact papers on six predetermined labeled development queries. Input hashes
are checked first. This is an **interface parity test**, not independent
scientific accuracy calibration.

Run the usual Python suite with the optional feature installed:

\`\`\`bash
python -m pip install -e '.[dev,retrieval]'
pytest -q --cov=literature_evidence_mcp --cov-branch --cov-fail-under=100
\`\`\`
