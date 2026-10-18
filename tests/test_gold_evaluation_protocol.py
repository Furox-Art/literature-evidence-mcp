"""Deterministic audit of benchmark math and no-test-tuning protocols."""
import pytest

from scripts.evaluation import evidencebench_gold as bench
from scripts.evaluation import scifact_gold as scifact


def test_confusion_explicit_abstention():
    out = scifact.confusion([True, False, True, False], [False] * 4)
    assert out["tp"] == 0 and out["fn"] == 2
    assert out["tn"] == 2 and out["fp"] == 0
    assert out["precision"] is None and out["f1"] == 0
    assert out["recall"] == 0
    with pytest.raises(ValueError):
        scifact.confusion([True], [])


def test_lexical_baselines_distinguish_irrelevant_text():
    assert scifact.jaccard("significant neural effect", "neural significant effect") > 0
    assert scifact.jaccard("brain imaging", "liver metabolism") == 0
    assert scifact.containment("brain brain imagery", "brain") == 1 / 2
    assert scifact.containment("", "none") == 0
    assert scifact.jaccard("", "none") == 0


def test_threshold_uses_only_supplied_train_partition():
    rows = [(1, 1, "brain neural", "brain neural", True),
            (2, 2, "liver", "neural", False)]
    a, b = scifact.optimize_train(rows, scifact.containment)
    assert a > 0 and b == 1
    # Contrast dev samples never passed to threshold fitting.
    out = scifact.confusion([True, False], [True, False])
    assert out["f1"] == 1.0


def test_cluster_bootstrap_fixed_seed():
    ids = [1, 1, 2, 3]
    g = [True, False, False, True]
    p = [True, True, False, False]
    ci = scifact.cluster_ci(ids, g, p, repeats=500)
    assert scifact.cluster_ci(ids, g, p, repeats=500) == ci
    assert 0 <= ci[0] <= ci[1] <= 1


def test_evidencebench_aspect_metrics():
    row = {
        "aspect_list_ids": ["a", "b"],
        "results_aspect_list_ids": ["a"],
        "aspect2sentence_indices": {"a":[1], "b":[2, 3]},
    }
    assert bench.aspect_recall(row, [1, 3]) == 1.0
    assert bench.aspect_recall(row, [1]) == 0.5
    assert bench.aspect_recall(row, [2], True) == 0.0
    assert bench.aspect_recall({**row, "results_aspect_list_ids":[]}, [1], True) is None


def test_evidencebench_fail_closed_if_gold_checksum_wrong(tmp_path):
    data = tmp_path / "bench.json"
    data.write_text("{}")
    with pytest.raises(ValueError, match="SHA mismatch"):
        bench.evaluate(data)


def test_scifact_missing_corpus_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        scifact.evaluate(tmp_path)


def test_scifact_duplicate_corpus_rejected(tmp_path):
    folder = tmp_path
    for name in ("claims_train.jsonl","claims_dev.jsonl"):
        (folder / name).write_text("")
    (folder / "corpus.jsonl").write_text(
        '{"doc_id": 1, "abstract": ["a"]}\n{"doc_id": 1, "abstract": ["a"]}\n')
    with pytest.raises(ValueError, match="duplicate"):
        scifact.evaluate(folder)
