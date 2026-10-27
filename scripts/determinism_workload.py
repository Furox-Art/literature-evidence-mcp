"""Deterministic literature-evidence workload sampled by the determinism matrix."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _rounded(value: Any) -> Any:
    """Round floats recursively so compiler-level noise cannot fail the matrix gate."""
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    return value


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_dir = repo_root / "src"
    if source_dir.is_dir():
        sys.path.insert(0, str(source_dir))

    from literature_evidence_mcp.bibliography import export_bibliography_records
    from literature_evidence_mcp.core import (
        compare_metadata,
        evidence_graph,
        normalize_doi,
        screen_methodology,
        verify_quote,
    )
    from literature_evidence_mcp.methodology import audit_statistical_fields
    from literature_evidence_mcp.native import (
        cpp_fixed_effect_meta_analysis,
        cpp_random_effects_meta,
    )
    from literature_evidence_mcp.prisma import dual_screen

    papers = [
        {
            "title": "Effects of A & B_1 in {cells} \\ input",
            "authors": ["Ada Lovelace", "Rene D'Arcy"],
            "year": 2024,
            "journal": "J. Synthetic Methods",
            "doi": "https://doi.org/10.1234/TEST.42",
            "metadata_disagreements": [
                {"field": "title", "status": "REVIEW_REQUIRED_NOT_RESOLVED"}
            ],
        },
        {
            "title": "Untitled trial record",
            "authors": ["Grace Hopper"],
            "year": 2023,
            "doi": "doi:10.5555/ABC.7",
        },
    ]
    source_text = (
        "Participants were randomly assigned in a double-blind design. "
        "A power analysis fixed the sample size, and the trial was preregistered. "
        "We report a 95% CI and apply Bonferroni correction for multiple testing."
    )
    meta_studies = [
        {"estimate": 0.85, "standard_error": 0.12},
        {"estimate": -0.4, "standard_error": 0.25},
        {"estimate": 0.3, "standard_error": 0.18},
        {"estimate": 1.2, "standard_error": 0.3},
        {"estimate": 0.05, "standard_error": 0.2},
    ]
    payload: dict[str, Any] = {
        "dois": [
            normalize_doi(value)
            for value in (
                "https://doi.org/10.1234/TEST.42",
                "doi:10.5555/ABC.7",
                " 10.1000/xYz ",
            )
        ],
        "quote": verify_quote(
            "randomly assigned in a double-blind design",
            source_text,
            "lit-src-1",
        ),
        "methodology": screen_methodology(source_text, "lit-src-2"),
        "metadata": compare_metadata(papers),
        "graph": evidence_graph(
            [{"id": "a", "label": "claim"}, {"id": "b", "label": "study"}],
            [{"source": "a", "target": "b", "evidence_id": "ev-1"}],
        ),
        "prisma": dual_screen(
            [
                {
                    "record_id": "r1",
                    "reviewers": [
                        {"reviewer_id": "rev-1", "decision": "include"},
                        {"reviewer_id": "rev-2", "decision": "include"},
                    ],
                },
                {
                    "record_id": "r2",
                    "reviewers": [
                        {
                            "reviewer_id": "rev-1",
                            "decision": "exclude",
                            "reason": "no primary data",
                        },
                        {
                            "reviewer_id": "rev-2",
                            "decision": "exclude",
                            "reason": "no primary data",
                        },
                    ],
                },
                {
                    "record_id": "r3",
                    "reviewers": [
                        {"reviewer_id": "rev-1", "decision": "include"},
                        {
                            "reviewer_id": "rev-2",
                            "decision": "exclude",
                            "reason": "wrong population",
                        },
                    ],
                },
            ]
        ),
        "bibliography": {
            fmt: export_bibliography_records(papers, fmt) for fmt in ("bibtex", "ris", "csl-json")
        },
        "statistics": audit_statistical_fields(
            [
                {"p_value": 1.4, "sample_size": 0, "ci_lower": 0.8, "ci_upper": 0.2},
                {
                    "p_value": 0.01,
                    "sample_size": 120,
                    "ci_lower": 0.2,
                    "ci_upper": 0.8,
                    "estimate": 0.5,
                },
            ]
        ),
        "meta": {
            "fixed": _rounded(cpp_fixed_effect_meta_analysis(meta_studies)),
            "random": _rounded(cpp_random_effects_meta(meta_studies, leave_one_out=True)),
        },
    }
    if not payload["quote"]["text_match"] or payload["prisma"]["included_records"] != 1:
        raise SystemExit("workload produced unverifiable results; it is vacuous")
    if payload["meta"]["fixed"]["status"] != "NUMERICAL_CALCULATION_ONLY":
        if os.environ.get("DETERMINISM_REQUIRE_NATIVE") == "1":
            raise SystemExit(
                "native C++ meta module is required but not installed; build native/cpp_meta"
            )
    elif len(payload["meta"]["random"]["leave_one_out"]) != len(meta_studies):
        raise SystemExit("leave-one-out did not cover every study; the workload is vacuous")
    artifact_dir = os.environ.get("DETERMINISM_ARTIFACT_DIR")
    if artifact_dir:
        Path(artifact_dir, "payload.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
