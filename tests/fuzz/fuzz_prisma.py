"""Atheris harness for the two-reviewer PRISMA screening validator."""

import sys

import atheris

from literature_evidence_mcp.prisma import dual_screen

_DECISIONS = ("include", "exclude")


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    records = []
    for _ in range(fdp.ConsumeIntInRange(0, 4)):
        reviewers = []
        for _ in range(2):
            choice = fdp.ConsumeIntInRange(0, 2)
            decision = _DECISIONS[choice] if choice < 2 else fdp.ConsumeUnicodeNoSurrogates(8)
            reviewers.append(
                {
                    "reviewer_id": fdp.ConsumeUnicodeNoSurrogates(16),
                    "decision": decision,
                    "reason": fdp.ConsumeUnicodeNoSurrogates(64),
                }
            )
        records.append(
            {
                "record_id": fdp.ConsumeUnicodeNoSurrogates(32),
                "reviewers": reviewers,
            }
        )
    try:
        dual_screen(records)
    except (TypeError, ValueError):
        pass


atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
