"""Synthetic grammar regression: never ship CC BY-NC-ND HealthFC rows."""
from __future__ import annotations

import pytest

from scripts.evaluation import healthfc_controlled as fc


@pytest.mark.parametrize("source,expected", [
    ("Can probiotics lower blood sugar?", "Probiotics can lower blood sugar."),
    ("Does cranberry juice prevent cystitis?",
     "Cranberry juice does prevent cystitis."),
    ("Do supplements improve sleep?", "Supplements do improve sleep."),
    ("Will a vaccine protect adults?", "A vaccine will protect adults."),
    ("Did trials show a benefit?", "Trials did show a benefit."),
    ("Could walking reduce fatigue?", "Walking could reduce fatigue."),
    ("Should masks prevent spread?", "Masks should prevent spread."),
])
def test_strict_reversible_auxiliary_inversion(source, expected):
    result, reason = fc.normalize_question(source)
    assert result == expected
    assert reason == "automatic_syntax_only_unreviewed"


@pytest.mark.parametrize("source,reason", [
    ("", "empty"),
    ("The intervention helps.", "already_declarative"),
    ("Is the treatment effective?", "unsupported_question_type"),
    ("What treatments help?", "unsupported_question_type"),
    ("Can X help? Does Y prevent illness?", "compound_or_embedded_question"),
    ("Can X help? Why?", "compound_or_embedded_question"),
    ("Can X help; prevent illness?", "complex_or_ambiguous_syntax"),
    ("Can X cure a disease? Is that a benefit?", "compound_or_embedded_question"),
    ("Can a device do something?", "predicate_not_identified"),
    ("Can prevent illness?", "subject_boundary_unreliable"),
    ("Can apples to reduce fatigue?", "subject_boundary_unreliable"),
    ("Can A that might help others?", "subject_boundary_unreliable"),
    ("Can \"X\" help: safely?", "complex_or_ambiguous_syntax"),
    ("Can " + "long " * 16 + "help?", "subject_boundary_unreliable"),
])
def test_abstentions_never_create_ground_truth(source, reason):
    assert fc.normalize_question(source) == (None, reason)


def test_real_source_requires_exact_bytes(tmp_path):
    path = tmp_path / "healthfc.csv"
    with pytest.raises(FileNotFoundError):
        fc.read_source(path)
    path.write_bytes(b"en_claim,en_top_sentences,label\\nX,Y,0\\n")
    with pytest.raises(ValueError, match="SHA-256"):
        fc.read_source(path)


def test_aggregate_has_correct_label_mapping_and_no_corpus_text():
    records = [
        {"en_claim": "Can tablets improve sleep?", "en_top_sentences": "Synthetic A",
         "label": "0"},
        {"en_claim": "Does therapy reduce pain?", "en_top_sentences": "Synthetic B",
         "label": "2"},
        {"en_claim": "Is treatment effective?", "en_top_sentences": "Synthetic C",
         "label": "1"},
    ]
    data, aggregate = fc.prepare(records)
    assert [r["label"] for r in data] == ["Supports", "Refutes"]
    assert aggregate["original_label_distribution"] == {
        "NEUTRAL": 1, "REFUTE": 1, "SUPPORT": 1
    }
    assert aggregate["selected_rows"] == 2
    assert aggregate["excluded_rows"] == 1
    assert aggregate["disposition"]["unsupported_question_type"] == 1
    text = repr(aggregate)
    for record in records:
        assert record["en_claim"] not in text
        assert record["en_top_sentences"] not in text
    with pytest.raises(ValueError, match="gold"):
        fc.prepare([{"en_claim": "Can pills improve sleep?",
                     "en_top_sentences": "Synthetic", "label": "other"}])
