# SOURCE: NOT IN PAPERS. Integrated Gradients (Captum, LayerIntegratedGradients) over the input
# tokens for the predicted class, merged back to words, and a deletion-based faithfulness proxy.
# P6's attention heat map comes from a module we do not implement, so it is not reproduced here.
# torch and captum are imported inside functions.
"""Token attributions for the DDI classifier, and a faithfulness proxy."""
from __future__ import annotations

import os
import random
import re

from .ddi_model import LABELS, MARKER_TOKENS, MAX_LEN, collate, encode_marked, predict_proba

IG_STEPS = int(os.environ.get("MEDSAFE_DDI_IG_STEPS", "50"))
_MARK = re.compile(r"</?e[12]>")


# ---------------------------------------------------------------- pure helpers

def plain_map(marked: str) -> list[int | None]:
    """For each index of `marked`, its index in the text without markers (None inside a marker)."""
    out, j, i = [], 0, 0
    while i < len(marked):
        m = _MARK.match(marked, i)
        if m:
            out.extend([None] * (m.end() - i))
            i = m.end()
        else:
            out.append(j)
            j += 1
            i += 1
    return out


def entity_spans(marked: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """Character spans of e1 and e2 in the text without markers."""
    pm = plain_map(marked)
    spans = []
    for tag in ("e1", "e2"):
        a, b = marked.index(f"<{tag}>") + len(tag) + 2, marked.index(f"</{tag}>")
        spans.append((pm[a], pm[b - 1] + 1))
    return spans[0], spans[1]


def merge_words(marked: str, pieces: list[dict]) -> list[dict]:
    """Merge word-piece scores into words. `pieces`: dicts with start, end (offsets into `marked`),
    word_id and score; marker and special tokens are not passed in. A word is the pieces sharing a
    word_id; its score is their sum; its span is in the text without markers."""
    pm = plain_map(marked)
    e1, e2 = entity_spans(marked)
    by_word: dict[int, list[dict]] = {}
    for p in pieces:
        by_word.setdefault(p["word_id"], []).append(p)
    plain = _MARK.sub("", marked)
    words = []
    for wid in sorted(by_word):
        ps = by_word[wid]
        a = pm[min(p["start"] for p in ps)]
        b = pm[max(p["end"] for p in ps) - 1] + 1
        drug = any(a >= s and b <= e for s, e in (e1, e2))
        words.append({"text": plain[a:b], "start": a, "end": b, "attribution": float(sum(p["score"] for p in ps)),
                      "is_drug": drug})
    return words


def delete_words(marked: str, words: list[dict]) -> str:
    """`marked` without the given words (spans are in the marker-free text), markers kept."""
    pm = plain_map(marked)
    inv = {j: i for i, j in enumerate(pm) if j is not None}
    out = marked
    for w in sorted(words, key=lambda w: w["start"], reverse=True):
        out = out[:inv[w["start"]]] + out[inv[w["end"] - 1] + 1:]
    return re.sub(r"[ \t]{2,}", " ", out)


def eligible(words: list[dict]) -> list[dict]:
    """Words that may be deleted in the faithfulness check: not a drug name, has a letter or digit."""
    return [w for w in words if not w["is_drug"] and re.search(r"\w", w["text"])]


# ---------------------------------------------------------------- Integrated Gradients

def explain(model, tok, marked: str, max_len: int = MAX_LEN, n_steps: int = IG_STEPS, target: int | None = None) -> dict:
    """Probabilities, predicted class and per-word attributions (IG on the word embeddings, target =
    predicted-class probability, baseline = [PAD] everywhere except [CLS], [SEP] and the markers)."""
    import torch
    from captum.attr import LayerIntegratedGradients

    device = next(model.parameters()).device
    enc = encode_marked(tok, marked, max_len)
    batch = {k: v.to(device) for k, v in collate([enc], tok.pad_token_id).items()}
    with torch.no_grad():
        probs = torch.softmax(model(**batch).float(), dim=-1)[0]
    pred = int(probs.argmax()) if target is None else target

    keep = set(tok.convert_tokens_to_ids(MARKER_TOKENS)) | {tok.cls_token_id, tok.sep_token_id}
    ids = batch["input_ids"]
    base = torch.where(torch.tensor([[t in keep for t in ids[0].tolist()]], device=device), ids,
                       torch.full_like(ids, tok.pad_token_id))

    def fwd(input_ids, attention_mask, e1_mask, e2_mask):
        return torch.softmax(model(input_ids, attention_mask, e1_mask, e2_mask).float(), dim=-1)

    lig = LayerIntegratedGradients(fwd, model.bert.embeddings.word_embeddings)
    cudnn_off = torch.backends.cudnn.flags(enabled=False)  # cuDNN RNN backward needs train mode
    with cudnn_off:
        attr, delta = lig.attribute(ids, baselines=base, additional_forward_args=(
            batch["attention_mask"], batch["e1_mask"], batch["e2_mask"]), target=pred, n_steps=n_steps,
            return_convergence_delta=True)
    scores = attr.sum(-1)[0].detach().cpu().tolist()

    pieces = [{"start": o[0], "end": o[1], "word_id": w, "score": s}
              for o, w, s, t in zip(enc["offsets"], enc["word_ids"], scores, enc["ids"])
              if w is not None and t not in keep]
    return {"probabilities": [float(p) for p in probs], "predicted": LABELS[pred],
            "words": merge_words(marked, pieces), "n_steps": n_steps, "delta": float(delta.abs().max()),
            "truncated": enc["truncated"]}


# ---------------------------------------------------------------- faithfulness proxy

def faithfulness(model, tok, marked_texts: list[str], ks=(1, 3, 5), seed: int = 13, draws: int = 5,
                 max_len: int = MAX_LEN, n_steps: int = IG_STEPS) -> dict:
    """A faithfulness proxy, not proof that an explanation is right. For each sentence: delete the top-k
    positively attributed words (not drug names), and k random eligible words (`draws` draws, fixed
    seed), and record the drop in the predicted-class probability. Sentences with fewer than k
    eligible words are skipped for that k and counted."""
    rng = random.Random(seed)
    acc = {k: {"top": [], "rand": [], "skipped": 0} for k in ks}
    for text in marked_texts:
        ex = explain(model, tok, text, max_len, n_steps)
        c = LABELS.index(ex["predicted"])
        p0 = ex["probabilities"][c]
        pool = eligible(ex["words"])
        ranked = sorted((w for w in pool if w["attribution"] > 0), key=lambda w: -w["attribution"])
        for k in ks:
            if len(pool) < k or len(ranked) < k:
                acc[k]["skipped"] += 1
                continue
            variants = [delete_words(text, ranked[:k])] + [delete_words(text, rng.sample(pool, k)) for _ in range(draws)]
            ps = [p[c] for p in predict_proba(model, tok, variants, max_len)]
            acc[k]["top"].append(p0 - ps[0])
            acc[k]["rand"].append(sum(p0 - p for p in ps[1:]) / draws)
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None
    return {"label": "a faithfulness proxy", "seed": seed, "random_draws": draws, "n_steps": n_steps,
            "n_sentences": len(marked_texts),
            "by_k": {str(k): {"n": len(a["top"]), "skipped": a["skipped"], "mean_drop_top_k": mean(a["top"]),
                              "mean_drop_random_k": mean(a["rand"])} for k, a in acc.items()}}
