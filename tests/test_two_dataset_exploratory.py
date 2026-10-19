"""Synthetic regressions for the two retrospective evaluations.

Never embed licensed NFCorpus/VitaminC test examples in Git.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from scripts.evaluation import nfcorpus_fixed_bm25_exploratory as nf
from scripts.evaluation import vitaminc_three_pinned_exploratory as vc


def test_bm25_exact_production_ranking_on_synthetic_records():
    from literature_evidence_mcp.bm25_retrieval import rank_supplied_evidence

    docs = [
        {"_id": "a", "title": "SyNaPtiC synaptic modulation", "text": "neural activity"},
        {"_id": "b", "title": "Photosynthesis", "text": "plant cells"},
        {"_id": "c", "title": "synaptic activity", "text": "brain activity"},
    ]
    queries = {"q1": "synaptic activity", "q2": "nooverlap term"}
    gold = {"q1": {"a", "c"}, "q2": {"b"}}
    report = nf.score_documents(docs, queries, gold)
    assert report["status"].startswith("EXPLORATORY")
    assert report["test_queries"] == 2
    assert report["no_lexical_match_queries"] == 1
    assert report["precision_at_k"] is None
    single = rank_supplied_evidence(
        "synaptic activity",
        [{"id": d["_id"], "title": d["title"], "abstract": d["text"]} for d in docs],
        10,
    )
    # This tests that the single index uses the same score and tie behavior.
    assert {x["id"] for x in single["results"][:2]} == {"a", "c"}
    assert report["scientific_superiority_demonstrated"] is False


def test_no_retrieval_positive_is_explicitly_unscored():
    docs = [{"_id": "x", "title": "text", "text": "simple"}]
    with pytest.raises(ValueError, match="No known-positive"):
        nf.score_documents(docs, {"q1": "simple"}, {"q1": set()})


def test_retrieval_unindexable_source_and_query_rejected():
    with pytest.raises(ValueError, match="Empty tokenized"):
        nf.score_documents([{"_id": "a", "title": "a", "text": "."}],
                           {"q": "good query"}, {"q": {"a"}})
    with pytest.raises(ValueError, match="no indexable"):
        nf.score_documents([{"_id": "a", "title": "good", "text": "text"}],
                           {"q": "I!"}, {"q": {"a"}})


def _make_vc(tmp_path, monkeypatch, rows):
    path = tmp_path / "vitaminc-synthetic.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    monkeypatch.setattr(vc, "EXPECTED_ROWS", len(rows))
    monkeypatch.setitem(vc.DATASETS["classification"], "sha256",
                        hashlib.sha256(path.read_bytes()).hexdigest())
    return path


def _row(uid="one", case="group1", label="SUPPORTS"):
    return {
        "unique_id": uid, "case_id": case, "claim": "Synthetic text claim.",
        "evidence": "This is synthetic premise.", "label": label,
    }


def test_public_test_mapping_is_fixed_and_has_no_case_leak(monkeypatch, tmp_path):
    source = _make_vc(tmp_path, monkeypatch, [
        _row("one", "g1", "SUPPORTS"),
        _row("two", "g1", "REFUTES"),
        _row("three", "g2", "NOT ENOUGH INFO"),
    ])
    rows, groups = vc.read_vitaminc(source)
    assert groups == ["g1", "g1", "g2"]
    assert [r["label"] for r in rows] == ["Supports", "Refutes", "Neutral"]
    assert not any("case_id" in row or "unique_id" in row for row in rows)


@pytest.mark.parametrize("broken", [
    [_row(label="UNMAPPED")],
    [_row(uid="")],
    [_row(case="")],
    [_row(), _row()],
    [_row(label=4)],
    [_row(label="SUPPORTS") | {"claim": ""}],
    [_row(label="REFUTES") | {"evidence": 5}],
])
def test_vc_fail_closed_gold_schema(monkeypatch, tmp_path, broken):
    path = _make_vc(tmp_path, monkeypatch, broken)
    with pytest.raises(ValueError):
        vc.read_vitaminc(path)


def test_vc_hash_mismatch_rejected_without_reading_labels(monkeypatch, tmp_path):
    path = _make_vc(tmp_path, monkeypatch, [_row()])
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="SHA-256"):
        vc.read_vitaminc(path)


def test_vc_expected_size_gate(monkeypatch, tmp_path):
    path = _make_vc(tmp_path, monkeypatch, [_row()])
    monkeypatch.setattr(vc, "EXPECTED_ROWS", 55197)
    with pytest.raises(ValueError, match="row count"):
        vc.read_vitaminc(path)


def test_vc_summary_aggregates_only_and_no_predictions(monkeypatch, tmp_path):
    rows = [
        {"claim": "same", "evidence": "same premise", "label": "Supports"},
        {"claim": "same", "evidence": "same premise", "label": "Refutes"},
        {"claim": "different", "evidence": "another", "label": "Neutral"},
    ]
    predictions = ["SUPPORT", "REFUTE", "NEUTRAL"]
    def fake_model(directory, candidates, digest):
        assert digest == vc.CANDIDATES["frozen_original_deberta_small"]["weights_sha256"]
        return {
            "weights_sha256": digest, "predictions": predictions,
            "raw_predictions": predictions,
            "metrics": {"accuracy": 1.0},
            "raw_argmax_metrics": {"accuracy": 1.0},
            "selective": {"non_neutral_coverage": 2 / 3},
        }
    monkeypatch.setattr(vc, "infer_model", fake_model)
    result = vc.summarize("frozen_original_deberta_small", tmp_path, rows,
                          ["case1", "case1", "case2"])
    assert result["duplicate_exact_pairs"] == 1
    assert result["case_id_groups"] == 2
    assert result["test_rows"] == 3
    assert result["unique_pair_metrics"]["count"] == 2
    assert result["scientific_superiority_demonstrated"] is False
    assert result["production_model_modified"] is False
    assert "predictions" not in result and "raw_predictions" not in result
    assert "same premise" not in json.dumps(result)
    assert "case1" not in json.dumps(result)


def test_vc_model_unknown_and_mismatched_output_fail_closed(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="Only pre-pinned"):
        vc.summarize("imaginary", tmp_path, [_row()], ["g"])
    with pytest.raises(ValueError, match="Invalid"):
        vc.summarize("general_deberta_base", tmp_path, [_row()], [])
    monkeypatch.setattr(vc, "infer_model", lambda *_: {
        "predictions": [], "raw_predictions": [],
    })
    with pytest.raises(ValueError, match="misaligned"):
        vc.summarize("general_deberta_base", tmp_path, [_row()], ["g"])


def test_nf_source_pin_fail_closed(tmp_path):
    path = tmp_path / "nfcorpus.zip"
    path.write_bytes(b"synthetic non-archive")
    with pytest.raises(ValueError, match="SHA-256"):
        nf.load_nfcorpus(path)


def test_nf_pinned_synthetic_archive_decodes_test_only(monkeypatch, tmp_path):
    import zipfile

    contents = {
        "nfcorpus/corpus.jsonl": "\n".join(json.dumps(x) for x in [
            {"_id": "a", "title": "neurobiology", "text": "cell"},
            {"_id": "b", "title": "hematology", "text": "blood"},
        ]) + "\n",
        "nfcorpus/queries.jsonl": json.dumps({
            "_id": "q1", "text": "neurobiology",
        }) + "\n",
        "nfcorpus/qrels/test.tsv": (
            "query-id\tcorpus-id\tscore\nq1\ta\t2\nq1\tb\t0\n"
        ),
    }
    p = tmp_path / "nfcorpus.zip"
    with zipfile.ZipFile(p, "w") as file:
        for name, text in contents.items():
            file.writestr(name, text)
    monkeypatch.setitem(nf.CANDIDATES["retrieval"], "sha256",
                        hashlib.sha256(p.read_bytes()).hexdigest())
    monkeypatch.setattr(nf, "EXPECTED_DOCS", 2)
    monkeypatch.setattr(nf, "EXPECTED_TEST_QUERIES", 1)
    documents, queries, labels, observed = nf.load_nfcorpus(p)
    assert observed == 2
    assert len(documents) == 2
    assert list(queries) == ["q1"] and labels == {"q1": {"a"}}
    result = nf.evaluate(p)
    assert result["scored_queries"] == 1
    assert result["qrels_rows_inspected"] == 2
    assert result["known_positive_recall_at_k"]["10"] == 1.0


def test_nf_malformed_qrel_duplicate_or_unknown_fails(monkeypatch, tmp_path):
    import zipfile

    datasets = [
        "query-id\tcorpus-id\tscore\nq1\tmissing\t1\n",
        "query-id\tcorpus-id\tscore\nq1\ta\t2\nq1\ta\t2\n",
        "query-id\tcorpus-id\tscore\nq1\ta\n",
        "q\tdoc\tlabel\nq1\ta\t1\n",
    ]
    for idx, qrel in enumerate(datasets):
        p = tmp_path / f"case{idx}.zip"
        with zipfile.ZipFile(p, "w") as file:
            file.writestr("nfcorpus/corpus.jsonl",
                          json.dumps({"_id": "a", "title": "a", "text": "text"}) + "\n")
            file.writestr("nfcorpus/queries.jsonl",
                          json.dumps({"_id": "q1", "text": "text"}) + "\n")
            file.writestr("nfcorpus/qrels/test.tsv", qrel)
        monkeypatch.setitem(nf.CANDIDATES["retrieval"], "sha256",
                            hashlib.sha256(p.read_bytes()).hexdigest())
        monkeypatch.setattr(nf, "EXPECTED_DOCS", 1)
        monkeypatch.setattr(nf, "EXPECTED_TEST_QUERIES", 1)
        with pytest.raises(ValueError):
            nf.load_nfcorpus(p)



def test_nf_cli_writes_only_aggregate_result(monkeypatch, tmp_path, capsys):
    import sys
    target = tmp_path / "out" / "retrieval.json"
    monkeypatch.setattr(nf, "evaluate", lambda source: {
        "scored_queries": 5, "known_positive_recall_at_k": {"10": 0.2},
        "scientific_superiority_demonstrated": False,
    })
    monkeypatch.setattr(sys, "argv", ["test", "--dataset", str(tmp_path / "fake.zip"),
                                        "--output", str(target)])
    nf.main()
    stored = json.loads(target.read_text())
    assert stored["scored_queries"] == 5
    assert not stored["scientific_superiority_demonstrated"]
    assert "NFCORPUS_EXPLORATORY_DONE" in capsys.readouterr().out


def test_vc_cli_writes_aggregate_without_predictions(monkeypatch, tmp_path, capsys):
    import sys
    target = tmp_path / "out" / "classification.json"
    monkeypatch.setattr(vc, "read_vitaminc", lambda _: (
        [{"claim": "synthetic", "evidence": "synthetic", "label": "Neutral"}],
        ["group"],
    ))
    monkeypatch.setattr(vc, "summarize", lambda *_: {
        "metrics": {"accuracy": 0.5, "macro_f1": 0.5},
        "model_key": "frozen_original_deberta_small",
        "scientific_superiority_demonstrated": False,
    })
    monkeypatch.setattr(sys, "argv", [
        "test", "--dataset", str(tmp_path / "fake.jsonl"),
        "--model-key", "frozen_original_deberta_small",
        "--model-dir", str(tmp_path), "--output", str(target),
    ])
    vc.main()
    stored = json.loads(target.read_text())
    assert "predictions" not in stored
    assert stored["metrics"]["accuracy"] == 0.5
    assert not stored["scientific_superiority_demonstrated"]
    assert "VITAMINC_MODEL_COMPLETED" in capsys.readouterr().out



@pytest.mark.parametrize("failure", ["duplicate_document", "duplicate_query", "query_count"])
def test_nf_source_manifest_fails_closed(monkeypatch, tmp_path, failure):
    import zipfile

    docs = [{"_id": "a", "title": "signal", "text": "molecule"},
            {"_id": "b", "title": "brain", "text": "signal"}]
    queries = [{"_id": "q1", "text": "brain"}]
    if failure == "duplicate_document":
        docs[1]["_id"] = "a"
    elif failure == "duplicate_query":
        queries.append(queries[0].copy())
    archive = tmp_path / "nf.zip"
    with zipfile.ZipFile(archive, "w") as f:
        f.writestr("nfcorpus/corpus.jsonl",
                   "\n".join(json.dumps(x) for x in docs))
        f.writestr("nfcorpus/queries.jsonl",
                   "\n".join(json.dumps(x) for x in queries))
        f.writestr("nfcorpus/qrels/test.tsv",
                   "query-id\tcorpus-id\tscore\nq1\ta\t1\n")
    monkeypatch.setitem(nf.CANDIDATES["retrieval"], "sha256",
                        hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(nf, "EXPECTED_DOCS", 2)
    monkeypatch.setattr(nf, "EXPECTED_TEST_QUERIES",
                        2 if failure == "query_count" else 1)
    with pytest.raises(ValueError):
        nf.load_nfcorpus(archive)


def test_vc_blank_line_is_ignored_in_synthetic_input(monkeypatch, tmp_path):
    path = _make_vc(tmp_path, monkeypatch, [_row()])
    path.write_bytes(b"\n" + path.read_bytes())
    monkeypatch.setitem(vc.DATASETS["classification"], "sha256",
                        hashlib.sha256(path.read_bytes()).hexdigest())
    rows, groups = vc.read_vitaminc(path)
    assert len(rows) == 1 and groups == ["group1"]



def test_nf_main_module_guard_runs_on_only_synthetic_fixture(monkeypatch, tmp_path):
    import runpy
    import sys
    import zipfile
    from pathlib import Path

    source = tmp_path / "synthetic-nf.zip"
    with zipfile.ZipFile(source, "w") as arc:
        arc.writestr("nfcorpus/corpus.jsonl", "\n".join(
            json.dumps({"_id": str(i), "title": "synthetic biological word",
                        "text": "general"} )
            for i in range(3633)
        ))
        arc.writestr("nfcorpus/queries.jsonl", "\n".join(
            json.dumps({"_id": str(i), "text": "synthetic biological"})
            for i in range(323)
        ))
        arc.writestr("nfcorpus/qrels/test.tsv", "query-id\tcorpus-id\tscore\n" +
                     "".join(f"{i}\t{i}\t1\n" for i in range(323)))
    monkeypatch.setitem(nf.CANDIDATES["retrieval"], "sha256",
                        hashlib.sha256(source.read_bytes()).hexdigest())
    target = tmp_path / "nf-report.json"
    monkeypatch.setattr(sys, "argv", ["script", "--dataset", str(source),
                                      "--output", str(target)])
    runpy.run_path(str(Path(nf.__file__)), run_name="__main__")
    x = json.loads(target.read_text())
    assert x["test_queries"] == 323
    assert not x["scientific_superiority_demonstrated"]


def test_vc_main_module_guard_with_mocked_inference(monkeypatch, tmp_path):
    import runpy
    import sys
    from pathlib import Path

    source = tmp_path / "synthetic-vitaminC.jsonl"
    with source.open("w") as out:
        for i in range(55197):
            out.write(json.dumps({
                "unique_id": f"unit{i}", "case_id": f"case{i // 3}",
                "claim": f"Synthetic example {i}",
                "evidence": "Explicitly synthetic premise only",
                "label": "NOT ENOUGH INFO",
            }) + "\n")
    monkeypatch.setitem(vc.DATASETS["classification"], "sha256",
                        hashlib.sha256(source.read_bytes()).hexdigest())
    from scripts.evaluation import nli_challenger_benchmark as model_script

    def no_real_model(folder, rows, sha):
        assert len(rows) == 55197
        assert "model.safetensors" not in str(folder)
        assert sha == vc.CANDIDATES["frozen_original_deberta_small"]["weights_sha256"]
        labels = ["NEUTRAL"] * len(rows)
        return {
            "predictions": labels, "raw_predictions": labels,
            "metrics": {"accuracy": 1.0, "macro_f1": 1.0},
            "selective": {"non_neutral_coverage": 0},
        }
    monkeypatch.setattr(model_script, "infer_model", no_real_model)
    target = tmp_path / "vitaminc-aggregate-synthetic.json"
    monkeypatch.setattr(sys, "argv", [
        "script", "--dataset", str(source),
        "--model-key", "frozen_original_deberta_small",
        "--model-dir", str(tmp_path), "--output", str(target),
    ])
    runpy.run_path(str(Path(vc.__file__)), run_name="__main__")
    x = json.loads(target.read_text())
    assert x["test_rows"] == 55197
    assert x["scientific_superiority_demonstrated"] is False
    assert "Synthetic example" not in json.dumps(x)
