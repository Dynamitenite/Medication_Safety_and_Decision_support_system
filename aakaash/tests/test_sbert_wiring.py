# SOURCE: NOT IN PAPERS. Offline tests for the sbert wiring: device choice, unchanged windowing, the installer,
# and the fall back to TF-IDF. No network, no GPU, no model download (the model and torch are never loaded).
import dataclasses
import hashlib
import json
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

import test_retrieval as tr
from api.app import app
from api.config import get_settings
from api.services import retrieval
from medsafe import index as index_mod
from medsafe.encoder import (SBERT_MODEL, WINDOW_OVERLAP_WORDS, WINDOW_TOKEN_BUDGET, SbertEncoder,
                             default_batch_size, resolve_device)
from scripts import install_sbert  # noqa: E402

env = tr.env  # fixture: tiny hand-written TF-IDF index under tmp_path


# ---- device ---------------------------------------------------------------------------------------
def test_device_defaults_to_cpu(monkeypatch):
    monkeypatch.delenv("MEDSAFE_DEVICE", raising=False)
    assert resolve_device() == "cpu"
    assert default_batch_size() == 16
    assert SbertEncoder().requested_device is None


def test_device_from_env_and_argument(monkeypatch):
    monkeypatch.setenv("MEDSAFE_DEVICE", "cuda")
    assert resolve_device(cuda_available=lambda: True) == "cuda"
    assert default_batch_size(cuda_available=lambda: True) == 128
    assert resolve_device("cpu") == "cpu"  # an explicit argument beats the env var


def test_cuda_requested_without_gpu_fails_loudly(monkeypatch):
    monkeypatch.setenv("MEDSAFE_DEVICE", "cuda")
    with pytest.raises(RuntimeError, match="no CUDA GPU"):
        resolve_device(cuda_available=lambda: False)


def test_auto_picks_gpu_only_when_present():
    assert resolve_device("auto", cuda_available=lambda: True) == "cuda"
    assert resolve_device("auto", cuda_available=lambda: False) == "cpu"


def test_bad_device_value_rejected():
    with pytest.raises(ValueError, match="MEDSAFE_DEVICE"):
        resolve_device("tpu")


# ---- windowing is the CPU scheme, whatever the device ----------------------------------------------
class _Enc:
    def __init__(self, n_words, per_word):
        self._ids = [i for i in range(n_words) for _ in range(per_word(i))]

    def word_ids(self):
        return self._ids


class _FakeModel:
    def __init__(self, per_word):
        self.per_word = per_word

    def tokenizer(self, words, is_split_into_words=True, add_special_tokens=False):
        return _Enc(len(words), self.per_word)


def _windows(n_words, per_word=lambda i: 1):
    e = SbertEncoder(device="cuda")  # device must not matter for the windows
    e._model = _FakeModel(per_word)
    return e.windows(" ".join(f"w{i}" for i in range(n_words)))


def test_windowing_constants_unchanged():
    assert (WINDOW_TOKEN_BUDGET, WINDOW_OVERLAP_WORDS, SBERT_MODEL) == (500, 32, "BAAI/bge-small-en-v1.5")


def test_short_text_is_one_window_and_empty_is_none():
    assert len(_windows(10)) == 1
    assert _windows(0) == []


def test_long_text_windows_overlap_by_32_words():
    w = _windows(1200)  # 1 token per word: 500-word windows, step 468
    sizes = [len(x.split()) for x in w]
    assert sizes == [500, 500, 264] and w[0].split()[468] == w[1].split()[0]
    assert w[0].split()[-WINDOW_OVERLAP_WORDS:] == w[1].split()[:WINDOW_OVERLAP_WORDS]


def test_multi_token_words_respect_the_token_budget():
    w = _windows(300, per_word=lambda i: 2)  # 2 tokens per word -> 250 words per window
    assert [len(x.split()) for x in w][0] == 250


# ---- install_sbert ----------------------------------------------------------------------------------
def _top(folder, sha="a" * 64, chunks=3):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps({"chunks_sha256": sha, "chunks": chunks}), encoding="utf-8")


def _zip(path, sha="a" * 64, names=("vectors.npy", "window_chunk.npy", "manifest.json"), enc="sbert", chunks=3):
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            if n == "manifest.json":
                z.writestr(n, json.dumps({"encoder": enc, "chunks_sha256": sha, "chunks": chunks, "windows": 3,
                                          "dimension": 4, "model": SBERT_MODEL, "seconds": 1}))
            else:
                z.writestr(n, b"x")
    return path


def test_install_ok_extracts_three_files(tmp_path):
    _top(tmp_path / "index")
    m = install_sbert.install(_zip(tmp_path / "s.zip"), tmp_path / "index")
    assert m["chunks"] == 3
    assert sorted(p.name for p in (tmp_path / "index" / "sbert").iterdir()) == ["manifest.json", "vectors.npy", "window_chunk.npy"]
    assert not (tmp_path / "index" / "sbert.installing").exists()


def test_install_refuses_hash_mismatch_and_writes_nothing(tmp_path):
    _top(tmp_path / "index")
    with pytest.raises(install_sbert.InstallError, match="chunks_sha256 does not match"):
        install_sbert.install(_zip(tmp_path / "s.zip", sha="b" * 64), tmp_path / "index")
    assert not (tmp_path / "index" / "sbert").exists()


def test_install_refuses_to_overwrite_without_force(tmp_path):
    _top(tmp_path / "index")
    (tmp_path / "index" / "sbert" / "shards").mkdir(parents=True)
    z = _zip(tmp_path / "s.zip")
    with pytest.raises(install_sbert.InstallError, match="--force"):
        install_sbert.install(z, tmp_path / "index")
    assert (tmp_path / "index" / "sbert" / "shards").exists()
    install_sbert.install(z, tmp_path / "index", force=True)
    assert not (tmp_path / "index" / "sbert" / "shards").exists()
    assert (tmp_path / "index" / "sbert" / "vectors.npy").is_file()


def test_install_refuses_extra_files_and_wrong_encoder(tmp_path):
    _top(tmp_path / "index")
    with pytest.raises(install_sbert.InstallError, match="exactly"):
        install_sbert.install(_zip(tmp_path / "a.zip", names=("vectors.npy", "window_chunk.npy", "manifest.json", "../evil")),
                              tmp_path / "index")
    with pytest.raises(install_sbert.InstallError, match="not 'sbert'"):
        install_sbert.install(_zip(tmp_path / "b.zip", enc="tfidf"), tmp_path / "index")


# ---- fall back to TF-IDF with a visible reason --------------------------------------------------------
def _sbert_settings(s):
    s2 = dataclasses.replace(s, encoder_name="sbert")
    app.dependency_overrides[get_settings] = lambda: s2
    index_mod.clear_cache()
    return s2


def test_missing_sbert_folder_falls_back_and_says_so(env):
    _sbert_settings(env)
    body = tr.post({"query": "bleeding", "k": 3})
    assert body["status"] == "ready" and body["encoder"] == "tfidf" and "TF-IDF" in body["encoder_label"]
    assert "TF-IDF answered instead" in body["fallback_note"] and "install_sbert.py" in body["fallback_note"]
    st = TestClient(app).get("/api/status").json()
    enc = next(c for c in st["components"] if c["id"] == "encoder")
    assert enc["status"] == "not_ready" and "TF-IDF" in enc["reason"] and "install_sbert.py" in enc["fix"]
    summ = TestClient(app).get("/api/index/summary").json()
    assert summ["active_encoder"] == "tfidf" and summ["configured_encoder"] == "sbert" and summ["fallback_note"]


def test_stale_sbert_hash_falls_back(env):
    folder = env.artifacts_dir / "index" / "sbert"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps({"encoder": "sbert", "chunks_sha256": "0" * 64}), encoding="utf-8")
    _sbert_settings(env)
    body = tr.post({"query": "bleeding", "k": 3})
    assert body["encoder"] == "tfidf" and body["fallback_note"]
    enc = next(c for c in TestClient(app).get("/api/status").json()["components"] if c["id"] == "encoder")
    assert enc["status"] == "not_ready" and "different chunks" in enc["reason"]


def test_tfidf_default_has_no_fallback_note(env):
    body = tr.post({"query": "bleeding", "k": 3})
    assert body["encoder"] == "tfidf" and body["fallback_note"] is None


def test_valid_sbert_folder_is_used_and_labelled(env, monkeypatch):
    top = json.loads((env.artifacts_dir / "index" / "manifest.json").read_text())
    n = top["chunks"]
    folder = env.artifacts_dir / "index" / "sbert"
    folder.mkdir()
    V = np.eye(n, 8, dtype=np.float32)  # one window per chunk
    np.save(folder / "vectors.npy", V)
    np.save(folder / "window_chunk.npy", np.arange(n, dtype=np.int64))
    (folder / "manifest.json").write_text(json.dumps(
        {"encoder": "sbert", "chunks_sha256": top["chunks_sha256"], "chunks": n, "windows": n, "dimension": 8,
         "vector_bytes": int(V.nbytes), "model": SBERT_MODEL, "model_revision": "r1", "device": "cuda",
         "window_token_budget": 500, "window_overlap_words": 32}), encoding="utf-8")
    monkeypatch.setattr(SbertEncoder, "encode", lambda self, texts, is_query=False, batch_size=None: V[[2]].copy())
    _sbert_settings(env)
    body = tr.post({"query": "anything", "k": 3})
    assert body["status"] == "ready" and body["encoder"] == "sbert" and SBERT_MODEL in body["encoder_label"]
    assert body["fallback_note"] is None and body["is_deep_learning"] is True
    assert body["results"][0]["score"] == pytest.approx(1.0)
    summ = TestClient(app).get("/api/index/summary").json()
    assert summ["model"] == SBERT_MODEL and summ["model_revision"] == "r1" and summ["window_overlap_words"] == 32
    enc = next(c for c in TestClient(app).get("/api/status").json()["components"] if c["id"] == "encoder")
    assert enc["status"] == "ready"


def test_no_index_at_all_is_still_not_ready(env):
    (env.artifacts_dir / "index" / "manifest.json").unlink()
    _sbert_settings(env)
    assert tr.post({"query": "x", "k": 3})["status"] == "not_ready"
