# SOURCE: NOT IN PAPERS. FIXTURES ONLY: hand-written passages that exercise the retrieval code. None of it
# is real label text and none of it may appear in the UI. Writes the same files scripts/build_index.py
# writes (chunks.jsonl, offsets, label and section arrays, labels.json, tfidf vectors, manifests).
import hashlib
import json

import numpy as np
import scipy.sparse as sp

from medsafe.encoder import TfidfEncoder
from medsafe.forms import classify_label, describe

# (set id, section, text). Words repeat across passages so the min_df=2 vocabulary keeps them.
PASSAGES = [
    ("L-warf", "boxed_warning", "warning bleeding risk warfarin can cause major or fatal bleeding"),
    ("L-warf", "adverse_reactions", "bleeding and hemorrhage are the most common adverse reactions"),
    ("L-warf", "indications", "anticoagulant for prophylaxis and treatment of venous thrombosis"),
    ("L-apap-2", "indications", "management of mild to moderate pain and reduction of fever"),
    ("L-apap-2", "dosage_administration", "dose is 650 mg every six hours for pain and fever"),
    ("L-apap-2", "adverse_reactions", "hepatic injury after overdose and rash"),
    ("L-apap-1", "indications", "analgesic for pain and fever"),
    ("L-apap-inj", "indications", "management of mild to moderate pain and reduction of fever intravenous"),
    ("L-apap-inj", "dosage_administration", "inject 15 mg per kg intravenous for pain and fever"),
    ("L-metf", "indications", "adjunct to diet and exercise to improve glycemic control in type 2 diabetes mellitus"),
    ("L-combo", "indications", "improve glycemic control in adults with type 2 diabetes mellitus"),
    ("L-nacl", "indications", "source of water and electrolytes for fluid replacement"),
    ("L-nacl", "dosage_administration", "dosage depends on fluid deficit and electrolyte replacement"),
    ("L-kcl", "indications", "treatment of hypokalemia and electrolyte replacement"),
]


def write_index(art_dir, labels, passages=PASSAGES, encoder="tfidf"):
    folder = art_dir / "index"
    (folder / encoder).mkdir(parents=True, exist_ok=True)
    by_id = {l["set_id"]: l for l in labels}
    label_list, label_ix, sections = [], {}, []
    lines, offsets, cl, cs = [], [], [], []
    pos = 0
    for sid, sec, text in passages:
        l = by_id[sid]
        if sid not in label_ix:
            fams, inferred = classify_label(l["dosage_forms"], l["title"])
            label_ix[sid] = len(label_list)
            label_list.append({"set_id": sid, "product": l["products"][0], "title": l["title"],
                               "manufacturer": l["manufacturer"], "moieties": l["moieties"],
                               "form": describe(l["dosage_forms"]), "forms": [p["form"] for p in l["dosage_forms"]],
                               "routes": [r for p in l["dosage_forms"] for r in p["routes"]], "families": fams,
                               "form_inferred": inferred, "effective_time": l["effective_time"]})
        if sec not in sections:
            sections.append(sec)
        lab = label_list[label_ix[sid]]
        line = (json.dumps({"chunk_id": f"{sid}:{sec}:0", "set_id": sid, "section": sec, "product": lab["product"],
                            "moieties": lab["moieties"], "form": ", ".join(lab["forms"]) or None,
                            "route": ", ".join(lab["routes"]) or None, "text": text}) + "\n").encode()
        offsets.append(pos)
        pos += len(line)
        lines.append(line)
        cl.append(label_ix[sid])
        cs.append(sections.index(sec))
    blob = b"".join(lines)
    (folder / "chunks.jsonl").write_bytes(blob)
    np.save(folder / "chunk_offsets.npy", np.asarray(offsets, dtype=np.int64))
    np.save(folder / "chunk_label.npy", np.asarray(cl, dtype=np.int32))
    np.save(folder / "chunk_section.npy", np.asarray(cs, dtype=np.int8))
    (folder / "labels.json").write_text(json.dumps(label_list), encoding="utf-8")
    sha = hashlib.sha256(blob).hexdigest()
    top = {"labels": len(label_list), "chunks": len(passages), "sections": sections,
           "chunks_per_section": {s: cs.count(k) for k, s in enumerate(sections)}, "parts_loaded": ["x.zip"],
           "chunk_size": 512, "chunk_overlap": 64, "chunk_unit": "whitespace words", "chunks_sha256": sha,
           "is_sample": False}
    (folder / "manifest.json").write_text(json.dumps(top), encoding="utf-8")
    enc = TfidfEncoder()
    X = enc.fit_transform(p[2] for p in passages).tocsr().astype(np.float32)
    sp.save_npz(folder / encoder / "vectors.npz", X)
    enc.save(folder / encoder)
    (folder / encoder / "manifest.json").write_text(
        json.dumps({"encoder": encoder, "chunks_sha256": sha, "chunks": len(passages), "nnz": int(X.nnz),
                    "vector_bytes": 1, "seconds": 0.0}), encoding="utf-8")
    return folder
