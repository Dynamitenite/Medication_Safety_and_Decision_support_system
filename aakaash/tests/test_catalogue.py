# SOURCE: NOT IN PAPERS. FIXTURES ONLY (tests/fixtures_catalogue.py): hand-written rows and labels.
import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.config import Settings, get_settings
from api.services import appms as appms_service, catalogue as catalogue_service, medicines
from medsafe.appms_match import ingredient_keys
from medsafe.catalogue import (FLAG_CONFLICT, FLAG_INCOMPLETE, Catalogue, LabelLinker, build,
                               composition_source, parse_interactions, parse_item, strength_key)
from medsafe.synonyms import KINDS, canonical, read_rows

from fixtures_catalogue import LABELS, PARSED, ROWS, lab, row, write_artifacts


@pytest.fixture(scope="module")
def built():
    return build(ROWS, LABELS)


@pytest.fixture(scope="module")
def cat(built):
    return Catalogue(built[0])


def ix(cat, name):
    return cat.names.index(name)


# ---- composition parsing ---------------------------------------------------------------------
def test_parse_single_item_and_odd_formats():
    assert parse_item("Paracetamol (650mg)") == {"name": "Paracetamol", "strength": "650mg", "raw": "Paracetamol (650mg)"}
    assert parse_item("  Amoxycillin   (500mg) ")["raw"] == "Amoxycillin (500mg)"
    assert parse_item("Omeprazole (NA)")["strength"] is None                       # not stated
    v = parse_item("Hepatitis B Vaccine (rDNA) (NA)")                              # bracket inside the name
    assert v["name"] == "Hepatitis B Vaccine (rDNA)" and v["strength"] is None
    assert parse_item("Xylometazoline (0.05% w/v)")["strength"] == "0.05% w/v"
    assert parse_item("Bacillus Clausii (2Billion Spores)")["strength"] == "2Billion Spores"
    assert parse_item("No strength here") is None and parse_item("(5mg)") is None


def test_combination_uses_full_composition_and_flags():
    used, short, flags = composition_source(row("x", "x", "A (1mg) ", " B (2mg)", salt="A (1mg) + B (2mg) + C (3mg)"))
    assert used == ["A (1mg)", "B (2mg)", "C (3mg)"] and flags == 0
    used, _, flags = composition_source(row("x", "x", "A (1mg) ", " B (2mg)"))
    assert used == ["A (1mg)", "B (2mg)"] and flags == FLAG_INCOMPLETE            # two listed, no full field
    _, _, flags = composition_source(row("x", "x", "A (1mg)"))
    assert flags == 0                                                              # one listed: complete
    _, _, flags = composition_source(row("x", "x", "A (1mg) ", " B (2mg)", salt="C (3mg) + D (4mg)"))
    assert flags == FLAG_CONFLICT


def test_build_counts_and_no_guessing(built):
    data, rep = built
    assert rep["rows"] == len(ROWS) and rep["unparseable_items"] == 0
    assert rep["composition_incomplete"] == 1 and rep["composition_conflict"] == 1   # row 6; row 11
    assert rep["discontinued"] == 1
    bad, rep2 = build([row("x", "Odd", "Paracetamol 650mg")], LABELS)
    assert rep2["unparseable_items"] == 1 and rep2["unparseable_sample"] == [("x", "Paracetamol 650mg")]
    assert bad["compositions"][0]["items"] == []                                   # counted, not guessed


def test_strength_compared_as_written():
    assert strength_key("100 IU/ml") == strength_key("100iu/ML") == "100iu/ml"
    assert strength_key("100IU/ml") != strength_key("100IU") and strength_key(None) is None


def test_secondary_interactions_drop_brands():
    pairs, ok = parse_interactions(ROWS[13]["drug_interactions"])
    assert ok and pairs == [["Paracetamol", "MODERATE"], ["Aspirin", "SERIOUS"]]
    assert parse_interactions('{"drug": [], "brand": [], "effect": []}') == ([], True)
    assert parse_interactions("{not json") == ([], False)


# ---- synonyms and salt words -----------------------------------------------------------------
def test_synonym_file_is_exact_and_auditable():
    rows = read_rows()
    assert len(rows) == 32 and all(r["kind"] in KINDS for r in rows)
    assert sum(r["kind"] == "spelling fix" for r in rows) == 2
    assert canonical("Paracetamol") == "acetaminophen" and canonical("SALBUTAMOL") == "albuterol"
    assert canonical("Adrenaline") == "epinephrine" and canonical("frusemide") == "furosemide"
    assert canonical("Amoxycillin") == "amoxicillin" and canonical("Tazobactum") == "tazobactam"
    assert canonical("Levo-Carnitine") == "levocarnitine"
    assert canonical("Paracetamols") == "paracetamols"                          # no fuzzy matching
    assert canonical("Luliconazole") == "luliconazole"


@pytest.mark.parametrize("a,b", [("sodium chloride", "sodium citrate"), ("calcium chloride", "calcium acetate"),
                                 ("potassium chloride", "potassium citrate")])
def test_salts_of_one_metal_never_link_to_each_other(a, b, built):
    assert not ingredient_keys(a) & ingredient_keys(b)
    linker = LabelLinker(LABELS)
    la, lb = ({LABELS[i]["set_id"] for i in linker.link(canonical(x))["label_idx"]} for x in (a, b))
    assert not la & lb
    by_key = {x["key"]: x for x in built[0]["ingredients"]}
    if a in by_key and b in by_key:
        assert not set(by_key[a]["link"]["set_ids"]) & set(by_key[b]["link"]["set_ids"])


def test_salt_word_still_stripped_from_a_drug_name():
    assert "warfarin" in ingredient_keys("WARFARIN SODIUM")
    assert ingredient_keys("sodium chloride") == {"sodium chloride"}


# ---- linking ---------------------------------------------------------------------------------
def test_linking_default_label_and_single_ingredient_first(built):
    by_key = {x["key"]: x for x in built[0]["ingredients"]}
    apap = by_key["acetaminophen"]
    assert apap["name"] == "Paracetamol" and apap["us_name"] == "acetaminophen"
    assert apap["link"]["set_ids"] == ["L-apap-2", "L-apap-1"]            # more sections first
    assert by_key["metformin"]["link"]["set_ids"] == ["L-metf"]            # combination label not used
    assert by_key["metformin"]["link"]["method"] == "active moiety"
    assert by_key["albuterol"]["link"]["set_ids"] == ["L-albut"]          # Salbutamol via the synonym list
    assert by_key["sodium citrate"]["link"]["set_ids"] == []              # label without text is never linked
    assert by_key["glimepiride"]["link"]["set_ids"] == []


# ---- suggest ---------------------------------------------------------------------------------
def test_dolo_matches_only_when_a_brand_starts_with_it(cat):
    m, s = cat.suggest("dolo")
    assert [r["name"] for r in m] == ["Dolotest 650 Tablet"] and s == []
    other = Catalogue(build([r for r in ROWS if r["id"] != "1"], LABELS)[0])
    m, s = other.suggest("dolo")
    assert m == [] and all(r["match"] in ("substring", "fuzzy") for r in s)


def test_met_shows_matches(cat):
    m, s = cat.suggest("met")
    names = [r["name"] for r in m]
    assert names[:4] == ["Metfo 500 Tablet", "Metfocomb Tablet"] + names[2:4] and s == []
    assert {r["match"] for r in m} <= {"prefix", "word", "ingredient"}
    assert all(r["composition"] and r["type"] == "allopathy" for r in m)


def test_typo_goes_to_similar_never_matches(cat):
    m, s = cat.suggest("paracetmol")
    assert m == [] and 0 < len(s) <= 4
    assert all(r["match"] == "fuzzy" and "Paracetamol" in r["ingredients"] for r in s)
    assert cat.suggest("zzqx") == ([], [])


def test_length_rules_and_discontinued_last(cat):
    assert cat.suggest("m") == ([], [])                                    # under 2 characters
    assert cat.suggest("me")[0]                                            # prefix from 2
    assert cat.suggest("xq")[1] == []                                      # no similar under 3
    m, _ = cat.suggest("paracetamol", 20)                                  # ingredient-name matches
    assert m and all(r["match"] == "ingredient" for r in m)
    assert m[-1]["name"] == "Oldpara 650 Tablet" and m[-1]["discontinued"]
    assert all(not r["discontinued"] for r in m[:-1])
    assert cat.suggest("acetaminophen", 20)[0]                             # the US name finds Indian brands


# ---- alternatives ----------------------------------------------------------------------------
def test_alternatives_same_strength_by_price(cat):
    a = cat.alternatives(ix(cat, "Dolotest 650 Tablet"))
    assert [r["name"] for r in a["same"]] == ["Calpara 650 Tablet"]          # discontinued hidden
    r = a["same"][0]
    assert r["price_difference"] == -10.0 and r["different_pack_size"]
    assert [g["composition"] for g in a["other_strength"]] == ["Paracetamol (500mg)"]
    b = cat.alternatives(ix(cat, "Dolotest 650 Tablet"), include_discontinued=True)
    assert [r["name"] for r in b["same"]] == ["Oldpara 650 Tablet", "Calpara 650 Tablet"]


def test_combination_matches_only_full_set_and_flags_incomplete(cat):
    a = cat.alternatives(ix(cat, "Glimetwo Tablet"))
    assert [r["name"] for r in a["same"]] == ["Metfocomb Tablet"]            # not Glimet (3), not Metfo (1)
    assert a["same"][0]["composition_incomplete"] and a["flagged_in_same"] == 1
    assert cat.alternatives(ix(cat, "Metfo 500 Tablet"))["same"] == []


def test_strength_not_stated_never_same_strength(cat):
    a = cat.alternatives(ix(cat, "Amoxyna Tablet"))
    assert a["strength_stated"] is False and a["same"] == []


# ---- API -------------------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art",
                        trace_path=tmp_path / "t.md", encoder_name="tfidf", classifier_name="x")
    app.dependency_overrides[get_settings] = lambda: settings
    catalogue_service.clear_cache()
    medicines.clear_cache()
    yield TestClient(app), settings
    app.dependency_overrides.clear()
    catalogue_service.clear_cache()
    medicines.clear_cache()


def test_not_ready_without_catalogue(client):
    c, _ = client
    for r in (c.get("/api/medicine/suggest?q=dolo"), c.get("/api/medicine/1"), c.get("/api/medicine/1/alternatives"),
              c.get("/api/catalogue/summary"), c.post("/api/checker", json={"catalogue_ids": ["1", "2"]})):
        assert r.status_code == 200 and r.json()["status"] == "not_ready"
        assert "build_catalogue.py" in r.json()["fix"]


def test_brand_alternatives_and_summary_endpoints(client):
    c, s = client
    write_artifacts(s.artifacts_dir)
    b = c.get("/api/medicine/suggest?q=dolo").json()
    assert b["status"] == "ready" and [x["id"] for x in b["matches"]] == ["1"] and b["similar"] == []
    d = c.get("/api/medicine/1").json()
    assert d["brand"]["name"] == "Dolotest 650 Tablet" and d["price_note"] == "Prices may be out of date."
    ing = d["ingredient_details"][0]
    assert ing["name"] == "Paracetamol" and ing["us_name"] == "acetaminophen"
    assert [l["set_id"] for l in ing["labels"]] == ["L-apap-2", "L-apap-1"] and ing["labels"][0]["default"]
    w = c.get("/api/medicine/14").json()
    assert [x["drug"] for x in w["secondary_interactions"]] == ["Paracetamol", "Aspirin"]
    assert "origin not stated" in w["secondary_source_label"]
    a = c.get("/api/medicine/1/alternatives").json()
    assert a["note"] == "Same ingredients and strength. Not necessarily interchangeable. Confirm with a pharmacist."
    assert [x["id"] for x in a["same"]] == ["2"]
    assert [x["id"] for x in c.get("/api/medicine/1/alternatives?include_discontinued=true").json()["same"]] == ["4", "2"]
    inc = c.get("/api/medicine/8/alternatives").json()
    assert any("may contain more" in x for x in inc["caveats"])
    assert c.get("/api/medicine/999").status_code == 404
    sm = c.get("/api/catalogue/summary").json()
    assert sm["brands"] == len(ROWS) and len(sm["synonyms"]) == 32


def _rules(s, text):
    folder = s.data_dir / "appms"
    folder.mkdir(parents=True)
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
        + text, encoding="utf-8")


def test_checker_across_ingredient_sets(client, monkeypatch):
    c, s = client
    write_artifacts(s.artifacts_dir)
    _rules(s, "Warfarin,Acetaminophen,High,Bleeding,Raised INR,Monitor INR,Src\n")
    monkeypatch.setattr(medicines, "load_label", lambda settings, idx, sid: PARSED[sid])
    assert c.post("/api/checker", json={"catalogue_ids": ["1"]}).status_code == 422
    assert c.post("/api/checker", json={"catalogue_ids": ["1", "1"]}).status_code == 422
    assert c.post("/api/checker", json={"names": ["Salbutamol", "salbutamol"]}).status_code == 422
    body = c.post("/api/checker", json={"catalogue_ids": ["1", "14", "6"], "names": ["Paracetamol"]}).json()
    assert body["status"] == "ready" and len(body["pairs"]) == 6
    first = body["pairs"][0]                                        # the flagged pair sorts first
    assert {first["a"]["name"], first["b"]["name"]} == {"Dolotest 650 Tablet", "Warfa 5 Tablet"}
    assert first["appms"]["severity"] == "high"
    hit = first["appms"]["hits"][0]
    assert {hit["a_ingredient"], hit["b_ingredient"]} == {"Paracetamol", "Warfarin"}   # rule says Acetaminophen
    tm = first["text_match"]
    assert tm["matches_total"] == 1 and tm["matches"][0]["sentence"] == "Acetaminophen may raise the INR."
    assert tm["matches"][0]["source_ingredient"] == "Warfarin" and tm["matches"][0]["named_ingredient"] == "Paracetamol"
    sec = first["secondary"]["hits"]
    assert [(h["in_product"], h["drug"], h["matches_ingredient"]) for h in sec] == [("Warfa 5 Tablet", "Paracetamol", "Paracetamol")]
    same = [p for p in body["pairs"] if {p["a"]["name"], p["b"]["name"]} == {"Dolotest 650 Tablet", "Paracetamol"}][0]
    assert same["shared_ingredients"] == ["Paracetamol"] and same["b"]["kind"] == "generic"
    metf = [p for p in body["pairs"] if "Metfocomb Tablet" in (p["a"]["name"], p["b"]["name"])]
    assert all(any("may be incomplete" in n for n in p["notes"]) for p in metf)
    assert any("Glimepiride (Metfocomb Tablet) has no linked US label" in n for n in metf[0]["text_match"]["notes"])


def test_checker_rules_not_loaded_is_reported(client, monkeypatch):
    c, s = client
    write_artifacts(s.artifacts_dir)
    monkeypatch.setattr(medicines, "load_label", lambda settings, idx, sid: PARSED[sid])
    body = c.post("/api/checker", json={"catalogue_ids": ["1", "14"]}).json()
    assert body["appms"]["status"] == "not_ready" and body["appms"]["fix"] == appms_service.FIX
    assert body["pairs"][0]["appms"]["severity"] is None
    assert body["pairs"][0]["text_match"]["matches_total"] == 1      # label text still checked


def test_combination_label_moieties_are_not_search_terms(client, monkeypatch):
    # aspirin's only US label is an aspirin + caffeine combination: a sentence naming caffeine must
    # not be reported as naming aspirin
    c, s = client
    labels = LABELS + [lab("L-asa-caf", "Aspirin and Caffeine", ["ASPIRIN", "CAFFEINE"], ["aspirin", "caffeine"])]
    write_artifacts(s.artifacts_dir, ROWS + [row("20", "Asprin 75 Tablet", "Aspirin (75mg)")], labels)
    parsed = {**PARSED, "L-warf": {"set_id": "L-warf", "sections": {"drug_interactions": [
        {"text": "Caffeine may lower levels. Aspirin raises bleeding risk."}]}},
        "L-asa-caf": {"set_id": "L-asa-caf", "sections": {}}}
    monkeypatch.setattr(medicines, "load_label", lambda settings, idx, sid: parsed[sid])
    body = c.post("/api/checker", json={"catalogue_ids": ["14", "20"]}).json()
    tm = body["pairs"][0]["text_match"]
    assert [m["sentence"] for m in tm["matches"]] == ["Aspirin raises bleeding risk."]
