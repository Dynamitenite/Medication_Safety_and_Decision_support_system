# SOURCE: NOT IN PAPERS. FIXTURES ONLY (tests/fixtures_catalogue.py, tests/fixtures_index.py): hand-written
# rows, labels and passages to exercise the retrieval code. No real data, nothing downloaded.
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.config import Settings, get_settings
from api.services import catalogue as catalogue_service, retrieval, similar_use
from medsafe import index as index_mod
from medsafe.chunking import chunk_label
from medsafe.encoder import encoder_name

from fixtures_catalogue import LABELS, ROWS, lab, row, write_artifacts
from fixtures_index import write_index

EXTRA_ROWS = [row("40", "Nacltab Tablet", "Sodium Chloride (500mg)"),
              row("41", "Metfosyrup Syrup", "Metformin (500mg)", price="1", pack="bottle of 60 ml Syrup")]


@pytest.fixture
def env(tmp_path):
    s = Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art", trace_path=tmp_path / "t.md",
                 encoder_name="tfidf", classifier_name="x")
    write_artifacts(s.artifacts_dir, ROWS + EXTRA_ROWS, LABELS)
    write_index(s.artifacts_dir, LABELS)
    app.dependency_overrides[get_settings] = lambda: s
    catalogue_service.clear_cache()
    index_mod.clear_cache()
    yield s
    app.dependency_overrides.clear()
    catalogue_service.clear_cache()
    index_mod.clear_cache()


def post(body):
    return TestClient(app).post("/api/search/labels", json=body).json()


def brand_id(name):
    return {r["name"]: r["id"] for r in ROWS + EXTRA_ROWS}[name]


# ---- chunking ------------------------------------------------------------------------------------
def test_chunking_keeps_sections_and_never_crosses_them():
    rec = {"set_id": "S", "title": "T", "ingredients": ["x"], "active_moieties": ["x"], "manufacturer": "M",
           "sections": {"indications": [{"text": " ".join(f"a{i}" for i in range(10))}],
                        "dosage_administration": [{"text": " ".join(f"b{i}" for i in range(6))}]}}
    ch = list(chunk_label(rec, size=4, overlap=1))
    assert {c["section"] for c in ch} == {"indications", "dosage_administration"}
    assert all(c["text"].split()[0][0] == ("a" if c["section"] == "indications" else "b") for c in ch)
    assert all(len(c["text"].split()) <= 4 for c in ch)
    assert [c["chunk_id"] for c in ch][:2] == ["S:indications:0", "S:indications:1"]
    assert ch[0]["text"].split()[-1] == ch[1]["text"].split()[0]  # overlap of 1 word


# ---- cosine search -------------------------------------------------------------------------------
def test_cosine_search_order_and_equals_dot_product(env):
    idx = retrieval.get_index(env)[0]
    hits = idx.search("pain and fever", 5)
    scores = [s for _, s in hits]
    assert scores == sorted(scores, reverse=True) and 0 < scores[0] <= 1.0 + 1e-6
    assert idx.label(hits[0][0])["moieties"] == ["acetaminophen"]
    q = idx.encoder.encode(["pain and fever"])
    c = hits[0][0]
    assert scores[0] == pytest.approx(float((idx.X[c] @ q.T).toarray()[0, 0]), abs=1e-6)  # normalised: dot = cosine
    assert idx.label(idx.search("bleeding", 1)[0][0])["set_id"] == "L-warf"


def test_restricted_search_only_returns_allowed_chunks(env):
    idx = retrieval.get_index(env)[0]
    allowed = idx.chunks_of_labels(["L-metf"])
    hits = idx.search("pain and fever", 5, allowed)
    assert all(c in set(allowed.tolist()) for c, _ in hits)
    assert idx.search("pain", 5, np.zeros(0, dtype=np.int64)) == []


def test_search_endpoint_for_medicine_uses_default_label_and_shows_form(env):
    r = post({"query": "pain and fever", "medicine_id": brand_id("Dolotest 650 Tablet"), "k": 5})
    assert r["status"] == "ready" and r["encoder"] == "tfidf" and r["is_deep_learning"] is False
    assert {x["set_id"] for x in r["results"]} == {"L-apap-2"}  # the default tablet label, not the injection
    assert all(x["form"] and x["route"] for x in r["results"])
    dose = next(x for x in r["results"] if x["section"] == "dosage_administration")
    assert dose["text"] and not dose["withheld"] and "pain" in dose["match_terms"]
    assert r["results"][0]["score"] >= r["results"][-1]["score"]


def test_scope_all_adds_other_linked_labels(env):
    r = post({"query": "pain and fever", "medicine_id": brand_id("Dolotest 650 Tablet"), "k": 10, "scope": "all"})
    assert {"L-apap-2", "L-apap-inj"} <= {x["set_id"] for x in r["results"]}


# ---- wrong-form guard ------------------------------------------------------------------------------
def test_wrong_form_label_never_shows_dosage_text(env):
    r = post({"query": "dosage fluid deficit", "medicine_id": brand_id("Nacltab Tablet"), "k": 5})
    assert r["status"] == "ready"
    dose = next(x for x in r["results"] if x["section"] == "dosage_administration")
    assert dose["withheld"] and dose["text"] == "" and dose["withheld_note"]
    assert dose["form"] == "INJECTION, SOLUTION" and dose["route"] == "INTRAVENOUS" and dose["score"] > 0
    assert "different dosage form" in dose["mismatch_note"]
    ind = [x for x in r["results"] if x["section"] == "indications"]
    assert all(x["text"] for x in ind)  # indications are shown (as on the details card), with the form beside them


def test_matching_form_is_not_withheld(env):
    r = post({"query": "dose every six hours", "medicine_id": brand_id("Dolotest 650 Tablet")})
    assert not any(x["withheld"] for x in r["results"])


# ---- not_ready -----------------------------------------------------------------------------------
def test_not_ready_when_no_index(env):
    import shutil
    shutil.rmtree(env.index_dir)
    index_mod.clear_cache()
    c = TestClient(app)
    for r in (c.post("/api/search/labels", json={"query": "pain"}).json(),
              c.get(f"/api/medicine/{brand_id('Dolotest 650 Tablet')}/similar-use").json(),
              c.get("/api/index/summary").json()):
        assert r["status"] == "not_ready" and "scripts/build_index.py" in r["fix"] and r["reason"]


def test_not_ready_when_index_is_stale(env):
    p = env.index_dir / "tfidf" / "manifest.json"
    m = json.loads(p.read_text())
    m["chunks_sha256"] = "0" * 64
    p.write_text(json.dumps(m))
    index_mod.clear_cache()
    r = post({"query": "pain"})
    assert r["status"] == "not_ready" and "do not match" in r["reason"]


def test_not_ready_when_the_chosen_encoder_is_not_built(env):
    s2 = Settings(**{**env.__dict__, "encoder_name": "sbert"})
    app.dependency_overrides[get_settings] = lambda: s2
    assert post({"query": "pain"})["status"] == "not_ready"


def test_encoder_name_rejects_unknown(monkeypatch):
    monkeypatch.setenv("ENCODER", "nope")
    with pytest.raises(ValueError):
        encoder_name()
    monkeypatch.setenv("ENCODER", "SBERT")
    assert encoder_name() == "sbert"


def test_search_validation(env):
    c = TestClient(app)
    assert c.post("/api/search/labels", json={"query": "   "}).status_code == 422
    assert c.post("/api/search/labels", json={"query": "x", "k": 99}).status_code == 422
    assert c.post("/api/search/labels", json={"query": "x", "medicine_id": "nope"}).status_code == 404


# ---- similar uses: aggregation -------------------------------------------------------------------
def test_rank_takes_max_per_ingredient_and_excludes():
    # 2 query chunks x 5 candidate chunks; ingredients 10 (cols 0-1), 11 (col 2), 12 (cols 3-4)
    S = np.array([[0.1, 0.8, 0.9, 0.2, 0.3],
                  [0.7, 0.2, 0.4, 0.6, 0.1]])
    ings, bounds = [10, 11, 12], np.array([0, 2, 3, 5])
    r = similar_use.rank(S, bounds, excluded=set(), ings=ings, moieties={}, min_sim=0.5, limit=10)
    assert [(x["ing"], x["score"], x["support"]) for x in r] == [(11, 0.9, 1), (10, 0.8, 2), (12, 0.6, 1)]
    assert r[1]["col"] == 1 and r[1]["row"] == 0
    r = similar_use.rank(S, bounds, excluded={11}, ings=ings, moieties={}, min_sim=None, limit=1)
    assert [x["ing"] for x in r] == [10] and r[0]["support"] is None  # no minimum set: no count invented


def test_rank_keeps_one_ingredient_per_moiety_set():
    S = np.array([[0.9, 0.5]])
    r = similar_use.rank(S, np.array([0, 1, 2]), set(), [1, 2], {1: frozenset({"m"}), 2: frozenset({"m"})}, None, 10)
    assert [x["ing"] for x in r] == [1]


# ---- similar uses: endpoint and brand mapping ------------------------------------------------------
def similar(name, limit=10):
    return TestClient(app).get(f"/api/medicine/{brand_id(name)}/similar-use", params={"limit": limit}).json()


def test_similar_use_excludes_same_ingredient_and_words_are_safe(env):
    r = similar("Dolotest 650 Tablet")
    assert r["status"] == "ready" and r["heading"] == "Medicines with similar uses"
    assert "not advice to switch" in r["note"] and "interchangeable" in r["note"]
    names = [s["ingredient"].lower() for g in r["groups"] for s in g["suggestions"]]
    assert "paracetamol" not in names and "acetaminophen" not in names
    assert "metformin" in names and r["min_similarity"] is None
    assert not any("equivalent" in json.dumps(r).lower() or "substitute" in json.dumps(r).lower() for _ in [0])
    g = r["groups"][0]
    assert g["query_labels"] == 3 and g["query_passages"] == 3
    sims = [s["similarity"] for s in g["suggestions"]]
    assert sims == sorted(sims, reverse=True)
    top = g["suggestions"][0]
    assert top["supporting_sentence"] and top["supporting_label"]["set_id"].startswith("L-")


def test_similar_use_combination_handles_each_ingredient_and_says_so(env):
    r = similar("Metfocomb Tablet")
    assert r["combination_note"] == "This medicine has 2 ingredients. Each one is compared on its own."
    by = {g["ingredient"].lower(): g for g in r["groups"]}
    assert set(by) == {"metformin", "glimepiride"}
    assert "No Indications text" in by["glimepiride"]["note"] and by["glimepiride"]["suggestions"] == []
    names = [s["ingredient"].lower() for s in by["metformin"]["suggestions"]]
    assert "metformin" not in names and "glimepiride" not in names


def test_brands_for_ingredient_filters_and_order(env):
    cat = catalogue_service.get_catalogue(env)
    para = cat.ing_by_key["paracetamol"] if "paracetamol" in cat.ing_by_key else cat.ing_by_key["acetaminophen"]
    total, brands = cat.brands_for_ingredient(para, "oral solid", 10)
    names = [b["name"] for b in brands]
    assert "Oldpara 650 Tablet" not in names          # discontinued
    assert "Paraunclear Tablet" not in names          # composition unclear
    assert not {"Parasyp 650 Syrup", "Paradrops 650", "Calpara 650 Dry Syrup"} & set(names)  # other form family
    assert names == ["Parafen 500 Tablet", "Calpara 650 Tablet", "Dolotest 650 Tablet"] and total == 3  # cheapest first
    assert cat.brands_for_ingredient(para, "unknown", 10) == (0, [])
    assert len(cat.brands_for_ingredient(para, "oral solid", 2)[1]) == 2          # limit
    metf = cat.ing_by_key["metformin"]
    _, mb = cat.brands_for_ingredient(metf, "oral solid", 10)
    assert mb[0]["name"] == "Metfo 500 Tablet" and mb[0]["ingredient_count"] == 1   # single-ingredient first
    assert all(b["ingredient_count"] >= 2 for b in mb[1:]) and "Metfosyrup Syrup" not in [b["name"] for b in mb]


def test_similar_use_suggestion_carries_brands_of_same_form(env):
    r = similar("Dolotest 650 Tablet")
    metf = next(s for s in r["groups"][0]["suggestions"] if s["ingredient"].lower() == "metformin")
    assert metf["brands"][0]["name"] == "Metfo 500 Tablet" and metf["brands"][0]["price"] == 15.0
    assert all(b["form_family"] == "oral solid" and not b["discontinued"] for b in metf["brands"])
    assert metf["brands_total"] >= len(metf["brands"]) and len(metf["brands"]) <= 5


def test_generic_wording_flag_marks_but_never_hides(env, monkeypatch):
    base = similar("Dolotest 650 Tablet")
    n_default = len(base["groups"][0]["suggestions"])
    assert all(s["flags"] == [] for s in base["groups"][0]["suggestions"])  # nothing here is carried by 5 ingredients
    monkeypatch.setattr(similar_use, "GENERIC_MIN_INGREDIENTS", 1)
    r = similar("Dolotest 650 Tablet")
    sug = r["groups"][0]["suggestions"]
    assert len(sug) == n_default and all(s["flags"] and "Generic wording" in s["flags"][0] for s in sug)
    assert [s["ingredient"] for s in sug] == [s["ingredient"] for s in base["groups"][0]["suggestions"]]  # same results, same order


def test_carrier_count_normalises_the_sentence(env):
    cat = catalogue_service.get_catalogue(env)
    similar_use._candidates(cat, retrieval.get_index(env)[0])
    assert similar_use.carrier_count("Management of MILD to moderate pain, and reduction of fever") >= 0
    assert similar_use.carrier_count("a sentence that no label contains at all here") == 0
