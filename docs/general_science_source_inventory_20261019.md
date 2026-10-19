# General-science source inventory — 2026-10-19

**Status: live metadata discovery completed; candidate quality, licensing, and expert gold NOT verified.** This is a sourcing inventory, not a benchmark, preregistered sample, or scientific result.

## Live discovery check

On 2026-10-19, the WSL environment made direct HTTPS requests to the OpenAlex Works API. Five exploratory searches used `search=<field> research`, a publication-date filter of 2026-10-01 through 2026-10-19, `per-page=3`, and metadata-only selected fields. API endpoint: <https://api.openalex.org/works>. Counts are the API's matching-record counts for those broad queries, **not** counts of eligible, peer-reviewed, licensed, or high-quality studies.

| Search query | API matching records | Metadata examples returned | Important limitation |
|---|---:|---|---|
| `physics research` | 14,807 | *From Research Goals to Scientific Closure: Evaluating Agents Through Evidence-Supported Physics Research* (2026-10-15; arXiv preprint) | Search can surface speculative or unrelated records; check the source and actual paper. |
| `chemistry research` | 14,556 | *Navigating and Evaluating High-Quality Qualitative Chemistry Education Research* (2026-10-16) | Broad search includes education and medicinal chemistry; not chemistry-topic stratification. |
| `mathematics research` | 24,032 | *Continual Graph Memory for Mathematical Research Agents* (2026-10-02; arXiv preprint) | Search also returned software and preliminary disclosures; quality review is required. |
| `computer science research` | 22,366 | *The Structure of Research Careers in Computer Science: A Multidimensional Analysis of Productivity, Persistence, and Collaboration* (2026-10-07; preprint) | Search includes bibliometrics and datasets, not just primary CS methods papers. |
| `earth science research` | 9,115 | Returned metadata included a journal paratext record | Clear false-positive risk; improve query/eligibility filters before sampling. |

These examples are API metadata only; no full texts, claims, evidence passages, or gold labels were collected. They demonstrate source reachability, **not** that the records are suitable candidates. No cross-disciplinary quotas or sample sizes were selected.

## Source families to evaluate

- **OpenAlex** (<https://openalex.org/>): broad cross-disciplinary scholarly metadata and identifiers. Its search counts are not relevance judgments; validate records against publisher/repository pages.
- **Crossref** (<https://www.crossref.org/>): DOI and publication metadata; a DOI is an identifier, not proof of quality or open-text reuse rights.
- **arXiv** (<https://arxiv.org/>): useful for physics, mathematics, computer science and related preprints. Treat version, category and preprint status explicitly; not all papers are peer reviewed.
- **Europe PMC / PubMed Central** (<https://europepmc.org/>; <https://pmc.ncbi.nlm.nih.gov/tools/openftlist/>): useful for biomedical records and open full text where licensing permits. These do not alone cover general science.
- **Zenodo** (<https://zenodo.org/>): research outputs and datasets; inspect record type, version and license per item.

Use source-specific APIs under their published terms and respect rate limits. Store only metadata required for provenance until the source license and eligibility are verified. Do not commit large corpora or copyrighted full text to Git.

## Expert recruitment channels

Potential channels, not confirmed recruits:

- <https://engage.cochrane.org/> — evidence-synthesis community; likely more relevant to health evidence than all science disciplines.
- <https://www.kolabtree.com/> — paid research/expert marketplace; scope, availability, cost and identity/credentials must be checked directly.
- Relevant scholarly societies, university departments, and authors' institutional contact pages — recruit by the discipline and claim type, verify qualifications and conflicts of interest, and use a written annotation protocol.

No expert was contacted, contracted, credential-verified, or asked to annotate in this run. Before outreach, approve compensation/budget, target disciplines, reviewer count per case, and adjudication procedure. Do not represent an interested volunteer as an independent qualified expert until credentials and conflicts are checked.

## Next blockers

1. Improve precision of source discovery and independently check record-level provenance and license.
2. Obtain approval for the sampling frame, discipline proportions, source genres, and primary outcomes.
3. Recruit and credential-check subject-matched experts; secure independent custody and blinding.
4. Collect new cases under the approved protocol, then run separate retrieval and evidence-assessment tracks. Public benchmark results remain exploratory and are not substitutes for this holdout.

**No scientific superiority claim is supported by this inventory.**
