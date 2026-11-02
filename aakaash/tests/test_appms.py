# SOURCE: NOT IN PAPERS. FIXTURES ONLY: every CSV below is hand-written to exercise code paths.
# None of it is APPMS data and none of it may appear in the UI.
import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.config import Settings, get_settings
from api.services import appms as appms_service, medicines
from medsafe import appms

PATIENTS = """patient_id,age_years,gender,state,district,residence_type,primary_condition,secondary_condition,reported_drug_allergy,egfr_category,data_origin
P1,40,Female,StateA,DistX,Urban,Condone,None,None,60-89,SYNTHETIC
P2,70,Male,StateB,DistY,Rural,Condtwo,Condthree,Fixallergy,<30,SYNTHETIC
"""
MEDS = """medication_record_id,patient_id,drug_name,strength,route,indication,frequency,duration_days,start_date_synthetic,data_origin
P1-M1,P1,Alphadrug,5 mg,oral,Ind,Once daily,30,2026-01-01,SYNTHETIC
P1-M2,P1,Betadrug,5 mg,oral,Ind,Once daily,30,2026-01-01,SYNTHETIC
P2-M1,P2,Gammadrug,5 mg,oral,Ind,Once daily,30,2026-01-01,SYNTHETIC
P9-M1,P9,Orphandrug,5 mg,oral,Ind,Once daily,30,2026-01-01,SYNTHETIC
"""
SCEN_HEAD = ("scenario_id,patient_id,drug_a,drug_b,known_interaction_in_seed_rules,severity_label,"
             "interaction_category,mechanism_or_risk,xai_explanation,evidence_source,label_scope,data_origin\n")
SCEN = SCEN_HEAD + """P1-P1,P1,Alphadrug,Betadrug,1,High,Cat,Mech,Do the careful thing,Src,Scope,S
P1-P2,P1,Betadrug,Alphadrug,1,High,Cat,Mech,Do the careful thing,Src,Scope,S
P2-P1,P2,Gammadrug,Alphadrug,0,Not flagged by seed rules,No rule match,x,Nothing matched,Src,Scope,S
"""
RULES = """drug_a,drug_b,severity_label,interaction_category,mechanism_or_risk,explanation_or_action,evidence_source
Alphadrug,Betadrug,High,Cat,Mech,Do the careful thing,Src
Gammadrug,Deltadrug,Critical,Cat2,Mech2,Avoid it,Src2
"""


@pytest.fixture
def client(tmp_path):
    folder = tmp_path / "data" / "appms"
    folder.mkdir(parents=True)
    for name, text in (("patients.csv", PATIENTS), ("medications.csv", MEDS),
                       ("patient_drug_pair_scenarios.csv", SCEN), ("ddi_seed_rules.csv", RULES)):
        (folder / name).write_text(text, encoding="utf-8")
    settings = Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art",
                        trace_path=tmp_path / "t.md", encoder_name="tfidf", classifier_name="x")
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app), settings
    app.dependency_overrides.clear()


def test_loader_types_and_none_values(client):
    _, s = client
    d = appms.load(s.data_dir / "appms")
    assert [p.patient_id for p in d.patients] == ["P1", "P2"]
    assert d.patients[0].secondary_condition is None and d.patients[0].reported_drug_allergy is None
    assert d.patients[1].reported_drug_allergy == "Fixallergy"
    assert d.scenarios[0].flagged and d.scenarios[0].severity == "High"
    assert d.scenarios[2].flagged is False and d.scenarios[2].severity is None
    assert len(d.meds_by_patient["P1"]) == 2


def test_summary_counts(client):
    c, _ = client
    b = c.get("/api/appms/summary").json()
    assert (b["patients"], b["medication_rows"], b["scenarios"], b["rules"]) == (2, 4, 3, 2)
    assert (b["flagged_scenarios"], b["not_flagged_scenarios"]) == (2, 1)
    assert {x["severity"]: x["scenarios"] for x in b["severity"]} == {"Critical": 0, "High": 2, "Moderate": 0}
    assert b["distinct_explanations"] == 2 and b["orphan_medication_rows"] == 1


def test_not_ready_when_folder_missing(tmp_path):
    settings = Settings(data_dir=tmp_path / "nodata", artifacts_dir=tmp_path, trace_path=tmp_path / "t.md",
                        encoder_name="x", classifier_name="x")
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        c = TestClient(app)
        for url in ("/api/appms/summary", "/api/appms/patients", "/api/appms/patients/P1",
                    "/api/appms/lookup?drug_a=a&drug_b=b"):
            b = c.get(url).json()
            assert b["status"] == "not_ready" and b["fix"] == appms_service.FIX
            assert str(tmp_path) not in b["reason"]
    finally:
        app.dependency_overrides.clear()


def test_patients_search_paging_and_detail(client):
    c, _ = client
    assert c.get("/api/appms/patients").json()["total"] == 2
    b = c.get("/api/appms/patients?q=condthree").json()
    assert b["total"] == 1 and b["patients"][0]["patient_id"] == "P2"
    assert c.get("/api/appms/patients?q=gammadrug").json()["total"] == 1   # matches a medication name
    assert c.get("/api/appms/patients?limit=1&offset=1").json()["patients"][0]["patient_id"] == "P2"
    d = c.get("/api/appms/patients/P1").json()
    assert d["patient"]["age_years"] == 40 and [m["drug_name"] for m in d["medications"]] == ["Alphadrug", "Betadrug"]
    assert "patient_id" not in d["medications"][0]
    assert c.get("/api/appms/patients/NOPE").status_code == 404


def test_lookup_match_order_case_and_no_match(client):
    c, _ = client
    for a, b in (("Alphadrug", "Betadrug"), ("betadrug", "ALPHADRUG")):
        r = c.get("/api/appms/lookup", params={"drug_a": a, "drug_b": b}).json()
        assert r["matched"] and r["rule"]["severity"] == "High" and r["rule"]["explanation"] == "Do the careful thing"
        assert r["rule"]["sample_scenarios"] == 2
    r = c.get("/api/appms/lookup", params={"drug_a": "Alphadrug", "drug_b": "Gammadrug"}).json()
    assert r["matched"] is False and r["rule"] is None
    assert r["message"] == "No known interaction found in our rules. This does not mean the combination is safe."
    assert c.get("/api/appms/lookup?drug_a=x").status_code == 422


def test_checker_rule_severity(client, monkeypatch):
    c, s = client
    names = s.artifacts_dir
    names.mkdir(exist_ok=True)
    labels = {sid: {"set_id": sid, "title": "t", "product_names": [n], "active_moieties": [m],
                    "manufacturer": "M", "sections": {}}
              for sid, n, m in (("1", "Alpha", "alphadrug"), ("2", "Beta", "BETADRUG"), ("3", "Other", "zzz"))}
    monkeypatch.setattr(medicines, "get_index", lambda settings: object())
    monkeypatch.setattr(medicines, "load_label", lambda settings, idx, sid: labels[sid])
    body = c.post("/api/checker", json={"set_ids": ["1", "2", "3"]}).json()
    assert body["appms"]["status"] == "ready"
    first = body["pairs"][0]
    assert first["appms"]["severity"] == "high" and "Do the careful thing" in first["appms"]["explanation"]
    assert all(p["appms"]["severity"] is None for p in body["pairs"][1:])
