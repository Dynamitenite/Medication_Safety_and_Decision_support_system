# SOURCE: cosine similarity over text embeddings: P1 (ember-v1, cosine thresholds), P2 (cosine top-5),
# P3 (cosine retriever, chunk size 512). The encoder interface, the TF-IDF settings, the sbert
# sub-window scheme and the bge query prefix are NOT IN PAPERS (own design; prefix is from the bge model card).
"""Encoders for label search. ENCODER=tfidf (default, baseline, NOT deep learning) or sbert.

Every encoder returns L2-normalised vectors, so a dot product is the cosine similarity.
torch, transformers, sentence-transformers and faiss are imported lazily, inside the sbert code only."""
from __future__ import annotations

import os
import pickle
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Iterable

import numpy as np

SBERT_MODEL = "BAAI/bge-small-en-v1.5"
SBERT_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge model card
WINDOW_TOKEN_BUDGET = 500   # leaves room for [CLS]/[SEP] under the model's 512-token limit
WINDOW_OVERLAP_WORDS = 32


def resolve_device(requested: str | None = None, cuda_available=None) -> str:
    """"cpu" (default), "cuda", or "auto" (cuda when torch sees a GPU, else cpu). Read from MEDSAFE_DEVICE when
    not given. `cuda_available` is a callable for tests; by default torch is imported only for "auto"/"cuda"."""
    dev = (requested or os.environ.get("MEDSAFE_DEVICE") or "cpu").strip().lower()
    if dev == "cpu":
        return "cpu"
    if dev not in ("cuda", "auto"):
        raise ValueError(f"MEDSAFE_DEVICE must be 'cpu', 'cuda' or 'auto', not {dev!r}")
    if cuda_available is None:
        import torch
        cuda_available = torch.cuda.is_available
    have = bool(cuda_available())
    if dev == "cuda" and not have:
        raise RuntimeError("MEDSAFE_DEVICE=cuda but no CUDA GPU is available")
    return "cuda" if have else "cpu"


def default_batch_size(requested: str | None = None, cuda_available=None) -> int:
    """16 on CPU, 128 on GPU. Batch size changes speed only, never the windows or the text encoded."""
    return 16 if resolve_device(requested, cuda_available) == "cpu" else 128


def encoder_name(default: str = "tfidf") -> str:
    name = (os.environ.get("ENCODER") or os.environ.get("MEDSAFE_ENCODER") or default).strip().lower()
    if name not in ("tfidf", "sbert"):
        raise ValueError(f"ENCODER must be 'tfidf' or 'sbert', not {name!r}")
    return name


class TfidfEncoder:
    """sklearn TfidfVectorizer with L2 normalisation. A word-overlap baseline, not deep learning."""
    name = "tfidf"
    is_deep_learning = False
    label = "TF-IDF (baseline, word overlap, not deep learning)"
    dense = False

    def __init__(self, vectorizer=None):
        self.vectorizer = vectorizer

    def fit_transform(self, texts: Iterable[str]):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(sublinear_tf=True, stop_words="english", min_df=2,
                                          norm="l2", dtype=np.float32)
        return self.vectorizer.fit_transform(texts)

    def encode(self, texts: list[str], is_query: bool = False):
        return self.vectorizer.transform(texts)

    def save(self, folder: Path) -> None:
        with open(folder / "vectorizer.pkl", "wb") as fh:
            pickle.dump(self.vectorizer, fh)

    @classmethod
    def load(cls, folder: Path) -> "TfidfEncoder":
        with open(folder / "vectorizer.pkl", "rb") as fh:
            return cls(pickle.load(fh))

    def vocabulary_size(self) -> int:
        return len(self.vectorizer.vocabulary_)

    def analyzer(self):
        return self.vectorizer.build_analyzer()


VECTOR_CACHE_SIZE = 2000


class VectorCache:
    """Size-limited LRU of encoded texts, keyed by (encoder name, is_query, exact text). Vectors are
    stored as encoded, so a hit returns exactly what encoding again would."""

    def __init__(self, size: int = VECTOR_CACHE_SIZE):
        self.size = size
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._d)

    def get(self, key):
        with self._lock:
            v = self._d.get(key)
            if v is not None:
                self._d.move_to_end(key)
            return v

    def put(self, key, vec) -> None:
        with self._lock:
            self._d[key] = vec
            self._d.move_to_end(key)
            while len(self._d) > self.size:
                self._d.popitem(last=False)


class SbertEncoder:
    """sentence-transformers model (default BAAI/bge-small-en-v1.5). A chunk longer than the model's
    token limit is cut into word windows that fit; the chunk's score is its best window."""
    name = "sbert"
    is_deep_learning = True
    dense = True

    def __init__(self, model_name: str = SBERT_MODEL, revision: str | None = None, device: str | None = None):
        self.model_name, self.revision = model_name, revision
        self.requested_device = device
        self._model = None
        self.cache = VectorCache()

    @property
    def label(self) -> str:
        return f"{self.model_name} (sentence-transformers, deep learning)"

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, revision=self.revision,
                                              device=resolve_device(self.requested_device))
        return self._model

    def windows(self, text: str) -> list[str]:
        """Word windows that each fit the token budget, overlapping by WINDOW_OVERLAP_WORDS words."""
        words = text.split()
        if not words:
            return []
        tok = self.model.tokenizer
        enc = tok(words, is_split_into_words=True, add_special_tokens=False)
        per_word = np.zeros(len(words), dtype=np.int32)
        for wid in enc.word_ids():
            if wid is not None:
                per_word[wid] += 1
        out, start = [], 0
        while start < len(words):
            total, end = 0, start
            while end < len(words) and (total + per_word[end] <= WINDOW_TOKEN_BUDGET or end == start):
                total += per_word[end]
                end += 1
            out.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            start = max(end - WINDOW_OVERLAP_WORDS, start + 1)
        return out

    def encode(self, texts: list[str], is_query: bool = False, batch_size: int | None = None) -> np.ndarray:
        batch_size = batch_size or default_batch_size(self.requested_device)
        if is_query:
            texts = [SBERT_QUERY_PREFIX + t for t in texts]
        return self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False).astype(np.float32)

    def encode_cached(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        """Same vectors as encode(); texts seen before are not encoded again, and all the new ones go
        through the model in one batch call."""
        keys = [(self.name, is_query, t) for t in texts]
        have = {k: self.cache.get(k) for k in dict.fromkeys(keys)}
        todo = [k for k, v in have.items() if v is None]
        if todo:
            for k, v in zip(todo, self.encode([k[2] for k in todo], is_query=is_query)):
                have[k] = v
                self.cache.put(k, v)
        if not keys:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack([have[k] for k in keys])


def make_encoder(name: str | None = None, folder: Path | None = None):
    """An encoder ready to encode queries. `folder` is the built index folder (holds the fitted
    TF-IDF vocabulary; for sbert it holds nothing but the manifest)."""
    name = name or encoder_name()
    if name == "tfidf":
        return TfidfEncoder.load(folder) if folder is not None else TfidfEncoder()
    revision = None
    if folder is not None and (folder / "manifest.json").is_file():
        import json
        m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        revision = m.get("model_revision")
        return SbertEncoder(m.get("model", SBERT_MODEL), revision)
    return SbertEncoder(SBERT_MODEL, revision)
