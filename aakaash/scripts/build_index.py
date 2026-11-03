# SOURCE: NOT IN PAPERS (own tooling). Chunks every DailyMed label (medsafe/spl.py + medsafe/chunking.py,
# size 512, overlap 64, whitespace words) and encodes the chunks. Output is generated data and is
# gitignored (aakaash/artifacts/index/). Never commit it.
"""Build artifacts/index/ from whichever DailyMed zips exist.

From the aakaash folder:
    .venv\\Scripts\\python.exe scripts\\build_index.py                # chunks + TF-IDF (default ENCODER)
    set ENCODER=sbert & .venv\\Scripts\\python.exe scripts\\build_index.py   # sbert: OPTIONAL, NOT BUILT (about 6 h on this CPU; downloads the model)
    ... --probe 500            # time 500 chunks with the sbert encoder and stop (no index written)
Chunks are written once (pass 1, label by label, in batches); each encoder then reads chunks.jsonl."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
AAKAASH = HERE.parent
sys.path.insert(0, str(AAKAASH))
sys.path.insert(0, str(HERE))

from dailymed_stats import peak_working_set_mb  # noqa: E402
from medsafe.chunking import DEFAULT_OVERLAP, DEFAULT_SIZE, chunk_label  # noqa: E402
from medsafe.encoder import SBERT_MODEL, SbertEncoder, TfidfEncoder, encoder_name  # noqa: E402
from medsafe.forms import classify_label, describe  # noqa: E402
from medsafe.spl import iter_parts  # noqa: E402

BATCH = 2000
SHARD_CHUNKS = 256


def build_chunks(data_dir: Path, out: Path, size: int, overlap: int, cap: int | None) -> dict:
    """Pass 1. Label by label; chunk records are appended in batches of BATCH."""
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    labels, label_ix, seen = [], {}, set()
    sections: list[str] = []
    offsets, chunk_label_ix, chunk_section_ix, words = [], [], [], []
    sha = hashlib.sha256()
    pos, buf, size_buf = 0, [], 0
    parts: list[str] = []
    stats_by_part: dict = {}
    with open(out / "chunks.jsonl", "wb") as fh:
        def flush():
            nonlocal buf, pos, size_buf
            blob = b"".join(buf)
            fh.write(blob)
            sha.update(blob)
            pos += len(blob)
            buf, size_buf = [], 0
        for rec in iter_parts(data_dir, stats_by_part, cap):
            sid = rec["set_id"]
            if not sid or sid in seen:
                continue
            seen.add(sid)
            fams, inferred = classify_label(rec["dosage_forms"], rec["title"])
            forms = list(dict.fromkeys(p["form"] for p in rec["dosage_forms"]))
            routes = list(dict.fromkeys(r for p in rec["dosage_forms"] for r in p["routes"]))
            label_ix[sid] = len(labels)
            labels.append({"set_id": sid, "product": (rec["product_names"] or [rec["title"]])[0],
                           "title": rec["title"], "manufacturer": rec["manufacturer"],
                           "moieties": rec["active_moieties"], "form": describe(rec["dosage_forms"]),
                           "forms": forms, "routes": routes, "families": fams, "form_inferred": inferred,
                           "effective_time": rec["effective_time"]})
            lab = labels[-1]
            for ch in chunk_label(rec, size, overlap):
                if ch["section"] not in sections:
                    sections.append(ch["section"])
                line = json.dumps({"chunk_id": ch["chunk_id"], "set_id": sid, "section": ch["section"],
                                   "product": lab["product"], "moieties": lab["moieties"],
                                   "form": ", ".join(forms) or None, "route": ", ".join(routes) or None,
                                   "text": ch["text"]}, ensure_ascii=False).encode("utf-8") + b"\n"
                offsets.append(pos + size_buf)
                chunk_label_ix.append(label_ix[sid])
                chunk_section_ix.append(sections.index(ch["section"]))
                words.append(len(ch["text"].split()))
                buf.append(line)
                size_buf += len(line)
                if len(buf) >= BATCH:
                    flush()
        flush()
    parts = [z for z in stats_by_part]
    np.save(out / "chunk_offsets.npy", np.asarray(offsets, dtype=np.int64))
    np.save(out / "chunk_label.npy", np.asarray(chunk_label_ix, dtype=np.int32))
    np.save(out / "chunk_section.npy", np.asarray(chunk_section_ix, dtype=np.int8))
    np.save(out / "chunk_words.npy", np.asarray(words, dtype=np.int32))
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    per_section = {s: int(sum(1 for x in chunk_section_ix if x == k)) for k, s in enumerate(sections)}
    manifest = {"labels": len(labels), "chunks": len(offsets), "sections": sections,
                "chunks_per_section": per_section, "parts_loaded": parts, "chunk_size": size,
                "chunk_overlap": overlap, "chunk_unit": "whitespace words",
                "chunks_sha256": sha.hexdigest(), "chunks_bytes": pos,
                "chunk_seconds": round(time.perf_counter() - t0, 1), "is_sample": cap is not None,
                "parse_stats": {k: dict(v) for k, v in stats_by_part.items()}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def iter_chunk_texts(folder: Path):
    with open(folder / "chunks.jsonl", "rb") as fh:
        for line in fh:
            yield json.loads(line.decode("utf-8"))["text"]


def build_tfidf(folder: Path, top: dict) -> dict:
    import scipy.sparse as sp
    out = folder / "tfidf"
    out.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    enc = TfidfEncoder()
    X = enc.fit_transform(iter_chunk_texts(folder)).tocsr().astype(np.float32)
    sp.save_npz(out / "vectors.npz", X)
    enc.save(out)
    m = {"encoder": "tfidf", "is_deep_learning": False, "chunks_sha256": top["chunks_sha256"],
         "chunks": int(X.shape[0]), "vocabulary": enc.vocabulary_size(), "nnz": int(X.nnz),
         "settings": "TfidfVectorizer(sublinear_tf=True, stop_words='english', min_df=2, norm='l2')",
         "vector_bytes": (out / "vectors.npz").stat().st_size, "seconds": round(time.perf_counter() - t0, 1)}
    (out / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    return m


def build_sbert(folder: Path, top: dict, resume: bool = True) -> dict:
    out = folder / "sbert"
    shards = out / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    enc = SbertEncoder(SBERT_MODEL)
    _ = enc.model  # load (downloads on first use)
    revision = getattr(getattr(enc.model[0].auto_model, "config", None), "_commit_hash", None)
    n, n_shard = top["chunks"], 0
    texts, chunk_ids = [], []
    windows_total = multi = 0

    def run_shard(k: int, base: int, group: list[str]):
        nonlocal windows_total, multi
        f = shards / f"{k:05d}.npz"
        if resume and f.is_file():
            z = np.load(f)
            windows_total += len(z["chunk"])
            return
        wins, owner = [], []
        for j, t in enumerate(group):
            w = enc.windows(t)
            wins += w
            owner += [base + j] * len(w)
            multi += len(w) > 1
        vec = enc.encode(wins, batch_size=16)
        np.savez(f, vec=vec, chunk=np.asarray(owner, dtype=np.int64))
        windows_total += len(wins)
        done = base + len(group)
        el = time.perf_counter() - t0
        print(f"  encoded {done}/{n} chunks, {windows_total} windows, {el:.0f}s, peak RAM {peak_working_set_mb()} MB", flush=True)

    group, base, k = [], 0, 0
    for t in iter_chunk_texts(folder):
        group.append(t)
        if len(group) == SHARD_CHUNKS:
            run_shard(k, base, group)
            base, k, group = base + len(group), k + 1, []
    if group:
        run_shard(k, base, group)
    vecs, owners = [], []
    for f in sorted(shards.glob("*.npz")):
        z = np.load(f)
        vecs.append(z["vec"])
        owners.append(z["chunk"])
    V, owner = np.concatenate(vecs), np.concatenate(owners)
    np.save(out / "vectors.npy", V)
    np.save(out / "window_chunk.npy", owner)
    for f in shards.glob("*.npz"):
        f.unlink()
    shards.rmdir()
    cnt = np.bincount(owner, minlength=n)
    m = {"encoder": "sbert", "is_deep_learning": True, "model": SBERT_MODEL, "model_revision": revision,
         "chunks_sha256": top["chunks_sha256"], "chunks": n, "dimension": int(V.shape[1]),
         "windows": int(len(V)), "chunks_with_more_than_one_window": int((cnt > 1).sum()),
         "window_token_budget": 500, "window_overlap_words": 32,
         "vector_bytes": int(V.nbytes), "seconds": round(time.perf_counter() - t0, 1)}
    (out / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    return m


def probe(folder: Path, count: int) -> None:
    """Time `count` chunks with the sbert encoder and extrapolate. Writes nothing."""
    enc = SbertEncoder(SBERT_MODEL)
    t = time.perf_counter()
    _ = enc.model
    print(f"model load {time.perf_counter() - t:.1f}s")
    texts = []
    for x in iter_chunk_texts(folder):
        texts.append(x)
        if len(texts) >= count:
            break
    t = time.perf_counter()
    wins = [w for x in texts for w in enc.windows(x)]
    tw = time.perf_counter() - t
    t = time.perf_counter()
    enc.encode(wins, batch_size=16)
    te = time.perf_counter() - t
    total = json.loads((folder / "manifest.json").read_text())["chunks"]
    per = (tw + te) / len(texts)
    print(f"{len(texts)} chunks -> {len(wins)} windows; windowing {tw:.1f}s, encoding {te:.1f}s")
    print(f"extrapolated to {total} chunks: {per * total / 60:.0f} min (peak RAM {peak_working_set_mb()} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=AAKAASH.parent / "data" / "dailymed_rx")
    ap.add_argument("--out", type=Path, default=AAKAASH / "artifacts" / "index")
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE)
    ap.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    ap.add_argument("--max-labels-per-part", type=int, default=None, help="cap per zip; marks the index as a sample")
    ap.add_argument("--rechunk", action="store_true", help="rebuild chunks.jsonl even if present (invalidates other encoders)")
    ap.add_argument("--probe", type=int, default=None, help="time N chunks with sbert and stop")
    a = ap.parse_args()
    if a.probe:
        probe(a.out, a.probe)
        return
    t0 = time.perf_counter()
    have = (a.out / "manifest.json").is_file() and not a.rechunk
    if have:
        top = json.loads((a.out / "manifest.json").read_text(encoding="utf-8"))
        print(f"reusing chunks: {top['labels']} labels, {top['chunks']} chunks")
    else:
        if not list(a.data_dir.glob("*.zip")):
            sys.exit(f"No .zip files in {a.data_dir}; nothing to index.")
        top = build_chunks(a.data_dir, a.out, a.size, a.overlap, a.max_labels_per_part)
        print(f"labels {top['labels']}, chunks {top['chunks']}, chunking {top['chunk_seconds']}s, "
              f"peak RAM {peak_working_set_mb()} MB")
    name = encoder_name()
    print(f"encoder: {name}")
    m = build_tfidf(a.out, top) if name == "tfidf" else build_sbert(a.out, top)
    print(json.dumps(m, indent=1))
    size = sum(f.stat().st_size for f in a.out.rglob("*") if f.is_file())
    print(f"total {time.perf_counter() - t0:.1f}s, peak RAM {peak_working_set_mb()} MB, index folder {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
