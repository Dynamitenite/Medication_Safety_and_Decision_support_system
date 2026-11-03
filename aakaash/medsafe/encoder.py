# SOURCE: cosine similarity over text embeddings: P1 (ember-v1, cosine thresholds), P2 (cosine top-5),
# P3 (cosine retriever, chunk size 512). The encoder interface, the TF-IDF settings, the sbert
# sub-window scheme and the bge query prefix are NOT IN PAPERS (own design; prefix is from the bge model card).
"""Encoders for label search. ENCODER=tfidf (default, baseline, NOT deep learning) or sbert.

Every encoder returns L2-normalised vectors, so a dot product is the cosine similarity.
torch, transformers, sentence-transformers and faiss are imported lazily, inside the sbert code only."""
from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Iterable

import numpy as np

SBERT_MODEL = "BAAI/bge-small-en-v1.5"
SBERT_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge model card
WINDOW_TOKEN_BUDGET = 500   # leaves room for [CLS]/[SEP] under the model's 512-token limit
WINDOW_OVERLAP_WORDS = 32


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


class SbertEncoder:
    """sentence-transformers model (default BAAI/bge-small-en-v1.5). A chunk longer than the model's
    token limit is cut into word windows that fit; the chunk's score is its best window."""
    name = "sbert"
    is_deep_learning = True
    dense = True

    def __init__(self, model_name: str = SBERT_MODEL, revision: str | None = None):
        self.model_name, self.revision = model_name, revision
        self._model = None

    @property
    def label(self) -> str:
        return f"{self.model_name} (sentence-transformers, deep learning)"

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, revision=self.revision, device="cpu")
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

    def encode(self, texts: list[str], is_query: bool = False, batch_size: int = 16) -> np.ndarray:
        if is_query:
            texts = [SBERT_QUERY_PREFIX + t for t in texts]
        return self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False).astype(np.float32)


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
