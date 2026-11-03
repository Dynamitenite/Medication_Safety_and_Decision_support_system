# SOURCE: cosine-similarity retrieval over label chunks: P1, P2, P3 (cosine), P7 (FAISS; P7 uses
# IndexFlatL2 then cosine re-ranking, this uses IndexFlatIP on L2-normalised vectors, so the inner
# product IS the cosine: NOT IN PAPERS). No boosts and no re-ranking: the score is the cosine.
"""Runtime over artifacts/index/ written by scripts/build_index.py.

Layout:  index/manifest.json, chunks.jsonl, chunk_offsets.npy, chunk_label.npy, chunk_section.npy,
labels.json, <encoder>/manifest.json + vectors. Chunk i is line i of chunks.jsonl."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import numpy as np

from .encoder import make_encoder

STALE = "The index files do not match each other (chunks changed after this encoder was built)."


class IndexError_(Exception):
    """Raised when the files on disk are missing or inconsistent; callers turn it into not_ready."""


def split_sentences(text: str) -> list[str]:
    """Rough sentence split for showing one verbatim sentence; the text is not altered."""
    parts = re.split(r"(?<=[.;:!?])\s+(?=[A-Z0-9(\[•\-])|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


class Index:
    def __init__(self, folder: Path, encoder: str):
        self.folder, self.enc_name = folder, encoder
        top = folder / "manifest.json"
        enc_dir = folder / encoder
        if not top.is_file():
            raise IndexError_(f"{top.name} is missing")
        if not (enc_dir / "manifest.json").is_file():
            raise IndexError_(f"the {encoder} index is not built")
        self.manifest = json.loads(top.read_text(encoding="utf-8"))
        self.enc_manifest = json.loads((enc_dir / "manifest.json").read_text(encoding="utf-8"))
        if self.enc_manifest.get("chunks_sha256") != self.manifest.get("chunks_sha256"):
            raise IndexError_(STALE)
        self.n = int(self.manifest["chunks"])
        self.offsets = np.load(folder / "chunk_offsets.npy")
        self.chunk_label = np.load(folder / "chunk_label.npy")
        self.chunk_section = np.load(folder / "chunk_section.npy")
        self.sections: list[str] = self.manifest["sections"]
        self.labels: list[dict] = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
        self.label_by_id = {l["set_id"]: i for i, l in enumerate(self.labels)}
        self.encoder = make_encoder(encoder, enc_dir)
        self._enc_dir = enc_dir
        self._lock = threading.Lock()
        self._faiss = None
        if self.encoder.dense:
            self.V = np.load(enc_dir / "vectors.npy", mmap_mode="r")
            self.win_chunk = np.load(enc_dir / "window_chunk.npy")
            self.win_start = np.searchsorted(self.win_chunk, np.arange(self.n + 1))
            if len(self.win_chunk) != len(self.V):
                raise IndexError_(STALE)
        else:
            import scipy.sparse as sp
            self.X = sp.load_npz(enc_dir / "vectors.npz").tocsr()
            if self.X.shape[0] != self.n:
                raise IndexError_(STALE)
        self._by_section: dict[str, np.ndarray] = {}
        self._by_label: dict[int, np.ndarray] | None = None

    # ---- chunk access ---------------------------------------------------------------------
    def record(self, i: int) -> dict:
        with open(self.folder / "chunks.jsonl", "rb") as fh:
            fh.seek(int(self.offsets[i]))
            return json.loads(fh.readline().decode("utf-8"))

    def text(self, i: int) -> str:
        return self.record(i)["text"]

    def section(self, i: int) -> str:
        return self.sections[int(self.chunk_section[i])]

    def label(self, i: int) -> dict:
        return self.labels[int(self.chunk_label[i])]

    def chunks_of_section(self, section: str) -> np.ndarray:
        if section not in self._by_section:
            if section not in self.sections:
                self._by_section[section] = np.zeros(0, dtype=np.int64)
            else:
                self._by_section[section] = np.flatnonzero(self.chunk_section == self.sections.index(section))
        return self._by_section[section]

    def chunks_of_labels(self, set_ids: list[str]) -> np.ndarray:
        if self._by_label is None:
            order = np.argsort(self.chunk_label, kind="stable")
            bounds = np.searchsorted(self.chunk_label[order], np.arange(len(self.labels) + 1))
            self._by_label = {k: order[bounds[k]:bounds[k + 1]] for k in range(len(self.labels))}
        parts = [self._by_label[self.label_by_id[s]] for s in set_ids if s in self.label_by_id]
        return np.sort(np.concatenate(parts)) if parts else np.zeros(0, dtype=np.int64)

    # ---- search ---------------------------------------------------------------------------
    def _faiss_index(self):
        with self._lock:
            if self._faiss is None:
                import faiss
                ix = faiss.IndexFlatIP(self.V.shape[1])
                ix.add(np.ascontiguousarray(self.V, dtype=np.float32))
                self._faiss = ix
            return self._faiss

    def search(self, query: str, k: int, allowed: np.ndarray | None = None) -> list[tuple[int, float]]:
        """Top-k chunks by cosine similarity: [(chunk index, score)], best first. `allowed` limits
        the search to those chunk indices (still an exact inner product)."""
        if allowed is not None and len(allowed) == 0:
            return []
        q = self.encoder.encode([query], is_query=True)
        if not self.encoder.dense:
            if allowed is None:
                s = (self.X @ q.T).toarray().ravel()
                cand = np.arange(self.n)
            else:
                s = (self.X[allowed] @ q.T).toarray().ravel()
                cand = allowed
            top = np.argsort(-s, kind="stable")[:k]
            return [(int(cand[j]), float(s[j])) for j in top if s[j] > 0]
        import faiss
        ix = self._faiss_index()
        params = None
        if allowed is not None:
            wids = np.concatenate([np.arange(self.win_start[c], self.win_start[c + 1]) for c in allowed]).astype(np.int64)
            params = faiss.SearchParameters(sel=faiss.IDSelectorBatch(wids))
            total = len(wids)
        else:
            total = len(self.V)
        fetch = min(total, max(k * 8, 32))
        while True:
            D, I = ix.search(q.astype(np.float32), fetch, params=params)
            best: dict[int, float] = {}
            for d, w in zip(D[0], I[0]):
                if w < 0:
                    continue
                c = int(self.win_chunk[w])
                if c not in best:
                    best[c] = float(d)  # results come best first, so the first window seen is the best
            if len(best) >= k or fetch >= total:
                break
            fetch = min(total, fetch * 4)
        return sorted(best.items(), key=lambda t: -t[1])[:k]

    # ---- chunk to chunk -------------------------------------------------------------------
    def _gather(self, idx: np.ndarray):
        """Dense windows of the chunks in `idx` and where each chunk's windows start."""
        wins = [np.arange(self.win_start[c], self.win_start[c + 1]) for c in idx]
        starts = np.cumsum([0] + [len(w) for w in wins[:-1]]) if wins else np.zeros(0, dtype=np.int64)
        flat = np.concatenate(wins) if wins else np.zeros(0, dtype=np.int64)
        return np.asarray(self.V[flat], dtype=np.float32), starts.astype(np.int64)

    def pair_similarity(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Cosine similarity matrix (len(a) x len(b)) between chunks. For sbert it is the best
        window pair of each two chunks."""
        if not self.encoder.dense:
            return (self.X[a] @ self.X[b].T).toarray()
        Va, sa = self._gather(a)
        Vb, sb = self._gather(b)
        S = Va @ Vb.T
        return np.maximum.reduceat(np.maximum.reduceat(S, sa, axis=0), sb, axis=1)

    def text_cosines(self, reference: str, sentences: list[str]) -> np.ndarray:
        """Cosine of each sentence with a reference text, under this encoder (no query prefix)."""
        if not sentences:
            return np.zeros(0)
        r = self.encoder.encode([reference])
        s = self.encoder.encode(sentences)
        if self.encoder.dense:
            return (s @ r.T).ravel()
        return (s @ r.T).toarray().ravel()


_cache: dict[tuple, Index] = {}
_cache_lock = threading.Lock()


def load_index(folder: Path, encoder: str) -> Index:
    """Cached per (folder, encoder, manifest mtime)."""
    m = folder / encoder / "manifest.json"
    key = (str(folder), encoder, m.stat().st_mtime_ns if m.is_file() else 0,
           (folder / "manifest.json").stat().st_mtime_ns if (folder / "manifest.json").is_file() else 0)
    with _cache_lock:
        if key not in _cache:
            _cache.clear()
            _cache[key] = Index(folder, encoder)
        return _cache[key]


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
