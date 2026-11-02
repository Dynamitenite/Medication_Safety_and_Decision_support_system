# SOURCE: NOT IN PAPERS. FIXTURES ONLY: hand-written offsets and a tiny random BERT (ddi_fixture.py).
import pytest

from medsafe import explain as ex

MARKED = "<e1>Warfarin</e1> may raise bleeding with <e2>aspirin</e2>."
PLAIN = "Warfarin may raise bleeding with aspirin."


def test_plain_map_and_entity_spans():
    pm = ex.plain_map(MARKED)
    assert pm[0:4] == [None] * 4 and pm[4] == 0                      # "<e1>" is dropped, "W" is plain index 0
    (a, b), (c, d) = ex.entity_spans(MARKED)
    assert PLAIN[a:b] == "Warfarin" and PLAIN[c:d] == "aspirin"


def test_merge_word_pieces_back_to_words():
    # "Warfarin" = two pieces (marked offsets 4-7 and 7-12); "bleeding" = one piece
    start = MARKED.index("bleeding")
    pieces = [{"start": 4, "end": 7, "word_id": 0, "score": 0.25},
              {"start": 7, "end": 12, "word_id": 0, "score": 0.5},
              {"start": start, "end": start + 8, "word_id": 3, "score": -0.125}]
    words = ex.merge_words(MARKED, pieces)
    assert [w["text"] for w in words] == ["Warfarin", "bleeding"]
    assert words[0]["attribution"] == pytest.approx(0.75) and words[0]["is_drug"] is True
    assert words[1]["attribution"] == pytest.approx(-0.125) and words[1]["is_drug"] is False
    assert PLAIN[words[1]["start"]:words[1]["end"]] == "bleeding"


def test_delete_words_keeps_markers_and_drops_spans():
    words = [{"text": "bleeding", "start": PLAIN.index("bleeding"), "end": PLAIN.index("bleeding") + 8}]
    assert ex.delete_words(MARKED, words) == "<e1>Warfarin</e1> may raise with <e2>aspirin</e2>."


def test_eligible_excludes_drugs_and_punctuation():
    ws = [{"text": "aspirin", "is_drug": True}, {"text": ".", "is_drug": False}, {"text": "may", "is_drug": False}]
    assert [w["text"] for w in ex.eligible(ws)] == ["may"]


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    pytest.importorskip("captum")
    from ddi_fixture import make_checkpoint
    from medsafe import ddi_model as dm

    return dm.load_checkpoint(make_checkpoint(tmp_path_factory.mktemp("ddi")))


def test_attribution_shape_matches_words(tiny):
    model, tok, _ = tiny
    marked = "<e1>warfarin</e1> may raise the level of <e2>aspirin</e2> ."
    out = ex.explain(model, tok, marked, max_len=64, n_steps=8)
    assert [w["text"] for w in out["words"]] == ["warfarin", "may", "raise", "the", "level", "of", "aspirin", "."]
    assert all(isinstance(w["attribution"], float) for w in out["words"])
    assert [w["is_drug"] for w in out["words"]] == [True] + [False] * 5 + [True, False]
    assert sum(out["probabilities"]) == pytest.approx(1.0)
    assert out["predicted"] in ("effect", "mechanism", "advise", "int", "false")
    assert out["n_steps"] == 8


def test_faithfulness_proxy_reports_counts_and_skips(tiny):
    model, tok, _ = tiny
    texts = ["<e1>warfarin</e1> may raise the level of <e2>aspirin</e2> .", "<e1>a</e1> with <e2>b</e2> ."]
    r = ex.faithfulness(model, tok, texts, ks=(1, 3), draws=2, max_len=64, n_steps=6)
    assert r["label"] == "a faithfulness proxy" and r["n_sentences"] == 2
    assert r["by_k"]["1"]["n"] + r["by_k"]["1"]["skipped"] == 2
    assert r["by_k"]["3"]["skipped"] >= 1                             # the second sentence has no 3 eligible words
