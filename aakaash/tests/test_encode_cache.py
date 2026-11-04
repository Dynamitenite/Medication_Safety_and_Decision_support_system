# SOURCE: NOT IN PAPERS. Offline tests for the query-vector cache, the batched encode and the start-up load.
# The sbert model is never loaded: SbertEncoder.encode is replaced by a deterministic fake.
import hashlib
import json

import numpy as np
import pytest

import test_retrieval as tr
import test_sbert_wiring as tw
from api.services import retrieval
from medsafe import index as index_mod
from medsafe.encoder import SBERT_MODEL, VectorCache, SbertEncoder

env = tr.env
DIM = 16


def _vec(text: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "little")
    v = np.random.default_rng(seed).normal(size=DIM).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def fake_encode(monkeypatch):
    calls = []

    def encode(self, texts, is_query=False, batch_size=None):
        calls.append((list(texts), is_query))
        return np.stack([_vec(("Q:" if is_query else "") + t) for t in texts]) if texts else np.zeros((0, DIM), np.float32)

    monkeypatch.setattr(SbertEncoder, "encode", encode)
    return calls


@pytest.fixture
def sbert_env(env, fake_encode):
    top = json.loads((env.artifacts_dir / "index" / "manifest.json").read_text())
    n = top["chunks"]
    folder = env.artifacts_dir / "index" / "sbert"
    folder.mkdir()
    V = np.stack([_vec(f"chunk {i}") for i in range(n)])
    np.save(folder / "vectors.npy", V)
    np.save(folder / "window_chunk.npy", np.arange(n, dtype=np.int64))
    (folder / "manifest.json").write_text(json.dumps(
        {"encoder": "sbert", "chunks_sha256": top["chunks_sha256"], "chunks": n, "windows": n, "dimension": DIM,
         "vector_bytes": int(V.nbytes), "model": SBERT_MODEL, "model_revision": "r1", "device": "cpu",
         "window_token_budget": 500, "window_overlap_words": 32}), encoding="utf-8")
    retrieval._model_error = None
    s = tw._sbert_settings(env)
    yield s
    retrieval._model_error = None


# ---- the cache --------------------------------------------------------------------------------------
def test_repeated_text_is_encoded_once(fake_encode):
    e = SbertEncoder()
    a = e.encode_cached(["warfarin", "aspirin"], is_query=True)
    b = e.encode_cached(["aspirin", "warfarin"], is_query=True)
    assert len(fake_encode) == 1 and fake_encode[0][0] == ["warfarin", "aspirin"]
    assert np.array_equal(a, b[::-1])


def test_new_texts_go_through_the_model_in_one_batch(fake_encode):
    e = SbertEncoder()
    e.encode_cached(["a", "b"])
    e.encode_cached(["b", "c", "d", "c"])
    assert [c[0] for c in fake_encode] == [["a", "b"], ["c", "d"]]


def test_key_is_text_and_query_flag(fake_encode):
    e = SbertEncoder()
    q, p = e.encode_cached(["same"], is_query=True), e.encode_cached(["same"], is_query=False)
    assert len(fake_encode) == 2 and not np.array_equal(q, p)


def test_cache_is_size_limited_and_drops_the_oldest(fake_encode):
    c = VectorCache(2)
    for k in "abc":
        c.put(k, k)
    assert len(c) == 2 and c.get("a") is None and c.get("c") == "c"
    e = SbertEncoder()
    e.cache = VectorCache(2)
    e.encode_cached(["x", "y", "z"])
    fake_encode.clear()
    e.encode_cached(["z"])
    assert fake_encode == []
    e.encode_cached(["x"])
    assert len(fake_encode) == 1


def test_default_size_is_2000():
    assert SbertEncoder().cache.size == 2000


def test_empty_input(fake_encode):
    assert len(SbertEncoder().encode_cached([])) == 0 and fake_encode == []


# ---- results do not change ----------------------------------------------------------------------------
def test_top5_same_with_and_without_the_cache(sbert_env, fake_encode):
    queries = ["bleeding", "pain and fever", "pregnancy", "kidney", "take with food"]
    idx = index_mod.load_index(sbert_env.index_dir, "sbert")
    idx.encoder.cache = VectorCache(0)  # nothing is ever kept: every call encodes
    without = [idx.search(q, 5) for q in queries]
    n_without = len(fake_encode)
    idx.encoder.cache = VectorCache()
    cold = [idx.search(q, 5) for q in queries]
    warm = [idx.search(q, 5) for q in queries]
    assert without == cold == warm
    assert len(fake_encode) == n_without + len(queries)  # the second pass read the cache only


def test_search_response_same_with_and_without_the_cache(sbert_env):
    idx = index_mod.load_index(sbert_env.index_dir, "sbert")
    first = tr.post({"query": "bleeding", "k": 5})
    again = tr.post({"query": "bleeding", "k": 5})
    idx.encoder.cache = VectorCache(0)
    plain = tr.post({"query": "bleeding", "k": 5})
    strip = lambda b: [(r["chunk_id"], r["score"]) for r in b["results"]]
    assert first["encoder"] == "sbert" and strip(first) == strip(again) == strip(plain)


def test_best_sentence_batches_and_keeps_its_answer(sbert_env, fake_encode):
    from api.services import similar_use
    idx = index_mod.load_index(sbert_env.index_dir, "sbert")
    cand = "Used to treat pain. Also reduces fever in adults. Not for children under twelve years."
    ref = "Management of mild to moderate pain and fever"
    idx.encoder.cache = VectorCache(0)
    plain = similar_use._best_sentence(idx, cand, ref)
    idx.encoder.cache = VectorCache()
    fake_encode.clear()
    similar_use._prefetch(idx, [(cand, ref)])
    assert len(fake_encode) == 1  # one model call for everything the suggestion needs
    fake_encode.clear()
    assert similar_use._best_sentence(idx, cand, ref) == plain and fake_encode == []


# ---- load at start ------------------------------------------------------------------------------------
def test_warm_up_loads_the_model_and_reports_sbert(sbert_env, fake_encode):
    assert retrieval.warm_up(sbert_env) == "sbert" and fake_encode  # the model was used before any request
    assert retrieval._model_error is None


def test_failed_model_load_falls_back_to_tfidf_and_says_so(sbert_env, monkeypatch):
    def boom(self, *a, **k):
        raise OSError("no network for the model")

    monkeypatch.setattr(SbertEncoder, "encode", boom)
    assert retrieval.warm_up(sbert_env) == "tfidf"
    body = tr.post({"query": "bleeding", "k": 3})
    assert body["status"] == "ready" and body["encoder"] == "tfidf"
    assert "could not be loaded" in body["fallback_note"] and "TF-IDF answered instead" in body["fallback_note"]


def test_warm_up_is_a_no_op_for_tfidf_and_a_missing_index(env, tmp_path):
    assert retrieval.warm_up(env) == "tfidf"
    (env.artifacts_dir / "index" / "manifest.json").unlink()
    assert retrieval.warm_up(env) == "tfidf" and retrieval._model_error is None
