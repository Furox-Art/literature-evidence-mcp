"""Only invented text is used; no real test claims or gold labels are stored."""
from __future__ import annotations

import hashlib
import json
import stat
import sys

import pytest

from scripts.evaluation import aggregate_live_doi_smoke as live
from scripts.evaluation import prepare_blinded_expert_packets as blind


def fake_case(ident="case1"):
    return {
        "candidate_id": ident,
        "claim": "Synthetic evidence supports a simulated test claim.",
        "evidence": "Artificial paragraph; NOT an actual clinical observation.",
        "source_doi": "10.5555/synthetic",
        "source_locator": "hypothetical:paragraph-1",
        "publication_type": "hypothetical",
        "collection_date": "2026-10-19",
    }


def example_live():
    data = {}
    revisions = {}
    for engine in live.EXPECTED_ENGINES:
        revisions[engine] = "a" * 40
        data[engine] = {
            "engine": engine,
            "providers": list(live.EXPECTED_PROVIDERS),
            "per_provider_limit": 5,
            "results": [
                {"query": q, "status": "OK",
                 "deduped_record_count": 2, "doi_count": 2,
                 "dois": [f"10.5555/{i}", "10.5555/shared"],
                 "seconds": 1.25, "errors": {}}
                for i, q in enumerate(live.EXPECTED_QUERIES)
            ],
        }
    return data, revisions


def test_produce_blinded_packet_without_gold_or_private_mapping_leak():
    rows = [fake_case("case-a"), fake_case("case-b")]
    packet, private, manifest = blind.create_packet(rows, b"x" * 32)
    revealed = [json.loads(line) for line in packet.decode().splitlines()]
    mapping = json.loads(private)["mapping"]
    assert len(revealed) == 2 and len(mapping) == 2
    assert {x["blind_id"] for x in revealed} == {x["blind_id"] for x in mapping}
    assert not any("candidate_id" in x for x in revealed)
    assert "case-a" not in packet.decode() and "case-b" not in packet.decode()
    assert "claim" not in private.decode() and "evidence" not in private.decode()
    assert all(len(x["blind_id"]) == 32 for x in revealed)
    assert "gold" not in packet.decode().lower()
    assert manifest["packet_sha256"] == hashlib.sha256(packet).hexdigest()
    assert manifest["private_mapping_sha256"] == hashlib.sha256(private).hexdigest()
    assert manifest["status"] == "REVIEW_PACKET_PREPARED_NO_EXPERT_ASSESSMENT"
    assert not manifest["independent_expert_annotation_verified"]
    assert not manifest["blindness_verified"]
    assert not manifest["classification_or_relevance_gold_generated"]
    assert packet == blind.create_packet(list(reversed(rows)), b"x" * 32)[0]
    assert packet != blind.create_packet(rows, b"y" * 32)[0]


@pytest.mark.parametrize("invalid", [
    None, [], [1], [fake_case(), fake_case()], [{}],
    [fake_case() | {"label": "SUPPORT"}],
    [fake_case() | {"prediction": "REFUTE"}],
    [fake_case() | {"gold": "INSUFFICIENT"}],
    [fake_case() | {"unapproved": "value"}],
    [fake_case() | {"claim": ""}],
    [fake_case() | {"evidence": 42}],
    [fake_case() | {"source_locator": ""}],
    [fake_case() | {"candidate_id": "x" * 300}],
    [fake_case() | {"evidence": "x" * 24001}],
    [fake_case()] * 1001,
])
def test_invalid_blind_source_rejected(invalid):
    with pytest.raises((ValueError, TypeError)):
        blind.create_packet(invalid, b"k" * 32)


def test_short_secret_and_hash_id_collision_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="secret"):
        blind.create_packet([fake_case()], b"short")
    def same_id(*_):
        class Digest:
            def hexdigest(self):
                return "f" * 64
        return Digest()
    monkeypatch.setattr(blind.hmac, "new", same_id)
    with pytest.raises(ValueError, match="collision"):
        blind.create_packet([fake_case("a"), fake_case("b")], b"a" * 32)


def test_packet_writer_separates_private_map_and_refuses_existing_files(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps([fake_case()]))
    packet = tmp_path / "review" / "packet.jsonl"
    private = tmp_path / "private" / "map.json"
    manifest = tmp_path / "sealed" / "manifest.json"
    result = blind.write_packet(source, packet, private, manifest, b"k" * 32)
    assert result["item_count"] == 1
    assert stat.S_IMODE(packet.stat().st_mode) == 0o600
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    assert "case1" not in packet.read_text()
    assert "case1" in private.read_text()
    with pytest.raises(FileExistsError):
        blind.write_packet(source, packet, private, manifest, b"k" * 32)


def test_packet_writer_rejects_collocated_or_conflicting_destinations(tmp_path):
    source = tmp_path / "cases.json"
    source.write_text(json.dumps([fake_case()]))
    with pytest.raises(ValueError, match="Unique output paths"):
        blind.write_packet(source, tmp_path / "shared" / "review",
                           tmp_path / "shared" / "private",
                           tmp_path / "other" / "manifest", b"x" * 32)
    with pytest.raises(ValueError, match="Source input"):
        blind.write_packet(source, source, tmp_path / "separate" / "private",
                           tmp_path / "metadata" / "manifest", b"x" * 32)


def test_write_new_private_rejects_overwrites(tmp_path):
    target = tmp_path / "preexisting"
    target.write_bytes(b"retain existing")
    with pytest.raises(FileExistsError):
        blind._write_new_private(target, b"overwrite")
    assert target.read_bytes() == b"retain existing"


def test_blind_cli_requires_secret_and_prints_aggregate_only(monkeypatch, tmp_path, capsys):
    source = tmp_path / "cases.json"
    source.write_text(json.dumps([fake_case()]))
    packet = tmp_path / "review" / "packet.jsonl"
    mapping = tmp_path / "private" / "map.json"
    report = tmp_path / "manifest" / "report.json"
    monkeypatch.setattr(sys, "argv", [
        "blind", "--input", str(source), "--review-packet", str(packet),
        "--private-map", str(mapping), "--manifest", str(report),
    ])
    monkeypatch.setenv("REVIEW_PACKET_SECRET_HEX", "broken")
    with pytest.raises(ValueError, match="Secret"):
        blind.main()
    monkeypatch.setenv("REVIEW_PACKET_SECRET_HEX", (b"s" * 32).hex())
    blind.main()
    printed = capsys.readouterr().out
    assert "case1" not in printed
    assert "PREPARED" in printed


def test_live_aggregate_same_queries_does_not_claim_relevance():
    sources, versions = example_live()
    result = live.aggregate(sources, versions)
    assert result["status"].startswith("LIVE_SAME_QUERY_DESCRIPTIVE")
    assert all(v["summary"]["total_records"] == 6
               for v in result["results"].values())
    assert len(result["doi_overlap_not_relevance"]) == 3
    assert result["doi_overlap_not_relevance"]["own__athenaeum"][
        live.EXPECTED_QUERIES[0]]["doi_overlap_count"] == 2
    assert not result["scientific_competitor_superiority_demonstrated"]
    assert not result["independent_blind_validation_completed"]


@pytest.mark.parametrize("edit", [
    lambda a,b: a.pop("athenaeum"),
    lambda a,b: b.pop("paper_search"),
    lambda a,b: b.update(athenaeum="shortsha"),
    lambda a,b: a["own"].update(engine="other"),
    lambda a,b: a["own"].update(providers=["openalex"]),
    lambda a,b: a["own"].update(per_provider_limit=9),
    lambda a,b: a["own"].update(results=[]),
    lambda a,b: a["own"]["results"][0].update(query="different"),
    lambda a,b: a["own"]["results"][0].update(status="WIN"),
    lambda a,b: a["own"]["results"][0].update(doi_count=100),
    lambda a,b: a["own"]["results"][0].update(dois=[]),
    lambda a,b: a["own"]["results"][0].update(seconds=-1),
    lambda a,b: a["own"]["results"][0].update(errors=["bad"]),
    lambda a,b: a["own"]["results"][0].update(dois=["A", "A"]),
    lambda a,b: a["own"]["results"][0].update(status="ERROR"),
    lambda a,b: a["own"]["results"][0].update(status="BLOCKED"),
])
def test_unfair_or_fabricated_comparison_rejected(edit):
    a,b = example_live()
    edit(a,b)
    with pytest.raises((ValueError, TypeError)):
        live.aggregate(a,b)


def test_zero_dois_and_provider_partial_are_reported_not_ignored():
    a,b = example_live()
    for result in a.values():
        item = result["results"][0]
        item.update(status="PARTIAL", dois=[], doi_count=0,
                    deduped_record_count=0, errors={"source": "RATE_LIMITED"})
    x = live.aggregate(a,b)
    assert x["results"]["own"]["summary"]["status_counts"]["PARTIAL"] == 1
    pair = x["doi_overlap_not_relevance"]["own__athenaeum"]
    assert pair[live.EXPECTED_QUERIES[0]]["doi_jaccard"] is None


def test_live_cli_reads_existing_3_engine_outputs(tmp_path, monkeypatch, capsys):
    data, revs = example_live()
    filenames = {}
    for engine in live.EXPECTED_ENGINES:
        path = tmp_path / f"{engine}.json"
        path.write_text(json.dumps(data[engine]))
        filenames[engine] = str(path)
    versions = tmp_path / "revisions.json"
    versions.write_text(json.dumps(revs))
    output = tmp_path / "summary" / "data.json"
    argv = ["smoke"]
    for engine in live.EXPECTED_ENGINES:
        argv.extend([f"--{engine.replace('_', '-')}", filenames[engine]])
    argv += ["--revisions", str(versions), "--output", str(output)]
    monkeypatch.setattr(sys, "argv", argv)
    live.main()
    result = json.loads(output.read_text())
    assert result["execution_artifact_sha256"]["own"]
    assert result["results"]["athenaeum"]["summary"]["queries"] == 3
    assert "DESCRIPTIVE" in capsys.readouterr().out


def test_failed_output_write_removes_incomplete_packet(tmp_path, monkeypatch):
    source = tmp_path / "cases.json"
    source.write_text(json.dumps([fake_case()]))
    packet = tmp_path / "review" / "packet.jsonl"
    private = tmp_path / "private" / "map.json"
    manifest = tmp_path / "manifest" / "metadata.json"
    real_write = blind._write_new_private
    def fail_second(path, content):
        if path == private:
            raise OSError("simulated private destination failure")
        return real_write(path, content)
    monkeypatch.setattr(blind, "_write_new_private", fail_second)
    with pytest.raises(OSError, match="simulated"):
        blind.write_packet(source, packet, private, manifest, b"k" * 32)
    assert not packet.exists()
    assert not private.exists()
    assert not manifest.exists()


def test_failed_write_removes_partial_destination(tmp_path, monkeypatch):
    path = tmp_path / "partial"
    original_fdopen = blind.os.fdopen

    class FailingStream:
        def __init__(self, fd):
            self.fd = fd
        def __enter__(self):
            return self
        def write(self, content):
            raise OSError("synthetic write failure")
        def __exit__(self, *args):
            blind.os.close(self.fd)

    monkeypatch.setattr(blind.os, "fdopen", lambda fd, mode: FailingStream(fd))
    with pytest.raises(OSError, match="synthetic"):
        blind._write_new_private(path, b"sensitive test bytes")
    monkeypatch.setattr(blind.os, "fdopen", original_fdopen)
    assert not path.exists()


def test_main_module_execution_from_file_in_synthetic_context(tmp_path, monkeypatch):
    import runpy
    from pathlib import Path

    data = tmp_path / "cases.json"
    data.write_text(json.dumps([fake_case("source-once")]))
    packet = tmp_path / "review" / "blind.jsonl"
    private = tmp_path / "private" / "mapping.json"
    meta = tmp_path / "meta" / "status.json"
    monkeypatch.setenv("REVIEW_PACKET_SECRET_HEX", (b"x" * 32).hex())
    monkeypatch.setattr(sys, "argv", [
        "runner", "--input", str(data), "--review-packet", str(packet),
        "--private-map", str(private), "--manifest", str(meta)
    ])
    runpy.run_path(str(Path(blind.__file__)), run_name="__main__")
    assert packet.exists() and private.exists() and meta.exists()


def test_aggregate_script_main_guard_on_only_synthetic_data(tmp_path, monkeypatch):
    import runpy
    from pathlib import Path

    systems, revisions = example_live()
    arg = ["smoke"]
    for engine in live.EXPECTED_ENGINES:
        p = tmp_path / f"{engine}.json"
        p.write_text(json.dumps(systems[engine]))
        arg.extend([f"--{engine.replace('_', '-')}", str(p)])
    meta = tmp_path / "revisions.json"
    meta.write_text(json.dumps(revisions))
    final = tmp_path / "summary.json"
    arg.extend(["--revisions", str(meta), "--output", str(final)])
    monkeypatch.setattr(sys, "argv", arg)
    runpy.run_path(str(Path(live.__file__)), run_name="__main__")
    assert json.loads(final.read_text())["scientific_competitor_superiority_demonstrated"] is False


@pytest.mark.parametrize("discipline,source_field,source_value", [
    ("physics", "source_id", "arXiv:2610.00001"),
    ("mathematics", "source_url", "https://arxiv.org/abs/2610.00002"),
    ("chemistry", "source_doi", "10.5555/synthetic-chem"),
    ("computer science", "source_id", "conference:synthetic-2026"),
    ("earth science", "source_url", "https://example.org/earth-data"),
    ("biology", "source_doi", "10.5555/synthetic-bio"),
])
def test_all_science_domains_and_non_doi_sources_supported(
    discipline, source_field, source_value,
):
    candidate = fake_case()
    candidate.pop("source_doi")
    candidate[source_field] = source_value
    candidate["discipline"] = discipline
    packet, private, meta = blind.create_packet([candidate], b"z" * 32)
    emitted = json.loads(packet.decode().strip())
    assert emitted["discipline"] == discipline
    assert emitted[source_field] == source_value
    assert emitted["source_locator"] == "hypothetical:paragraph-1"
    assert "candidate_id" not in emitted
    assert json.loads(private)["mapping"][0]["candidate_id"] == "case1"
    assert not meta["independent_expert_annotation_verified"]
    assert not meta["classification_or_relevance_gold_generated"]


@pytest.mark.parametrize("invalid", [
    {k: v for k, v in fake_case().items() if k != "source_doi"},
    fake_case() | {"source_id": ""},
    fake_case() | {"source_id": 10},
    fake_case() | {"source_url": []},
    fake_case() | {"source_id": "A" * 261},
    fake_case() | {"discipline": ""},
    fake_case() | {"discipline": None},
])
def test_general_science_source_validation_remains_fail_closed(invalid):
    with pytest.raises((TypeError, ValueError)):
        blind.create_packet([invalid], b"z" * 32)
