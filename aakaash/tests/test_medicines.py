# SOURCE: NOT IN PAPERS. FIXTURES ONLY: every label below is hand-written to exercise code paths.
# None of it is real DailyMed data and none of it may appear in the UI.
import json

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.config import Settings, get_settings
from api.services import medicines
from medsafe.names import NameIndex, drug_terms, mentions, pairs, split_sentences


def lab(sid, products, generic=(), ings=(), moieties=(), maker="Maker A"):
    return {"set_id": sid, "products": list(products), "generic": list(generic),
            "ingredients": [i.lower() for i in ings], "moieties": list(moieties),
            "moieties_raw": [m.upper() for m in moieties], "manufacturer": maker,
            "source": "x.zip!in.zip", "member": "a.xml"}


LABELS = [
    lab("1", ["Zorvex"], ["foobarin hydrochloride"], ["FOOBARIN HYDROCHLORIDE"], ["foobarin"]),
    lab("2", ["Foobarin Hydrochloride"], ["foobarin hydrochloride"], ["FOOBARIN HYDROCHLORIDE"], ["foobarin"], "Maker B"),
    lab("3", ["Foobarin Hydrochloride"], ["foobarin hydrochloride"], ["FOOBARIN HYDROCHLORIDE"], ["foobarin"], "Maker B"),
    lab("4", ["Quuxapril"], ["quuxapril"], ["QUUXAPRIL"], ["quuxapril"]),
    lab("5", ["Combo One"], ["foobarin and quuxapril"], ["FOOBARIN", "QUUXAPRIL"], ["foobarin", "quuxapril"]),
    lab("6", ["Abc"], [], ["ABC"], ["abc"]),
    lab("7", ["Nomoiety"], [], [], []),
]


@pytest.fixture
def idx():
    return NameIndex(LABELS)


def names(rows):
    return [r["name"].lower() for r in rows]


def test_prefix_before_word_before_substring(idx):
    extra = NameIndex(LABELS + [lab("8", ["Alpha Foobar"], ["alpha foobar"], [], ["alphafoobar"]),
                                lab("9", ["Xfoobarx"], ["xfoobarx"], [], ["xfoobarx"])])
    rows = extra.suggest("foobar", 20)
    tiers = [r["match"] for r in rows]
    assert tiers.index("prefix") < tiers.index("word") < tiers.index("substring")
    assert "alpha foobar" in names(rows) and "xfoobarx" in names(rows)


def test_brand_generic_ingredient_tags(idx):
    by_name = {r["name"].lower(): r for r in idx.suggest("z", 10)}
    assert by_name["zorvex"]["type"] == "brand"
    gen = {r["name"].lower(): r["type"] for r in idx.suggest("foobarin", 10)}
    assert gen["foobarin hydrochloride"] == "generic"


def test_same_name_is_collapsed_with_label_count(idx):
    rows = [r for r in idx.suggest("foobarin hydrochloride", 10) if r["name"].lower() == "foobarin hydrochloride"]
    assert len(rows) == 1 and rows[0]["label_count"] == 3  # labels 1, 2, 3 all name it


def test_fuzzy_catches_typo_and_ignores_garbage(idx):
    assert "quuxapril" in names(idx.suggest("quxapril", 5))
    assert idx.suggest("zzzzzz", 5) == []
    assert idx.suggest("   ", 5) == []


def test_result_carries_manufacturer_and_set_id(idx):
    r = idx.suggest("zorvex", 1)[0]
    assert r["manufacturer"] == "Maker A" and r["set_id"] == "1"


def test_alternatives_group_by_product_and_manufacturer(idx):
    alts = idx.alternatives("2")
    assert [(a["product"], a["manufacturer"], a["label_count"]) for a in alts] == [
        ("Foobarin Hydrochloride", "Maker B", 1), ("Zorvex", "Maker A", 1)]
    assert all(a["set_id"] != "2" for a in alts)


def test_combination_matches_only_full_moiety_set(idx):
    assert idx.alternatives("5") == []                 # no other foobarin+quuxapril product
    assert all(a["set_id"] != "5" for a in idx.alternatives("1"))  # single-ingredient excludes combo
    assert all(a["set_id"] != "5" for a in idx.alternatives("4"))


def test_no_moiety_means_no_alternatives(idx):
    assert idx.alternatives("7") == []


def test_word_boundary_and_min_length():
    target = lab("t", ["Warfarin Sodium"], moieties=["warfarin"])
    assert mentions("Avoid with warfarin.", target)
    assert not mentions("Antiwarfarinic agents.", target)      # inside a word
    assert not mentions("The warfarins differ.", target)
    short = lab("s", ["Abc"], moieties=["abc"])
    assert drug_terms(short) == [] and mentions("abc interacts", short) == []   # < 4 characters


def test_multiword_term_and_case_insensitive():
    target = lab("t", ["Warfarin Sodium"], moieties=["warfarin"])
    hit = mentions("Monitor INR when WARFARIN   sodium is added.", target)
    assert len(hit) == 1 and hit[0]["matched_term"].lower().startswith("warfarin")


def test_long_line_is_excerpted_around_the_match():
    target = lab("t", ["Warfarin Sodium"], moieties=["warfarin"])
    text = " ".join(f"drug{i}," for i in range(300)) + " warfarin, " + " ".join(f"other{i}," for i in range(300))
    hit = mentions(text, target)[0]["sentence"]
    assert "warfarin" in hit and len(hit) < 600 and hit.startswith("…") and hit.endswith("…")
    assert mentions("Short warfarin line.", target)[0]["sentence"] == "Short warfarin line."


def test_sentence_split_keeps_abbreviations():
    s = split_sentences("Use e.g. a low dose. Monitor closely.\nSee Table 1.")
    assert s == ["Use e.g. a low dose.", "Monitor closely.", "See Table 1."]


def test_pair_generation():
    assert pairs(["a", "b", "c"]) == [("a", "b"), ("a", "c"), ("b", "c")]
    assert len(pairs([str(i) for i in range(10)])) == 45


# ---- API paths ----------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art",
                        trace_path=tmp_path / "t.md", encoder_name="tfidf", classifier_name="x")
    app.dependency_overrides[get_settings] = lambda: settings
    medicines.clear_cache()
    yield TestClient(app), settings
    app.dependency_overrides.clear()
    medicines.clear_cache()


def test_no_name_index_is_not_ready(client):
    c, _ = client
    for r in (c.get("/api/label/1"), c.get("/api/label/1/alternatives")):
        body = r.json()
        assert r.status_code == 200 and body["status"] == "not_ready"
        assert "build_names.py" in body["fix"]


def _with_index(settings):
    settings.artifacts_dir.mkdir(parents=True)
    (settings.artifacts_dir / "names.json").write_text(json.dumps({"labels": LABELS}), encoding="utf-8")


def test_label_alternatives_endpoint_and_unknown_id(client):
    c, s = client
    _with_index(s)
    body = c.get("/api/label/1/alternatives").json()
    assert body["status"] == "ready" and body["total_labels"] == 2
    assert "Not necessarily interchangeable" in body["note"]
    assert c.get("/api/label/nope/alternatives").status_code == 404


def test_label_zip_missing_is_reported(client):
    c, s = client
    _with_index(s)
    assert c.get("/api/label/1").status_code == 503


# ---- APPMS name to label matching (hand-written fixtures) -------------------------------
def test_ingredient_matcher_strips_form_words_only():
    from medsafe.appms_match import IngredientMatcher, ingredient_keys
    assert ingredient_keys("ENALAPRIL MALEATE") == {"enalapril maleate", "enalapril"}
    assert ingredient_keys("Isosorbide mononitrate") == {"isosorbide mononitrate"}
    labels = [
        {"set_id": "1", "products": ["Zed"], "ingredients": ["ENALAPRIL MALEATE"], "moieties": ["enalaprilat anhydrous"], "manufacturer": "B"},
        {"set_id": "2", "products": ["albuterol"], "ingredients": ["ALBUTEROL SULFATE"], "moieties": ["albuterol"], "manufacturer": "A"},
    ]
    m = IngredientMatcher(labels)
    assert [l["set_id"] for l in m.match("Enalapril")] == ["1"]
    assert [l["set_id"] for l in m.match("Salbutamol")] == ["2"]  # medsafe/synonyms.csv, exact
    assert m.match("Salbutamols") == []  # no fuzzy matching


def test_checker_needs_two_medicines():
    c = TestClient(app)
    assert c.post("/api/checker", json={"catalogue_ids": [], "names": ["Solo"]}).status_code == 422
