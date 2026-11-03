# SOURCE: FROM PAPERS: P6 (Jia et al., iScience 2026): focal loss FL(p_t) = -alpha_t (1-p_t)^gamma log p_t
# (Eq. 13), BioBERT then BiLSTM, entity markers, dropout 0.2, two 256-unit ReLU layers, max length 300
# (locations UNVERIFIED: check 3.pdf; taken from the project brief). P6's dual graph, GCN and GAN parts are
# NOT implemented. NOT IN PAPERS: the [CLS] + entity-mean pooling head, BiLSTM size (1 layer, 256 per
# direction), the alpha modes, the window cut for long inputs, and the checkpoint format.
# torch and transformers are imported inside functions: cold imports take about a minute.
"""Model, loss, tokenisation and metrics for the DDI Extraction 2013 classifier."""
from __future__ import annotations

import functools
import json
from collections import Counter
from pathlib import Path

from .ddi2013 import ALL_LABELS, POSITIVE_CLASSES

LABELS = list(ALL_LABELS)  # effect, mechanism, advise, int, false
LABEL_INDEX = {l: i for i, l in enumerate(LABELS)}
MARKER_TOKENS = ["<e1>", "</e1>", "<e2>", "</e2>"]
ENCODER_ID = "dmis-lab/biobert-base-cased-v1.1"
ENCODER_COMMIT = "924f12e0c3db7f156a765ad53fb6b11e7afedbc8"
MAX_LEN = 300
MODEL_FILE, CONFIG_FILE = "model.safetensors", "config.json"


# ---------------------------------------------------------------- pure helpers (no torch)

def alpha_weights(counts: dict[str, int], mode: str) -> list[float]:
    """Per-class alpha in LABELS order, from train counts, rescaled to mean 1.
    none: all 1. inv: N / (K n_c). sqrt_inv: 1 / sqrt(n_c)."""
    if mode == "none":
        return [1.0] * len(LABELS)
    n = [max(counts.get(l, 0), 1) for l in LABELS]
    total, k = sum(n), len(n)
    if mode == "inv":
        w = [total / (k * c) for c in n]
    elif mode == "sqrt_inv":
        w = [c ** -0.5 for c in n]
    else:
        raise ValueError(f"unknown alpha mode {mode!r}")
    mean = sum(w) / k
    return [x / mean for x in w]


def metrics(gold: list[str], pred: list[str]) -> dict:
    """Micro precision, recall and F1 over the four positive classes (false is ignored: a pair
    counts as a hit only when the class is right), per-class P/R/F1/support, 5x5 confusion matrix
    (rows gold, columns predicted, LABELS order)."""
    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return p, r, (2 * p * r / (p + r) if p + r else 0.0)

    per = {}
    for c in LABELS:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        p, r, f = prf(tp, fp, fn)
        per[c] = {"precision": p, "recall": r, "f1": f, "support": tp + fn, "tp": tp, "fp": fp, "fn": fn}
    tp = sum(per[c]["tp"] for c in POSITIVE_CLASSES)
    fp = sum(per[c]["fp"] for c in POSITIVE_CLASSES)
    fn = sum(per[c]["fn"] for c in POSITIVE_CLASSES)
    p, r, f = prf(tp, fp, fn)
    cm = [[0] * len(LABELS) for _ in LABELS]
    for g, q in zip(gold, pred):
        cm[LABEL_INDEX[g]][LABEL_INDEX[q]] += 1
    return {"micro": {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn},
            "per_class": per, "confusion_matrix": cm, "labels": LABELS, "n": len(gold)}


def label_counts(rows) -> dict[str, int]:
    return dict(Counter(r["label"] for r in rows))


# ---------------------------------------------------------------- tokenisation

def build_tokenizer(vocab_file: str | Path):
    """Cased WordPiece tokenizer (BioBERT is cased; its repo has no tokenizer config) plus the four
    entity markers as single tokens."""
    from transformers import BertTokenizerFast

    # transformers 5 names this argument `vocab`; `vocab_file=` is swallowed by **kwargs and gives an
    # almost empty vocabulary (every word [UNK]). The size check below makes that failure loud.
    tok = BertTokenizerFast(vocab=str(vocab_file), do_lower_case=False)
    tok.add_special_tokens({"additional_special_tokens": MARKER_TOKENS})
    n_vocab = sum(1 for line in Path(vocab_file).read_text(encoding="utf-8").splitlines() if line.strip())
    if len(tok) != n_vocab + len(MARKER_TOKENS):
        raise RuntimeError(f"Tokenizer has {len(tok)} entries but {Path(vocab_file).name} has {n_vocab} lines + "
                           f"{len(MARKER_TOKENS)} markers: the vocabulary was not loaded.")
    return tok


def unk_rate(tok, texts: list[str]) -> float:
    """Share of word pieces that are [UNK] over `texts` (markers excluded from the count)."""
    unk = total = 0
    for t in texts:
        ids = tok(t, add_special_tokens=False)["input_ids"]
        unk += sum(i == tok.unk_token_id for i in ids)
        total += len(ids)
    return unk / max(total, 1)


def encode_marked(tok, marked_text: str, max_len: int = MAX_LEN) -> dict:
    """Token ids with [CLS]/[SEP], character offsets into `marked_text`, word ids, and the positions
    of the entity pieces (strictly between the markers). Inputs longer than max_len are cut to a
    window that keeps both entities when they fit (`truncated` is True)."""
    enc = tok(marked_text, add_special_tokens=False, return_offsets_mapping=True)
    ids, offs, words = list(enc["input_ids"]), list(enc["offset_mapping"]), list(enc.word_ids())
    m = tok.convert_tokens_to_ids(MARKER_TOKENS)
    truncated = False
    room = max_len - 2
    if len(ids) > room:
        truncated = True
        pos = [i for i, t in enumerate(ids) if t in m]
        lo, hi = (pos[0], pos[-1]) if pos else (0, 0)
        start = max(0, min(lo - (room - (hi - lo + 1)) // 2, len(ids) - room)) if hi - lo + 1 <= room else lo
        ids, offs, words = ids[start:start + room], offs[start:start + room], words[start:start + room]
    ids = [tok.cls_token_id] + ids + [tok.sep_token_id]
    offs = [(0, 0)] + offs + [(0, 0)]
    words = [None] + words + [None]

    def span(open_id, close_id):
        o = next((i for i, t in enumerate(ids) if t == open_id), None)
        c = next((i for i, t in enumerate(ids) if t == close_id and o is not None and i > o), None)
        if o is None:
            return [0]  # marker lost to truncation: fall back to [CLS]
        inner = list(range(o + 1, c)) if c is not None else []
        return inner or [o]

    return {"ids": ids, "offsets": offs, "word_ids": words, "e1": span(m[0], m[1]), "e2": span(m[2], m[3]),
            "truncated": truncated}


def collate(encs: list[dict], pad_id: int):
    import torch

    n, length = len(encs), max(len(e["ids"]) for e in encs)
    ids = torch.full((n, length), pad_id, dtype=torch.long)
    att = torch.zeros((n, length), dtype=torch.long)
    e1 = torch.zeros((n, length))
    e2 = torch.zeros((n, length))
    for i, e in enumerate(encs):
        k = len(e["ids"])
        ids[i, :k] = torch.tensor(e["ids"])
        att[i, :k] = 1
        e1[i, e["e1"]] = 1
        e2[i, e["e2"]] = 1
    return {"input_ids": ids, "attention_mask": att, "e1_mask": e1, "e2_mask": e2}


def iter_batches(encs: list[dict], labels: list[int], batch_size: int, order: list[int], pad_id: int):
    """Yield (batch dict, y tensor, indices). The inputs and the labels come from the same index list,
    so a shuffle cannot misalign them."""
    import torch

    for i in range(0, len(order), batch_size):
        idx = order[i:i + batch_size]
        yield collate([encs[j] for j in idx], pad_id), torch.tensor([labels[j] for j in idx]), idx


def constant_output_warning(pred: list[str], gold: list[str] | None = None) -> str | None:
    """A warning text when the predictions use one class only (the model is ignoring its input)."""
    used = sorted(set(pred))
    if len(pred) > 1 and len(used) == 1:
        return f"predicts only one class: {used[0]}"
    return None


def baselines(gold: list[str]) -> dict:
    """Metrics of constant predictors on `gold`: the majority class and the most frequent positive class."""
    cnt = Counter(gold)
    maj = max(LABELS, key=lambda l: cnt.get(l, 0))
    pos = max(POSITIVE_CLASSES, key=lambda l: cnt.get(l, 0))
    return {name: {"label": l, "micro_f1": metrics(gold, [l] * len(gold))["micro"]["f1"]}
            for name, l in (("majority", maj), ("most_frequent_positive", pos))}


# ---------------------------------------------------------------- torch classes (built on first use)

@functools.lru_cache(maxsize=1)
def torch_classes():
    import torch
    from torch import nn
    from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

    class FocalLoss(nn.Module):
        """FL = -alpha_y (1 - p_y)^gamma log p_y, mean over the batch. gamma=0 with alpha all 1 is
        cross-entropy; gamma=0 with alpha is alpha-weighted cross-entropy (mean over N)."""

        def __init__(self, gamma: float = 2.0, alpha=None):
            super().__init__()
            self.gamma = float(gamma)
            self.register_buffer("alpha", None if alpha is None else torch.as_tensor(alpha, dtype=torch.float32))

        def forward(self, logits, target):
            logp = torch.log_softmax(logits.float(), dim=-1).gather(1, target[:, None])[:, 0]
            loss = -((1 - logp.exp()) ** self.gamma) * logp
            if self.alpha is not None:
                loss = loss * self.alpha[target]
            return loss.mean()

    class DDIModel(nn.Module):
        """BERT encoder -> dropout -> BiLSTM -> [h_CLS ; mean(e1 pieces) ; mean(e2 pieces)] ->
        Dropout, Linear(3*2H, 256), ReLU, Dropout, Linear(256, 256), ReLU, Dropout, Linear(256, 5)."""

        def __init__(self, bert, lstm_hidden=256, head_hidden=256, dropout=0.2, n_classes=len(LABELS)):
            super().__init__()
            self.bert = bert
            self.drop = nn.Dropout(dropout)
            self.lstm = nn.LSTM(bert.config.hidden_size, lstm_hidden, batch_first=True, bidirectional=True)
            d = 3 * 2 * lstm_hidden
            self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(d, head_hidden), nn.ReLU(), nn.Dropout(dropout),
                                      nn.Linear(head_hidden, head_hidden), nn.ReLU(), nn.Dropout(dropout),
                                      nn.Linear(head_hidden, n_classes))

        def forward(self, input_ids, attention_mask, e1_mask, e2_mask):
            h = self.drop(self.bert(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state)
            packed = pack_padded_sequence(h, attention_mask.sum(1).cpu(), batch_first=True, enforce_sorted=False)
            out, _ = self.lstm(packed)
            out, _ = pad_packed_sequence(out, batch_first=True, total_length=h.size(1))

            def pool(mask):
                mask = mask.unsqueeze(-1).to(out.dtype)
                return (out * mask).sum(1) / mask.sum(1).clamp(min=1)

            return self.head(torch.cat([out[:, 0], pool(e1_mask), pool(e2_mask)], dim=-1))

    return DDIModel, FocalLoss


def make_loss(loss: str, gamma: float, alpha: list[float] | None):
    _, focal = torch_classes()
    if loss == "ce":
        return focal(0.0, None)  # exactly cross-entropy
    if loss == "focal":
        return focal(gamma, alpha)
    raise ValueError(f"unknown loss {loss!r}")


# ---------------------------------------------------------------- checkpoint

def save_checkpoint(model, tok, cfg: dict, out_dir: Path) -> Path:
    from safetensors.torch import save_file

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}, str(out_dir / MODEL_FILE))
    tok.save_pretrained(str(out_dir))
    full = dict(cfg, labels=LABELS, bert_config=model.bert.config.to_dict(), markers=MARKER_TOKENS)
    (out_dir / CONFIG_FILE).write_text(json.dumps(full, indent=2), encoding="utf-8")
    return out_dir


def read_config(model_dir: Path) -> dict | None:
    try:
        return json.loads((Path(model_dir) / CONFIG_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def checkpoint_present(model_dir: Path) -> bool:
    d = Path(model_dir)
    return (d / MODEL_FILE).is_file() and (d / CONFIG_FILE).is_file()


def load_checkpoint(model_dir: Path):
    """(model in eval mode on CPU, tokenizer, config). Needs no network: the encoder is rebuilt
    from the saved config and filled from model.safetensors."""
    from safetensors.torch import load_file
    from transformers import BertConfig, BertModel, BertTokenizerFast

    d = Path(model_dir)
    cfg = read_config(d)
    if cfg is None or not (d / MODEL_FILE).is_file():
        raise FileNotFoundError(f"No checkpoint in {d.name}")
    tok = BertTokenizerFast.from_pretrained(str(d))
    model_cls, _ = torch_classes()
    bert = BertModel(BertConfig.from_dict(cfg["bert_config"]), add_pooling_layer=False)
    if len(tok) != bert.config.vocab_size:
        raise RuntimeError(f"Tokenizer size {len(tok)} differs from the encoder vocabulary {bert.config.vocab_size}.")
    model = model_cls(bert, cfg["lstm_hidden"], cfg["head_hidden"], cfg["dropout"])
    model.load_state_dict(load_file(str(d / MODEL_FILE)))
    return model.eval(), tok, cfg


def predict_proba(model, tok, marked_texts: list[str], max_len: int = MAX_LEN, batch_size: int = 16):
    """Class probabilities (LABELS order) for each marked text. CPU or whatever device `model` is on."""
    import torch

    device = next(model.parameters()).device
    out = []
    with torch.no_grad():
        for i in range(0, len(marked_texts), batch_size):
            encs = [encode_marked(tok, t, max_len) for t in marked_texts[i:i + batch_size]]
            batch = {k: v.to(device) for k, v in collate(encs, tok.pad_token_id).items()}
            out.extend(torch.softmax(model(**batch).float(), dim=-1).cpu().tolist())
    return out
