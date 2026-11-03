# SOURCE: NOT IN PAPERS. FIXTURES ONLY: a tiny random checkpoint and hand-written metrics JSON in temp
# folders. These tests prove plumbing and the not_ready paths, not model quality.
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.config import Settings, get_settings
from api.services import appms as appms_service, catalogue as catalogue_service, ddi as ddi_service, medicines

from fixtures_catalogue import PARSED, write_artifacts
from ddi_fixture import make_checkpoint, metrics_json
from test_catalogue import _rules

SENT = "Warfarin may raise the level of aspirin."


@pytest.fixture(scope="module")
def ckpt(tmp_path_factory):
    return make_checkpoint(tmp_path_factory.mktemp("ddi_ckpt"))


def settings_for(tmp_path, model_dir=None, metrics_dir=None):
    return Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art", trace_path=tmp_path / "t.md",
                    encoder_name="tfidf", classifier_name="focal",
                    ddi_model_dir_override=model_dir, ddi_metrics_dir_override=metrics_dir)


@pytest.fixture
def make_client(tmp_path):
    def build(**kw):
        s = settings_for(tmp_path, **kw)
        app.dependency_overrides[get_settings] = lambda: s
        ddi_service.clear_cache()
        return TestClient(app), s
    yield build
    app.dependency_overrides.clear()
    ddi_service.clear_cache()


def post(c, sentence=SENT, d1="warfarin", d2="aspirin", explain=False):
    return c.post("/api/ddi/classify", json={"sentence": sentence, "drug_1": d1, "drug_2": d2, "explain": explain})


def test_classify_not_ready_without_checkpoint(make_client):
    c, _ = make_client()
    r = post(c)
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "not_ready" and "artifacts/models" in b["fix"] and b["predicted"] is None
    assert b["probabilities"] is None and b["model"] is None


def test_metrics_not_ready_without_files(make_client):
    c, _ = make_client()
    b = c.get("/api/ddi/metrics").json()
    assert b["status"] == "not_ready" and b["runs"] == [] and "artifacts/metrics" in b["fix"]


def test_status_reports_missing_and_present_checkpoint(make_client, ckpt):
    c, _ = make_client()
    comp = {x["id"]: x for x in c.get("/api/status").json()["components"]}["ddi_model"]
    assert comp["status"] == "not_ready" and "No checkpoint" in comp["reason"]
    c, _ = make_client(model_dir=ckpt)
    comp = {x["id"]: x for x in c.get("/api/status").json()["components"]}["ddi_model"]
    assert comp["status"] == "ready" and comp["detail"]["smoke_test"] == "yes"


def test_classify_ready_markable_and_not_markable(make_client, ckpt):
    c, _ = make_client(model_dir=ckpt)
    b = post(c).json()
    assert b["status"] == "ready" and b["label"] == "Model estimate"
    assert b["marked_text"] == "<e1>Warfarin</e1> may raise the level of <e2>aspirin</e2>."
    assert set(b["probabilities"]) == {"effect", "mechanism", "advise", "int", "false"}
    assert sum(b["probabilities"].values()) == pytest.approx(1.0)
    assert b["predicted"] == max(b["probabilities"], key=b["probabilities"].get)
    assert b["model"]["smoke_test"] is True and b["model"]["version"] == "fixture-tiny" and b["words"] is None
    assert b["timing_ms"]["load"] > 0
    again = post(c).json()                                     # served from memory: same answer, no reload
    assert again["probabilities"] == b["probabilities"]
    nm = post(c, d2="ibuprofen").json()
    assert nm["status"] == "not_markable" and nm["predicted"] is None and nm["probabilities"] is None


def test_classify_with_explanation(make_client, ckpt, monkeypatch):
    monkeypatch.setenv("MEDSAFE_DDI_IG_STEPS", "6")
    c, _ = make_client(model_dir=ckpt)
    b = post(c, explain=True).json()
    assert b["status"] == "ready" and [w["text"] for w in b["words"]][0] == "Warfarin"
    assert b["words"][0]["is_drug"] is True and b["ig"]["n_steps"] >= 1 and "explain" in b["timing_ms"]


def test_request_validation(make_client):
    c, _ = make_client()
    assert c.post("/api/ddi/classify", json={"sentence": "", "drug_1": "a", "drug_2": "b"}).status_code == 422
    assert c.post("/api/ddi/classify", json={"sentence": "x"}).status_code == 422


def test_metrics_read_from_json(make_client, tmp_path):
    m = tmp_path / "metrics"
    m.mkdir()
    (m / "ddi_focal.json").write_text(json.dumps(metrics_json("focal")))
    (m / "ddi_ce.json").write_text(json.dumps(metrics_json("ce")))
    (m / "ddi_search.json").write_text(json.dumps({"smoke_test": True, "runs": {"k": {
        "config": {"loss": "ce", "gamma": 0.0, "alpha": "none", "lr_encoder": 3e-5, "lr_head": 5e-4},
        "best_epoch": 1, "dev_micro": {"f1": 0.4}}}}))
    c, _ = make_client(metrics_dir=m)
    b = c.get("/api/ddi/metrics").json()
    assert b["status"] == "ready" and [r["name"] for r in b["runs"]] == ["ce", "focal"]
    r = b["runs"][1]
    assert r["smoke_test"] is True and r["test"]["micro"]["f1"] == pytest.approx(1 / 3)
    assert r["test"]["per_class"][0]["label"] == "effect" and r["faithfulness"]["label"] == "a faithfulness proxy"
    assert b["search"][0]["dev_micro_f1"] == 0.4 and b["search_smoke_test"] is True


def test_unreadable_metrics_file_is_not_ready(make_client, tmp_path):
    m = tmp_path / "metrics"
    m.mkdir()
    (m / "ddi_focal.json").write_text("{not json")
    c, _ = make_client(metrics_dir=m)
    b = c.get("/api/ddi/metrics").json()
    assert b["status"] == "not_ready" and "could not be read" in b["reason"]


def test_risk_code_never_imports_the_classifier():
    root = Path(__file__).resolve().parents[1]
    for rel in ("medsafe/risk.py", "api/services/intake.py", "medsafe/appms.py", "medsafe/appms_match.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert not re.search(r"ddi_model|services\.ddi|from \. import .*\bddi\b|explain", src), rel


def test_checker_levels_identical_with_and_without_the_model(tmp_path, ckpt, monkeypatch):
    results = []
    for model_dir in (None, ckpt):
        s = settings_for(tmp_path / ("with" if model_dir else "without"), model_dir=model_dir)
        write_artifacts(s.artifacts_dir)
        _rules(s, "Warfarin,Acetaminophen,High,Bleeding,Raised INR,Monitor INR,Src\n")
        monkeypatch.setattr(medicines, "load_label", lambda settings, idx, sid: PARSED[sid])
        app.dependency_overrides[get_settings] = lambda s=s: s
        catalogue_service.clear_cache()
        medicines.clear_cache()
        ddi_service.clear_cache()
        c = TestClient(app)
        # classify a label sentence first, so the model is loaded when the checker runs
        post(c, "Acetaminophen may raise the level of warfarin.", "warfarin", "acetaminophen")
        results.append(c.post("/api/checker", json={"catalogue_ids": ["1", "14"]}).json())
    app.dependency_overrides.clear()
    assert results[0] == results[1]
    assert results[0]["pairs"][0]["appms"]["severity"] == "high"


def test_ungated_real_checkpoint_is_not_ready(make_client, tmp_path):
    # A non-smoke checkpoint with no passed quality gate (e.g. trained before the tokenizer fix) is not served.
    import shutil

    d = tmp_path / "old_ckpt"
    shutil.copytree(make_checkpoint(tmp_path / "src", smoke=False), d)
    c, _ = make_client(model_dir=d)
    b = post(c).json()
    assert b["status"] == "not_ready" and b["predicted"] is None and b["probabilities"] is None
    cfg = json.loads((d / "config.json").read_text())
    cfg["quality_gate"] = {"passed": True}
    (d / "config.json").write_text(json.dumps(cfg))
    ddi_service.clear_cache()
    assert post(c).json()["status"] == "ready"


def test_ungated_real_metrics_are_not_listed(make_client, tmp_path):
    m = tmp_path / "metrics"
    m.mkdir()
    (m / "ddi_focal.json").write_text(json.dumps(metrics_json("focal", smoke=False)))
    c, _ = make_client(metrics_dir=m)
    b = c.get("/api/ddi/metrics").json()
    assert b["status"] == "not_ready" and b["runs"] == [] and "quality gate" in b["reason"]
    j = metrics_json("focal", smoke=False)
    j["quality_gate"] = {"passed": True}
    (m / "ddi_focal.json").write_text(json.dumps(j))
    assert c.get("/api/ddi/metrics").json()["status"] == "ready"
