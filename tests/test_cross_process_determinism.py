"""Cross-process determinism: bibliographic export must be byte-stable.

The same supplied metadata is exported to BibTeX, RIS and CSL-JSON in two
fresh interpreters with different ``PYTHONHASHSEED`` values. Ordering derived
from dict/set iteration would change citations or conflict notices between
runs, which must never happen for an offline export.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root / "src"))

from literature_evidence_mcp.bibliography import export_bibliography_records

papers = [
    {
        "title": "Effects of A & B_1 in {cells} \\ input",
        "authors": ["Ada Lovelace", "René D'Arcy"],
        "year": 2024,
        "journal": "J. Synthetic Methods",
        "doi": "https://doi.org/10.1234/TEST.42",
        "metadata_disagreements": [
            {"field": "title", "status": "REVIEW_REQUIRED_NOT_RESOLVED"},
            {"field": "year", "status": "REVIEW_REQUIRED_NOT_RESOLVED"},
        ],
    },
    {
        "title": "A second supplied record",
        "authors": ["Grace Hopper", "Edsger Dijkstra"],
        "year": 2025,
        "journal": "Annals of Deterministic Export",
        "doi": "10.5678/second.1",
    },
    {
        "title": "Record without a DOI",
        "authors": ["Katherine Johnson"],
        "year": 2023,
        "journal": "Journal of Canonical Output",
    },
]
payload = {
    output_format: export_bibliography_records(papers, output_format)
    for output_format in ("bibtex", "ris", "csl-json")
}
print(json.dumps(payload, ensure_ascii=False))
'''


@cache
def _run_with_hash_seed(seed: str) -> str:
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        "PYTHONIOENCODING": "utf-8",
    }
    completed = subprocess.run(
        [sys.executable, "-c", CHILD, str(REPO_ROOT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_exports_are_byte_identical_across_hash_seeds() -> None:
    first = _run_with_hash_seed("0")
    second = _run_with_hash_seed("12345")
    assert first.strip()
    assert first.strip() == second.strip()


def test_workload_exports_all_three_formats() -> None:
    payload = json.loads(_run_with_hash_seed("0"))
    for output_format in ("bibtex", "ris", "csl-json"):
        exported = payload[output_format]
        assert exported["format"] == output_format
        assert exported["record_count"] == 3
        assert exported["content"], f"{output_format} export is empty"
        assert exported["scientific_claim_verified"] is False
    assert "@article" in payload["bibtex"]["content"]
    assert "TY  - " in payload["ris"]["content"]
    assert payload["bibtex"]["records"][0]["metadata_conflicts_present"] is True
