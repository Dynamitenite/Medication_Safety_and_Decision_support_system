# SOURCE: NOT IN PAPERS. FIXTURES ONLY: every XML, zip, JSON and markdown string below is
# hand-written to exercise code paths. None of it is real DDI 2013 / TAC 2017 / DailyMed data,
# and none of it may appear in the UI. These tests prove the API plumbing, not data quality.
import json
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.config import Settings, get_settings
from api.services import datasets
from api.services.trace import parse_trace

FIXTURE_DDI_DOC = """<document id="DDI-DrugBank.dFIX{n}">
<sentence id="DDI-DrugBank.dFIX{n}.s0" text="Aspirin increases the effect of warfarin.">
<entity id="e0" charOffset="0-6" type="drug" text="Aspirin"/>
<entity id="e1" charOffset="32-39" type="drug" text="warfarin"/>
<pair id="p0" e1="e0" e2="e1" ddi="true" type="{typ}"/>
</sentence>
<sentence id="DDI-DrugBank.dFIX{n}.s1" text="Do not mix aspirin and ibuprofen.">
<entity id="e0" charOffset="11-17" type="drug" text="aspirin"/>
<entity id="e1" charOffset="23-31" type="drug" text="ibuprofen"/>
<pair id="p0" e1="e0" e2="e1" ddi="false"/>
</sentence></document>"""

FIXTURE_TAC = """<Label drug="FixDrug" setid="x">
<Text><Section name="adverse reactions" id="S1">Nausea was common.</Section></Text>
<Mentions><Mention id="M1" section="S1" type="AdverseReaction" start="0" len="6" str="Nausea"/></Mentions>
<Relations/><Reactions><Reaction id="R1" str="Nausea"/></Reactions></Label>"""

FIXTURE_TRACE = """# Paper trace

Fixture preamble line.

| component | file | source | note | status |
|---|---|---|---|---|
| A | a.py | FROM PAPERS: P6 (fixture) | n1 | UNTESTED |
| B | b.py | NOT IN PAPERS | n2 | RAN |
| C | c.py | FROM BASELINE REVIEW (ICMLAS 2025) | n3 | VERIFIED against fixture |
| D | d.py | something else | n4 | maybe |
| bad row | only three | cells |
"""


@pytest.fixture()
def dirs(tmp_path):
    data, art = tmp_path / "data", tmp_path / "artifacts"
    data.mkdir()
    art.mkdir()
    return data, art


@pytest.fixture()
def client(dirs, tmp_path):
    data, art = dirs
    trace = tmp_path / "PAPER_TRACE.md"
    trace.write_text(FIXTURE_TRACE, encoding="utf-8")
    settings = Settings(data_dir=data, artifacts_dir=art, trace_path=trace,
                        encoder_name="tfidf", classifier_name="linear_baseline")
    app.dependency_overrides[get_settings] = lambda: settings
    datasets.clear_cache()
    yield TestClient(app)
    app.dependency_overrides.clear()
    datasets.clear_cache()


def write_ddi(data: Path):
    """12 train docs (enough groups for the dev split) and 3 test docs."""
    for n in range(12):
        d = data / "ddi2013" / "DDICorpus" / "Train" / "DrugBank"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"t{n}.xml").write_text(
            FIXTURE_DDI_DOC.format(n=n, typ="effect" if n % 2 else "advise"), encoding="utf-8")
    for n in range(100, 103):
        d = data / "ddi2013" / "DDICorpus" / "Test" / "Test for DDI Extraction task" / "DrugBank"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"x{n}.xml").write_text(FIXTURE_DDI_DOC.format(n=n, typ="int"), encoding="utf-8")


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_all_routes_under_api_prefix():
    paths = list(app.openapi()["paths"])
    assert len(paths) == 7 and all(p.startswith("/api/") for p in paths)


def test_status_empty_data_is_not_ready_with_reasons(client):
    body = client.get("/api/status").json()
    comps = {c["id"]: c for c in body["components"]}
    assert set(comps) == {"ddi_data", "tac_data", "dailymed_data", "encoder", "index", "ddi_model"}
    for c in comps.values():
        assert c["status"] == "not_ready" and c["reason"] and c["fix"]
    assert body["active_encoder"] == "tfidf" and body["active_classifier"] == "linear_baseline"


def test_status_coming_soon_modules(client):
    mods = {m["id"]: m for m in client.get("/api/status").json()["modules"]}
    assert len(mods) == 7
    assert all(m["status"] == "coming_soon" and m["owner"] == "to be confirmed"
               for m in mods.values())
    assert {k: m["stages"] for k, m in mods.items()} == {
        "allergy_check": [4], "contraindication_check": [4], "duplicate_therapy_check": [3],
        "disease_precautions": [4], "full_patient_profile": [3],
        "deep_learning_encoder": [2, 5], "focal_loss_model": [4]}
    assert mods["deep_learning_encoder"]["stage_names"] == ["Information Extraction",
                                                            "Recommendation Engine"]


def test_status_stages(client):
    stages = client.get("/api/status").json()["stages"]
    assert [s["number"] for s in stages] == [1, 2, 3, 4, 5, 6]
    assert [s["number"] for s in stages if s["in_scope"]] == [2, 4, 5, 6]
    assert stages[0]["name"] == "Input Understanding"


def test_status_ddi_ready_when_files_exist(client, dirs):
    write_ddi(dirs[0])
    c = {c["id"]: c for c in client.get("/api/status").json()["components"]}["ddi_data"]
    assert c["status"] == "ready"
    assert c["detail"]["xml_train"] == 12 and c["detail"]["xml_test"] == 3


def test_status_index_and_model_follow_files(client, dirs):
    art = dirs[1]
    (art / "index").mkdir()
    (art / "index" / "manifest.json").write_text(json.dumps({"encoder": "tfidf", "chunks": 3}))
    (art / "ddi_baseline").mkdir()
    (art / "ddi_baseline" / "model.joblib").write_bytes(b"x")
    (art / "ddi_baseline" / "metrics.json").write_text("{}")
    comps = {c["id"]: c for c in client.get("/api/status").json()["components"]}
    assert comps["index"]["status"] == comps["encoder"]["status"] == "ready"
    assert comps["ddi_model"]["status"] == "ready"


def test_ddi_stats_not_ready(client):
    body = client.get("/api/datasets/ddi2013/stats").json()
    assert body["status"] == "not_ready" and body["splits"] == [] and body["reason"]


def test_ddi_stats_counts(client, dirs):
    write_ddi(dirs[0])
    body = client.get("/api/datasets/ddi2013/stats").json()
    assert body["status"] == "ready"
    by = {s["split"]: s for s in body["splits"]}
    assert by["train"]["instances"] + by["dev"]["instances"] == 24  # 12 docs x 2 pairs
    assert by["test"]["class_counts"] == {"effect": 0, "mechanism": 0, "advise": 0, "int": 3,
                                          "false": 3}
    assert by["test"]["imbalance_false_to_class"]["int"] == 1.0
    assert by["test"]["imbalance_false_to_class"]["effect"] is None  # no division by zero
    parser = {p["split"]: p["counts"] for p in body["parser"]}
    assert parser["train_all"]["pairs"] == 24 and parser["test"]["pairs"] == 6
    assert body["files_by_split"]["train"] == 12


def test_ddi_examples_filters(client, dirs):
    write_ddi(dirs[0])
    r = client.get("/api/datasets/ddi2013/examples", params={"split": "test", "label": "int",
                                                            "limit": 2}).json()
    assert r["status"] == "ready" and r["total_matching"] == 3 and len(r["examples"]) == 2
    ex = r["examples"][0]
    assert ex["label"] == "int" and ex["split"] == "test"
    assert "<e1>Aspirin</e1>" in ex["marked_text"] and "<e2>warfarin</e2>" in ex["marked_text"]


def test_ddi_examples_validation(client):
    assert client.get("/api/datasets/ddi2013/examples", params={"label": "bogus"}).status_code == 422
    assert client.get("/api/datasets/ddi2013/examples", params={"limit": 0}).status_code == 422
    assert client.get("/api/datasets/ddi2013/examples", params={"split": "val"}).status_code == 422


def test_ddi_examples_not_ready(client):
    r = client.get("/api/datasets/ddi2013/examples").json()
    assert r["status"] == "not_ready" and r["examples"] == []


def test_dailymed_not_ready_without_zips(client):
    r = client.get("/api/datasets/dailymed/stats").json()
    assert r["status"] == "not_ready" and r["labels_parsed"] is None and r["fix"]


def test_dailymed_zip_present_but_no_summary(client, dirs):
    folder = dirs[0] / "dailymed_rx"
    folder.mkdir()
    with zipfile.ZipFile(folder / "fixture_part.zip", "w") as zf:
        zf.writestr("a.txt", "fixture")
    r = client.get("/api/datasets/dailymed/stats").json()
    assert r["status"] == "not_ready" and r["labels_parsed"] is None
    assert r["zip_files"][0]["name"] == "fixture_part.zip"
    assert client.get("/api/status").json()["components"][2]["status"] == "ready"


def test_dailymed_ready_from_summary_file(client, dirs):
    folder = dirs[0] / "dailymed_rx"
    folder.mkdir()
    with zipfile.ZipFile(folder / "fixture_part.zip", "w") as zf:
        zf.writestr("a.txt", "fixture")
    (dirs[1] / "dailymed_stats.json").write_text(json.dumps({
        "is_sample": True, "sample_limit_per_part": 7,
        "scope": "SAMPLE: the first 7 labels of each loaded part, not the full set",
        "parts_loaded": ["fixture_part.zip"], "labels_parsed": 7, "parse_failures": 0,
        "labels_per_section": {"indications": 7}, "chunks": 9, "distinct_ingredients": 3,
        "distinct_active_moieties": 2}))
    r = client.get("/api/datasets/dailymed/stats").json()
    assert r["status"] == "ready" and r["labels_parsed"] == 7 and r["chunks"] == 9
    assert r["is_sample"] is True and r["scope"].startswith("SAMPLE")


def test_dailymed_bad_summary_file_is_not_ready(client, dirs):
    folder = dirs[0] / "dailymed_rx"
    folder.mkdir()
    with zipfile.ZipFile(folder / "fixture_part.zip", "w") as zf:
        zf.writestr("a.txt", "fixture")
    (dirs[1] / "dailymed_stats.json").write_text("{not json")
    r = client.get("/api/datasets/dailymed/stats").json()
    assert r["status"] == "not_ready" and "could not be read" in r["reason"]


def test_tac_not_ready_then_ready(client, dirs):
    assert client.get("/api/datasets/tac2017/stats").json()["status"] == "not_ready"
    d = dirs[0] / "tac2017" / "train_xml"
    d.mkdir(parents=True)
    (d / "x.xml").write_text(FIXTURE_TAC, encoding="utf-8")
    r = client.get("/api/datasets/tac2017/stats").json()
    assert r["status"] == "ready" and r["labels_per_split"] == {"train_xml": 1}
    assert r["mentions"] == 1 and r["section_names"] == {"adverse reactions": 1}


def test_trace_parsing_and_categories():
    rows, malformed, preamble = parse_trace(FIXTURE_TRACE)
    assert [r.category for r in rows] == ["from_papers", "not_in_papers",
                                          "from_baseline_review", "unclassified"]
    assert [r.status_kind for r in rows] == ["untested", "ran", "verified", "unknown"]
    assert len(malformed) == 1 and "bad row" in malformed[0]
    assert preamble == ["Fixture preamble line."]


def test_trace_endpoint(client):
    r = client.get("/api/trace").json()
    assert r["status"] == "ready" and len(r["rows"]) == 4
    assert r["counts_by_category"]["not_in_papers"] == 1
    assert r["counts_by_status"]["verified"] == 1


def test_trace_missing_file(dirs, tmp_path):
    settings = Settings(data_dir=dirs[0], artifacts_dir=dirs[1],
                        trace_path=tmp_path / "missing.md", encoder_name="e", classifier_name="c")
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        r = TestClient(app).get("/api/trace").json()
    finally:
        app.dependency_overrides.clear()
    assert r["status"] == "not_ready" and r["rows"] == []


# ---- absolute paths never leave the server ----------------------------------------------
ABS_PATH = re.compile(r"[A-Za-z]:[\\/]|^/(tmp|home|Users|var)/", re.M)


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def test_no_absolute_paths_in_api_messages(client, dirs):
    data, art = dirs
    (data / "dailymed_rx").mkdir()
    with zipfile.ZipFile(data / "dailymed_rx" / "fixture_part.zip", "w") as zf:
        zf.writestr("a.txt", "fixture")
    bodies = [client.get(p).json() for p in (
        "/api/status", "/api/datasets/ddi2013/stats", "/api/datasets/ddi2013/examples",
        "/api/datasets/dailymed/stats", "/api/datasets/tac2017/stats", "/api/trace")]
    (art / "dailymed_stats.json").write_text("{not json")
    bodies.append(client.get("/api/datasets/dailymed/stats").json())
    for body in bodies:
        for s in _strings(body):
            assert str(data) not in s and str(art) not in s and not ABS_PATH.search(s), s
    status = bodies[0]
    assert status["data_dir"] == "data"
    index = {c["id"]: c for c in status["components"]}["index"]
    assert "aakaash/artifacts/index/manifest.json" in index["reason"]
    assert "Phase" not in json.dumps(status)


def test_settings_display_and_scrub(dirs, tmp_path):
    data, art = dirs
    s = Settings(data_dir=data, artifacts_dir=art, trace_path=tmp_path / "PAPER_TRACE.md",
                 encoder_name="tfidf", classifier_name="linear_baseline")
    assert s.display(data / "tac2017") == "data/tac2017"
    assert s.display(art / "index" / "manifest.json") == "aakaash/artifacts/index/manifest.json"
    assert s.display(Path("C:/elsewhere/secret/file.txt")) == "file.txt"
    assert str(tmp_path) not in s.scrub(f"[Errno 2] No such file: '{art / 'x.json'}' in {data}")
    assert "C:" not in s.scrub(r"failed at C:\Users\someone\thing.json now")
