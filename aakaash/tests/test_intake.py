# SOURCE: NOT IN PAPERS. FIXTURES ONLY: every medicine, label, rule, allergy and date below is
# hand-written (tests/fixtures_catalogue.py and this file) to exercise code paths. None of it is real
# data and none of it may appear in the UI.
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api import auth, db
from api.app import app
from api.config import Settings, get_settings
from api.services import catalogue as catalogue_service, intake, medicines
from api.schemas import CourseIn
from medsafe.risk import ALLERGY_LEVEL, RULE_LEVEL, allergy_matches, highest
from medsafe.spl import parse_label

from fixtures_catalogue import INJECTION, LABELS, ROWS, lab, row, write_artifacts

PW = "correct horse battery"
TODAY = date.today()

EXTRA_ROWS = [
    row("40", "Nacltab Tablet", "Sodium Chloride (500mg)"),           # tablet; only an injection label exists
    row("41", "Asprin 75 Tablet", "Aspirin (75mg)"),                  # only a combination label carries aspirin
    row("42", "Penbenz Injection", "Benzathine Penicillin G (1200000IU)", pack="vial of 1 Injection"),
]
EXTRA_LABELS = [lab("L-asa-caf", "Aspirin and Caffeine", ["ASPIRIN", "CAFFEINE"], ["aspirin", "caffeine"])]

FULL = {"indications": [{"text": "Indicated for fixture pain. Second sentence."}],
        "boxed_warning": [{"text": "FIXTURE BOXED WARNING TEXT."}],
        "dosage_administration": [{"text": "Take one fixture tablet every 6 hours."}],
        "patient_counseling": [{"text": "Tell patients fixture advice."}],
        "drug_interactions": [{"text": "Acetaminophen may raise the INR."}]}
PARSED = {sid: {"set_id": sid, "sections": FULL} for sid in
          ("L-apap-1", "L-apap-2", "L-apap-inj", "L-warf", "L-metf", "L-albut", "L-nacl", "L-cacl", "L-kcl",
           "L-asa-caf", "L-combo")}

RULES = ("Warfarin,Acetaminophen,Moderate,Bleeding,Raised INR,Monitor INR,Src\n"
         "Warfarin,Metformin,Critical,Fixture,Fixture risk,Fixture action,Src\n")


def _appms(folder, rules=RULES):
    folder.mkdir(parents=True)
    # header-only sample files: the rules load, and no sample patient is copied into a new account
    (folder / "patients.csv").write_text(
        "patient_id,age_years,gender,state,district,residence_type,primary_condition,secondary_condition,"
        "reported_drug_allergy,egfr_category\n", encoding="utf-8")
    (folder / "medications.csv").write_text(
        "medication_record_id,patient_id,drug_name,strength,route,indication,frequency,duration_days\n", encoding="utf-8")
    (folder / "patient_drug_pair_scenarios.csv").write_text(
        "scenario_id,patient_id,drug_a,drug_b,known_interaction_in_seed_rules,severity_label,interaction_category,"
        "mechanism_or_risk,xai_explanation\n", encoding="utf-8")
    (folder / "ddi_seed_rules.csv").write_text(
        "drug_a,drug_b,severity_label,interaction_category,mechanism_or_risk,explanation_or_action,evidence_source\n"
        + rules, encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-anywhere-else")
    settings = Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art", trace_path=tmp_path / "t.md",
                        encoder_name="tfidf", classifier_name="x")
    _appms(settings.data_dir / "appms")
    write_artifacts(settings.artifacts_dir, ROWS + EXTRA_ROWS, LABELS + EXTRA_LABELS)
    monkeypatch.setattr(medicines, "load_label", lambda s, idx, sid: PARSED[sid])
    app.dependency_overrides[get_settings] = lambda: settings
    catalogue_service.clear_cache()
    medicines.clear_cache()
    auth.reset_rate_limit()
    yield settings
    app.dependency_overrides.clear()
    catalogue_service.clear_cache()
    medicines.clear_cache()
    db.dispose_all()


def sign_in(email="a@example.com"):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": email, "password": PW}).status_code in (200, 201)
    return c


def add_record(c, **kw):
    r = c.post("/api/medicine-records", json={"display_name": kw.pop("display_name", "x"), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def analyze(c, *ids, **extra):
    r = c.post("/api/analyze", json={"medicines": [{"catalogue_id": i} for i in ids], **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---- level rules (pure) -----------------------------------------------------------------------
def test_level_mapping_and_overall_is_highest():
    assert RULE_LEVEL == {"moderate": "Medium", "high": "High", "critical": "Critical"}
    assert ALLERGY_LEVEL == {"mild": "Medium", "moderate": "High", "severe": "Critical", "unknown": "High"}
    assert highest(["Medium", "Critical", "High"]) == "Critical"
    assert highest(["Medium", None]) == "Medium"
    assert highest([]) is None


@pytest.mark.parametrize("allergen,ingredient,expected", [
    ("Amoxycillin", "Amoxicillin", True),                 # approved synonym
    ("amoxicillin", "Amoxycillin", True),
    ("Amoxycillin", "Amoxicillin Trihydrate", True),      # salt word dropped
    ("Paracetamol", "Acetaminophen", True),
    ("Penicillin", "Amoxicillin", False),                 # same class, different name: not checked
    ("penicillin", "Benzathine Penicillin G", True),      # whole words inside the name
    ("Sodium", "Sodium Chloride", False),                 # a bare counter-ion never matches by words
    ("para", "Paracetamol", False),                       # part of a word is not a match
    ("Aspirin", "Aspirin", True),
])
def test_allergy_match_by_name_only(allergen, ingredient, expected):
    assert allergy_matches(allergen, ingredient) is expected


def test_course_end_date_from_duration():
    rec = intake.course_record(CourseIn(catalogue_id="1", duration_days=5, food="after food"), TODAY)
    assert (rec.start_date, rec.end_date, rec.notes) == (TODAY, TODAY + timedelta(days=4), "Food: after food")
    rec = intake.course_record(CourseIn(catalogue_id="1", start_date=date(2026, 1, 1)), TODAY)
    assert (rec.start_date, rec.end_date) == (date(2026, 1, 1), None)
    with pytest.raises(ValueError):
        CourseIn(catalogue_id="1", duration_days=5, end_date=TODAY)


# ---- analysis ---------------------------------------------------------------------------------
def test_compares_with_current_medicines_and_among_new_ones(env):
    c = sign_in()
    add_record(c, catalogue_id="14", start_date=str(TODAY - timedelta(days=5)))            # current, Warfa 5
    add_record(c, catalogue_id="5", start_date="2025-01-01", end_date="2025-01-10")       # past: not compared
    add_record(c, display_name="Mysterydrug")                                             # no dates: included
    body = analyze(c, "1", "20")  # Dolotest 650 Tablet and Parasyp 650 Syrup, both paracetamol
    assert body["status"] == "ready" and body["pairs_checked"] == 2 * 2 + 1
    roles = {(m["medicine"]["name"], m["role"]) for m in body["medicines"]}
    assert roles == {("Dolotest 650 Tablet", "new"), ("Parasyp 650 Syrup", "new"),
                     ("Warfa 5 Tablet", "current"), ("Mysterydrug", "current")}
    mystery = next(m for m in body["medicines"] if m["medicine"]["name"] == "Mysterydrug")
    assert mystery["dates_not_entered"] and mystery["checked_by_name_only"]
    names = lambda p: {p["a"]["name"], p["b"]["name"]}
    warf = [p for p in body["pairs"] if "Warfa 5 Tablet" in names(p)]
    assert len(warf) == 2 and all(p["level"] == "Medium" for p in warf)                  # rules say Moderate
    assert warf[0]["hits"][0]["rule_tier"] == "moderate" and warf[0]["hits"][0]["level"] == "Medium"
    assert warf[0]["text_match"]["matches_total"] >= 1                                    # label sentence, separate
    new_pair = next(p for p in body["pairs"] if names(p) == {"Dolotest 650 Tablet", "Parasyp 650 Syrup"})
    assert new_pair["a_role"] == new_pair["b_role"] == "new"
    assert new_pair["shared_ingredients"] == ["Paracetamol"] and new_pair["level"] is None
    assert body["overall"] == "Medium" and "Moderate" not in str([p["level"] for p in body["pairs"]])
    assert body["disclaimer"] == "Informational only. Not a substitute for advice from your doctor or pharmacist."


def test_overall_is_the_highest_level(env):
    c = sign_in()
    add_record(c, catalogue_id="14", start_date=str(TODAY))
    c.post("/api/allergies", json={"allergen": "Paracetamol", "severity": "mild"})
    body = analyze(c, "1", "5")  # paracetamol (Medium rule + mild allergy) and metformin (Critical rule)
    assert sorted(p["level"] for p in body["pairs"] if p["level"]) == ["Critical", "Medium"]
    assert [f["level"] for f in body["allergy_findings"]] == ["Medium"]
    assert body["overall"] == "Critical"
    assert body["overall_text"] == "This may be a serious risk. Talk to your doctor or pharmacist before taking this medicine."
    assert body["levels"] == ["Medium", "High", "Critical"]


def test_no_finding_sentence_and_never_safe(env):
    c = sign_in()
    body = analyze(c, "15")
    assert body["overall"] is None and body["pairs"] == [] and body["allergy_findings"] == []
    assert body["overall_text"] == "No known interaction found in our rules. This does not mean the combination is safe."
    assert "Safe" not in body["overall_text"] and "Low" not in str(body["levels"])


@pytest.mark.parametrize("severity,level", list(ALLERGY_LEVEL.items()))
def test_allergy_level_follows_recorded_severity(env, severity, level):
    c = sign_in()
    c.post("/api/allergies", json={"allergen": "Amoxicillin", "severity": severity, "reaction": "Rash"})
    body = analyze(c, "9")  # Amoxyna Tablet: Amoxycillin
    f = body["allergy_findings"][0]
    assert (f["allergen"], f["level"], f["ingredients"], f["reaction"]) == ("Amoxicillin", level, ["Amoxycillin"], "Rash")
    assert f["note"] == "Matched by name only. Related medicines in the same class are not checked."
    assert body["overall"] == level


def test_penicillin_allergy_does_not_match_amoxicillin_but_matches_penicillin_g(env):
    c = sign_in()
    c.post("/api/allergies", json={"allergen": "Penicillin", "severity": "severe"})
    assert analyze(c, "9")["allergy_findings"] == []
    assert analyze(c, "42")["allergy_findings"][0]["level"] == "Critical"


def test_client_supplied_current_medicines_and_allergies_are_ignored(env):
    c = sign_in()
    body = analyze(c, "1", current_medicines=[{"catalogue_id": "14"}],
                   allergies=[{"allergen": "Paracetamol", "severity": "severe"}])
    assert body["pairs"] == [] and body["allergy_findings"] == [] and body["allergies_checked"] == 0
    assert [m["role"] for m in body["medicines"]] == ["new"]


def test_ownership_isolation(env):
    a, b = sign_in("a@example.com"), sign_in("b@example.com")
    add_record(b, catalogue_id="14", start_date=str(TODAY))
    b.post("/api/allergies", json={"allergen": "Paracetamol", "severity": "severe"})
    body = analyze(a, "1")
    assert body["pairs"] == [] and body["allergy_findings"] == [] and body["allergies_checked"] == 0
    assert a.get("/api/medicine-records").json() == []
    for method, url, kw in (("post", "/api/analyze", {"json": {"medicines": [{"catalogue_id": "1"}]}}),
                            ("post", "/api/medicine-records/batch", {"json": {"items": [{"catalogue_id": "1"}]}}),
                            ("get", "/api/medicine/1/details", {})):
        assert getattr(TestClient(app), method)(url, **kw).status_code == 401


def test_duplicate_and_unknown_ids(env):
    c = sign_in()
    assert c.post("/api/analyze", json={"medicines": [{"catalogue_id": "1"}, {"catalogue_id": "1"}]}).status_code == 422
    assert c.post("/api/analyze", json={"medicines": [{"catalogue_id": "999"}]}).status_code == 404
    assert c.post("/api/analyze", json={"medicines": []}).status_code == 422


# ---- adding -----------------------------------------------------------------------------------
def test_critical_needs_acknowledgement_then_adds(env):
    c = sign_in()
    c.post("/api/allergies", json={"allergen": "Amoxycillin", "severity": "severe"})
    items = [{"catalogue_id": "9", "source": "scanned", "duration_days": 5, "frequency": "BD", "food": "after food"}]
    r = c.post("/api/medicine-records/batch", json={"items": items})
    assert r.status_code == 409 and "I have read this warning" in r.json()["detail"]
    assert c.get("/api/medicine-records").json() == []
    r = c.post("/api/medicine-records/batch", json={"items": items, "acknowledged_warning": True})
    assert r.status_code == 201 and r.json()["overall"] == "Critical"
    m = r.json()["added"][0]
    assert (m["display_name"], m["source"], m["frequency"], m["notes"]) == ("Amoxyna Tablet", "scanned", "BD", "Food: after food")
    assert (m["start_date"], m["end_date"]) == (str(TODAY), str(TODAY + timedelta(days=4)))
    assert m["ingredients"] == ["Amoxycillin"] and m["status"] == "current"


def test_non_critical_adds_without_acknowledgement(env):
    c = sign_in()
    r = c.post("/api/medicine-records/batch", json={"items": [{"catalogue_id": "1"}, {"catalogue_id": "15"}]})
    assert r.status_code == 201 and [m["display_name"] for m in r.json()["added"]] == ["Dolotest 650 Tablet", "Asthalin Inhaler"]
    assert all(m["source"] == "typed" and m["start_date"] == str(TODAY) and m["end_date"] is None for m in r.json()["added"])


def test_no_endpoint_accepts_an_image():
    for path, ops in app.openapi()["paths"].items():
        for op in ops.values():
            content = op.get("requestBody", {}).get("content", {})
            assert set(content) <= {"application/json"}, (path, content)
            assert "binary" not in str(content) and "base64" not in str(content), path


# ---- medicine details -------------------------------------------------------------------------
def test_details_same_form_label_shows_verbatim_instructions(env):
    d = sign_in().get("/api/medicine/1/details").json()
    g = d["ingredients"][0]
    assert d["status"] == "ready" and g["label"]["set_id"] == "L-apap-2" and g["mismatch"] is None
    assert g["indications"]["text"] == "Indicated for fixture pain. Second sentence."
    assert [s["key"] for s in g["instructions"]] == ["dosage_administration", "patient_counseling"]
    assert g["instructions"][0]["text"] == "Take one fixture tablet every 6 hours."            # verbatim
    assert g["boxed_warning"]["text"] == "FIXTURE BOXED WARNING TEXT." and g["withheld_note"] is None


@pytest.mark.parametrize("cid,mismatch,note", [
    ("40", "wrong_form", "No US label in the same form is loaded"),           # tablet, injection label only
    ("41", "combination_label", "No US label in the same form is loaded"),    # aspirin, aspirin + caffeine label
])
def test_details_withhold_dosage_from_other_form_or_product(env, cid, mismatch, note):
    g = sign_in().get(f"/api/medicine/{cid}/details").json()["ingredients"][0]
    assert g["mismatch"] == mismatch and g["instructions"] == [] and note in g["withheld_note"]
    assert g["indications"] is not None and g["mismatch_note"]                 # indications may still be shown
    assert "fixture tablet every 6 hours" not in str(g)


def test_details_combination_brand_with_single_ingredient_label(env):
    d = sign_in().get("/api/medicine/6/details").json()  # Metfocomb: metformin + glimepiride
    met, gli = d["ingredients"]
    assert met["mismatch"] == "single_for_combination" and met["instructions"] == []
    assert "same combination" in met["withheld_note"]
    assert gli["label"] is None and gli["form_match"] == "no_label"
    assert d["composition_incomplete"]


# ---- label parser: instruction sections -------------------------------------------------------
SPL = b"""<?xml version="1.0"?>
<document xmlns="urn:hl7-org:v3"><setId root="fixture-set"/><title>Fixturol</title>
<component><structuredBody>
<component><section><code code="34067-9"/><title>INDICATIONS</title><text>For fixture pain.</text></section></component>
<component><section><code code="34068-7"/><title>2 DOSAGE AND ADMINISTRATION</title><text>One tablet daily.</text></section></component>
<component><section><code code="42232-9"/><title>PRECAUTIONS</title><text>General.</text>
  <component><section><code code="34076-0"/><title>Information for Patients</title><text>Advise patients.</text>
    <component><section><code code="42228-7"/><title>Pregnancy</title><text>Pregnancy sentence.</text></section></component>
  </section></component></section></component>
<component><section><code code="42231-1"/><title>MEDICATION GUIDE</title><text>Guide text.</text></section></component>
<component><section><code code="59845-8"/><title>INSTRUCTIONS FOR USE</title><text>Steps.</text></section></component>
<component><section><code code="99999-9"/><title>Patient Counseling Information</title><text>By title.</text></section></component>
</structuredBody></component></document>"""


def test_parser_reads_instruction_sections():
    s = parse_label(SPL)["sections"]
    text = lambda k, i=0: s[k][i]["text"].splitlines()   # each text starts with the section title
    assert text("dosage_administration") == ["2 DOSAGE AND ADMINISTRATION", "One tablet daily."]
    assert text("patient_counseling") == ["Information for Patients", "Advise patients."]  # nested Pregnancy cut out
    assert text("patient_counseling", 1)[-1] == "By title." and s["patient_counseling"][1]["method"] == "title_fallback"
    assert text("specific_populations")[-1] == "Pregnancy sentence."
    assert text("patient_information")[-1] == "Guide text."
    assert text("instructions_for_use")[-1] == "Steps."
    assert "Advise patients" not in s["precautions"][0]["text"]
