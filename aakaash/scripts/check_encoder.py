# SOURCE: NOT IN PAPERS (own tooling). Fail-fast check before a long training run: builds the encoder,
# the model and one batch, runs a forward and backward pass, prints shapes, parameter count and memory.
"""Run first on the GPU machine:  python scripts/check_encoder.py        (BioBERT, downloads ~436 MB)
Locally, without a download:       python scripts/check_encoder.py --smoke  (tiny random BERT)"""
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import train_ddi as t  # noqa: E402
from medsafe import ddi_model as dm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--data-dir", default=str(ROOT / "artifacts" / "ddi2013"))
    ap.add_argument("--work-dir", default=str(ROOT / "artifacts" / "work"))
    a = ap.parse_args()
    import time

    import torch

    rows = t.read_jsonl(Path(a.data_dir) / "train.jsonl")[:8]
    args = types.SimpleNamespace(smoke=a.smoke, encoder=dm.ENCODER_ID, encoder_commit=dm.ENCODER_COMMIT)
    t0 = time.time()
    bert, tok, info = t.make_encoder(args, rows, Path(a.work_dir))
    print("encoder:", info, f"({time.time() - t0:.1f}s)  vocab size {len(tok)}  markers",
          tok.convert_tokens_to_ids(dm.MARKER_TOKENS))
    base = len(tok) - len(dm.MARKER_TOKENS)
    rate = dm.unk_rate(tok, [r["marked_text"] for r in rows])
    emb = bert.get_input_embeddings().weight.shape[0]
    print(f"base vocabulary {base} + {len(dm.MARKER_TOKENS)} markers = {len(tok)}; embedding rows {emb}; [UNK] rate on 8 train sentences {rate:.4f}")
    print("(vocab size 9 would mean the vocabulary file was NOT loaded: 5 specials + 4 markers)")
    assert base > 1000 and emb == len(tok), f"tokenizer/encoder mismatch: base {base}, embedding rows {emb}"
    assert rate < 0.05, f"[UNK] rate {rate:.3f}: the tokenizer is not reading the vocabulary"
    assert len(set(tok.convert_tokens_to_ids(dm.MARKER_TOKENS))) == 4 and tok.unk_token_id not in tok.convert_tokens_to_ids(dm.MARKER_TOKENS)
    if not a.smoke:
        assert base == 28996, f"BioBERT cased vocabulary should have 28996 entries, got {base}"
    model_cls, loss_cls = dm.torch_classes()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model_cls(bert).to(device)
    print("parameters:", sum(p.numel() for p in model.parameters()), "device:", device)
    encs = [dm.encode_marked(tok, r["marked_text"], dm.MAX_LEN) for r in rows]
    b = {k: v.to(device) for k, v in dm.collate(encs, tok.pad_token_id).items()}
    print("batch shapes:", {k: tuple(v.shape) for k, v in b.items()})
    logits = model(**b)
    y = torch.tensor([dm.LABEL_INDEX[r["label"]] for r in rows], device=device)
    loss = loss_cls(2.0, None).to(device)(logits, y)
    loss.backward()
    print("logits", tuple(logits.shape), "loss", round(loss.item(), 4), "all grads finite:",
          all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None))
    if device.type == "cuda":
        print("peak GPU memory (batch of 8, fp32):", round(torch.cuda.max_memory_allocated() / 2**20), "MiB")
    print("OK")


if __name__ == "__main__":
    main()
