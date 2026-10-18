# SciFact full-corpus retrieval extension (limited known-positive gold)

This reproducible follow-up ranks **all 5,183 titles/abstracts** in the
SciFact official corpus for every DEV claim with known annotated evidence
(188 of 300). The previous SciFact experiment ranked **only cited candidate
documents** (339 pairs), an easier task. This extension does not alter the
scientific MCP and does not infer semantic SUPPORT or CONTRADICT.

Methods: independent \`rank-bm25==0.2.2\` BM25Okapi, explicit Jaccard and
claim-word-coverage lexical controls, and corpus-ID order control. All methods
see the same claim and the same full corpus. No DEV-gold fitting or threshold
selection. Macro known-positive recall@1/5/10/20, MRR and binary nDCG@10
are measured per claim with known evidence. A paired 500-sample fixed-seed
query bootstrap compares BM25 with Jaccard and word coverage.

**Critical annotation limitation:** Across 5,183 papers, SciFact does not
provide exhaustive negative relevance labels for every claim/document pair.
Unlabeled documents cannot be considered truly irrelevant. Consequently
precision, corpus false-positive rate and scientific false-proof rate
**cannot** be estimated from this snapshot. At the time of this benchmark there was no native MCP hypothesis-conditioned
retrieval tool. The separately added opt-in `bm25_rank_evidence` tool now
ranks **user-supplied** abstracts, but the archived full-corpus benchmark
measures the *independent reference implementation*, not an independently
validated product-wide result. This benchmark measures baseline
retrieval only, *not* verified scientific claim correctness.

Run after obtaining the same pinned SciFact data and hashes from
[the independent benchmark protocol](external_gold_evaluation.md):

\`\`\`bash
python -m pip install -r scripts/evaluation/requirements.txt
python -m scripts.evaluation.scifact_open_retrieval \
  --data /tmp/literature-gold/data \
  --output /tmp/scifact_open_retrieval.json
\`\`\`

CI validates original SciFact file SHA-256 hashes, executes the benchmark
on the externally retrieved dataset, tests ranking invariants, and preserves
the resulting aggregate JSON as a CI artifact. No original copyrighted
or licensed corpus contents are committed or uploaded.
