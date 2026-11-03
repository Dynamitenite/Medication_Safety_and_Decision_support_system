# SOURCE: FROM PAPERS: P6 (focal loss, BioBERT -> BiLSTM, batch 8, up to 20 epochs, max length 300,
# dropout 0.2, micro P/R/F1 over the four positive classes; locations UNVERIFIED: check 3.pdf).
# NOT IN PAPERS: the staged dev-set search, AdamW + linear warm-up, two learning rates (encoder / head),
# early stopping on dev micro-F1, the seed, and the smoke test.
"""Train and evaluate the DDI classifier (CE vs focal). Run on a GPU for real results.

  python scripts/train_ddi.py search --out-dir artifacts            # dev set only
  python scripts/train_ddi.py final --loss ce    --from-search --out-dir artifacts
  python scripts/train_ddi.py final --loss focal --from-search --out-dir artifacts --faithfulness 300
  python scripts/train_ddi.py final --smoke                        # CPU pipeline check, tiny random BERT

The test set is read only by `final`, once per output file (refuses to overwrite without --force).
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medsafe import ddi_model as dm  # noqa: E402  (no torch import at module level)

PACKAGES = ["torch", "transformers", "tokenizers", "safetensors", "numpy", "scikit-learn", "lxml", "captum",
            "huggingface_hub", "accelerate"]
ENC_LR_RANGE, HEAD_LR_RANGE = (1e-5, 5e-5), (1e-4, 1e-3)   # NOT IN PAPERS; P6's single 5e-4 is not used
LR_GRID = [1e-5, 2e-5, 3e-5, 5e-5]
HEAD_LR_EXTRA = [1e-4, 1e-3]
GAMMAS, ALPHAS = [1.0, 2.0, 3.0], ["none", "sqrt_inv", "inv"]


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


class Log:
    def __init__(self, path: Path | None):
        self.fh = None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.fh = open(path, "a", encoding="utf-8")

    def __call__(self, *a):
        line = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
        print(line, flush=True)
        if self.fh:
            self.fh.write(line + "\n")
            self.fh.flush()


def versions() -> dict:
    out = {"python": platform.python_version(), "platform": platform.platform(), "packages": {}}
    for p in PACKAGES:
        try:
            out["packages"][p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            out["packages"][p] = None
    try:
        import torch
        out["cuda"] = torch.version.cuda
        out["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception as e:  # noqa: BLE001
        out["cuda_error"] = str(e)
    try:
        out["pip_freeze"] = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True,
                                           timeout=120).stdout.splitlines()
    except Exception:  # noqa: BLE001
        out["pip_freeze"] = None
    return out


def seed_all(seed: int):
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------- encoder

def make_encoder(args, train_rows, work: Path):
    """(bert, tokenizer, info). Real: BioBERT from Hugging Face at a pinned commit. Smoke: a tiny
    randomly initialised BERT with a vocabulary learned from the training text (no download)."""
    from transformers import BertConfig, BertModel

    if args.smoke:
        from tokenizers import BertWordPieceTokenizer

        wp = BertWordPieceTokenizer(lowercase=False)
        wp.train_from_iterator([r["text"] for r in train_rows], vocab_size=1500, min_frequency=1)
        vdir = work / "smoke_vocab"
        vdir.mkdir(parents=True, exist_ok=True)
        wp.save_model(str(vdir))
        tok = dm.build_tokenizer(vdir / "vocab.txt")
        cfg = BertConfig(vocab_size=len(tok), hidden_size=64, num_hidden_layers=2, num_attention_heads=2,
                         intermediate_size=128, max_position_embeddings=512)
        bert = BertModel(cfg, add_pooling_layer=False)
        return bert, tok, {"encoder": "tiny random BERT (smoke test, not BioBERT)", "encoder_commit": None}
    from huggingface_hub import hf_hub_download

    rev = args.encoder_commit
    vocab = hf_hub_download(args.encoder, "vocab.txt", revision=rev)
    tok = dm.build_tokenizer(vocab)
    cfg = BertConfig.from_pretrained(args.encoder, revision=rev)
    bert = BertModel.from_pretrained(args.encoder, config=cfg, revision=rev, add_pooling_layer=False)
    bert.resize_token_embeddings(len(tok))
    return bert, tok, {"encoder": args.encoder, "encoder_commit": rev}


# ---------------------------------------------------------------- one training run

def evaluate(model, encs, rows, tok, device, batch_size=32):
    import torch

    model.eval()
    probs = []
    with torch.no_grad():
        for i in range(0, len(encs), batch_size):
            b = {k: v.to(device) for k, v in dm.collate(encs[i:i + batch_size], tok.pad_token_id).items()}
            probs.extend(torch.softmax(model(**b).float(), -1).cpu().tolist())
    pred = [dm.LABELS[max(range(5), key=p.__getitem__)] for p in probs]
    return dm.metrics([r["label"] for r in rows], pred), pred, probs


class QualityGateError(SystemExit):
    """Raised (as an exit with a message) when a run is too weak to report."""


def check_lr_ranges(cfg: dict):
    if not ENC_LR_RANGE[0] <= cfg["lr_encoder"] <= ENC_LR_RANGE[1]:
        raise ValueError(f"encoder lr {cfg['lr_encoder']} outside {ENC_LR_RANGE}")
    if not HEAD_LR_RANGE[0] <= cfg["lr_head"] <= HEAD_LR_RANGE[1]:
        raise ValueError(f"head lr {cfg['lr_head']} outside {HEAD_LR_RANGE}")


def param_groups(model, lr_encoder, lr_head, weight_decay=0.01):
    """Encoder / head groups; no weight decay on biases and LayerNorm."""
    groups = {}
    for n, p in model.named_parameters():
        enc = n.startswith("bert.")
        nodecay = n.endswith(".bias") or "LayerNorm" in n or "layer_norm" in n
        groups.setdefault((enc, nodecay), []).append(p)
    return [{"params": ps, "lr": lr_encoder if enc else lr_head, "weight_decay": 0.0 if nd else weight_decay}
            for (enc, nd), ps in sorted(groups.items())]


def train_run(args, cfg: dict, bert, tok, train_rows, dev_rows, log: Log, gate: bool = False):
    """Train with `cfg` (loss, gamma, alpha, lr_encoder, lr_head, epochs, patience). Returns the best-dev-epoch
    model (loaded back in) and a result dict. Reads only train and dev."""
    import torch
    from transformers import get_linear_schedule_with_warmup

    check_lr_ranges(cfg)
    seed_all(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_cls, _ = dm.torch_classes()
    model = model_cls(bert, args.lstm_hidden, args.head_hidden, args.dropout).to(device)
    alpha = dm.alpha_weights(dm.label_counts(train_rows), cfg["alpha"]) if cfg["loss"] == "focal" else None
    loss_fn = dm.make_loss(cfg["loss"], cfg["gamma"], alpha).to(device)
    log("run", json.dumps(cfg), "alpha_weights", alpha)

    tr = [dm.encode_marked(tok, r["marked_text"], args.max_len) for r in train_rows]
    dv = [dm.encode_marked(tok, r["marked_text"], args.max_len) for r in dev_rows]
    log("truncated inputs: train", sum(e["truncated"] for e in tr), "dev", sum(e["truncated"] for e in dv))
    y = [dm.LABEL_INDEX[r["label"]] for r in train_rows]

    opt = torch.optim.AdamW(param_groups(model, cfg["lr_encoder"], cfg["lr_head"]))
    steps = cfg["epochs"] * ((len(tr) + args.batch_size - 1) // args.batch_size)
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)
    amp = args.amp and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    gen = torch.Generator().manual_seed(args.seed)

    history, best, best_state, bad = [], None, None, 0
    for epoch in range(1, cfg["epochs"] + 1):
        model.train()
        t0, total, nb = time.time(), 0.0, 0
        order = torch.randperm(len(tr), generator=gen).tolist()
        for b, yb, _ in dm.iter_batches(tr, y, args.batch_size, order, tok.pad_token_id):
            b = {k: v.to(device) for k, v in b.items()}
            with torch.autocast(device.type, dtype=torch.float16, enabled=amp):
                logits = model(**b)
            loss = loss_fn(logits, yb.to(device))
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
            nb += 1
        m, dpred, _ = evaluate(model, dv, dev_rows, tok, device)
        f1 = m["micro"]["f1"]
        warn = dm.constant_output_warning(dpred)
        if warn:
            log("WARNING", warn)
        if gate and epoch == args.gate_epoch and (f1 < args.gate_f1 or warn):
            raise QualityGateError(
                f"QUALITY GATE FAILED: dev micro-F1 {f1:.4f} after epoch {epoch} (needs >= {args.gate_f1}"
                f"{'; ' + warn if warn else ''}). The run is stopped and nothing is saved or reported. "
                "Check the tokenizer (scripts/check_encoder.py) and run scripts/diagnose_ddi.py.")
        history.append({"epoch": epoch, "train_loss": total / max(nb, 1), "dev_micro_f1": f1,
                        "dev_micro_precision": m["micro"]["precision"], "dev_micro_recall": m["micro"]["recall"], "dev_warning": warn,
                        "seconds": time.time() - t0})
        log(f"epoch {epoch} train_loss {total / max(nb, 1):.4f} dev_micro_f1 {f1:.4f} ({time.time() - t0:.0f}s)")
        if best is None or f1 > best:
            best, best_state, bad = f1, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}, 0
            best_epoch = epoch
        else:
            bad += 1
            if bad >= cfg.get("patience", 3):
                log("early stop")
                break
    model.load_state_dict(best_state)
    m, pred, probs = evaluate(model, dv, dev_rows, tok, device)
    return model, {"config": cfg, "alpha_weights": alpha, "best_epoch": best_epoch, "history": history,
                   "dev": m, "dev_pred": pred, "dev_probs": probs, "warning": dm.constant_output_warning(pred),
                   "baselines": dm.baselines([r["label"] for r in dev_rows])}


# ---------------------------------------------------------------- commands

def load_data(args):
    d = Path(args.data_dir)
    train, dev = read_jsonl(d / "train.jsonl"), read_jsonl(d / "dev.jsonl")
    rng = random.Random(args.seed)
    if args.limit_train:
        train = rng.sample(train, min(args.limit_train, len(train)))
    if args.limit_dev:
        dev = rng.sample(dev, min(args.limit_dev, len(dev)))
    return train, dev


def base_cfg(args, loss):
    return {"loss": loss, "gamma": args.gamma if loss == "focal" else 0.0, "alpha": args.alpha if loss == "focal" else "none",
            "lr_encoder": args.lr_encoder, "lr_head": args.lr_head, "epochs": args.epochs, "patience": args.patience}


def cmd_search(args):
    """Dev-set search. Stage 1: learning rate for CE and focal (+ one run with Jia's 5e-4 everywhere).
    Stage 2: gamma x alpha for focal at its best learning rate. Resumable: finished runs are skipped."""
    out = Path(args.out_dir)
    path = out / "metrics" / "ddi_search.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"runs": {}}
    log = Log(out / "metrics" / "ddi_runs" / "search" / "training_log.txt")
    train, dev = load_data(args)

    def run(cfg):
        key = json.dumps(cfg, sort_keys=True)
        if key in state["runs"]:
            log("skip (done)", key)
            return state["runs"][key]
        bert, tok, info = make_encoder(args, train, out / "work")
        _, res = train_run(args, cfg, bert, tok, train, dev, log)
        if res["warning"]:
            log("WARNING search run", key, res["warning"])
        rec = {"config": cfg, "best_epoch": res["best_epoch"], "dev_micro": res["dev"]["micro"],
               "warning": res["warning"], "baselines": res["baselines"],
               "dev_per_class_f1": {c: v["f1"] for c, v in res["dev"]["per_class"].items()}, "history": res["history"]}
        state["runs"][key] = rec
        state["baselines"] = res["baselines"]
        state.update({"smoke_test": args.smoke, "seed": args.seed, "set": "dev only", **info})
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return rec

    stage1 = {}
    for loss in ("ce", "focal"):
        for lr in LR_GRID:
            cfg = dict(base_cfg(args, loss), lr_encoder=lr, lr_head=5e-4, gamma=2.0 if loss == "focal" else 0.0,
                       alpha="inv" if loss == "focal" else "none", epochs=args.search_epochs, patience=args.search_epochs)
            stage1[(loss, lr)] = run(cfg)
    best = {loss: max((r for (l, _), r in stage1.items() if l == loss), key=lambda r: r["dev_micro"]["f1"])
            for loss in ("ce", "focal")}
    for loss in ("ce", "focal"):    # stage 1b: head lr at the best encoder lr
        for hlr in HEAD_LR_EXTRA:
            rec = run(dict(best[loss]["config"], lr_head=hlr))
            if rec["dev_micro"]["f1"] > best[loss]["dev_micro"]["f1"]:
                best[loss] = rec
    for g in GAMMAS:
        for a in ALPHAS:
            run(dict(best["focal"]["config"], gamma=g, alpha=a))
    runs = list(state["runs"].values())
    state["best"] = {
        "ce": max((r for r in runs if r["config"]["loss"] == "ce"), key=lambda r: r["dev_micro"]["f1"])["config"],
        "focal": max((r for r in runs if r["config"]["loss"] == "focal"), key=lambda r: r["dev_micro"]["f1"])["config"]}
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    log("majority-class baseline row (dev micro-F1):", json.dumps(state.get("baselines")))
    for r in runs:
        if r.get("warning"):
            log("WARNING", json.dumps(r["config"]), r["warning"])
    log("best", json.dumps(state["best"]))


def cmd_final(args):
    out = Path(args.out_dir)
    name = "smoke" if args.smoke else args.loss
    mpath = out / "metrics" / f"ddi_{name}.json"
    if mpath.exists() and not args.force and not args.smoke:
        sys.exit(f"{mpath} exists. The test set is evaluated once per final model; pass --force to redo it.")
    run_dir = out / "metrics" / "ddi_runs" / name
    log = Log(run_dir / "training_log.txt")
    train, dev = load_data(args)
    cfg = base_cfg(args, "focal" if args.smoke and args.loss == "focal" else args.loss)
    if args.from_search and not args.smoke:
        best = json.loads((out / "metrics" / "ddi_search.json").read_text(encoding="utf-8"))["best"][args.loss]
        cfg = dict(best, epochs=args.epochs, patience=args.patience)
    bert, tok, info = make_encoder(args, train, out / "work")
    t0 = time.time()
    model, res = train_run(args, cfg, bert, tok, train, dev, log, gate=not args.smoke)
    train_seconds = time.time() - t0

    import torch
    device = next(model.parameters()).device
    version = f"ddi-{name}-{time.strftime('%Y%m%d')}" + ("-smoke" if args.smoke else "")
    ckpt_cfg = {"version": version, "lstm_hidden": args.lstm_hidden, "head_hidden": args.head_hidden,
                "dropout": args.dropout, "max_len": args.max_len, "loss": cfg["loss"], "gamma": cfg["gamma"],
                "alpha": cfg["alpha"], "alpha_weights": res["alpha_weights"], "smoke_test": args.smoke,
                "tokenizer_vocab_size": len(tok),
                "unk_rate_train": dm.unk_rate(tok, [r["marked_text"] for r in train[:500]]),
                "quality_gate": {"passed": (not args.smoke) and not res["warning"], "min_dev_micro_f1": args.gate_f1,
                                 "epoch": args.gate_epoch, "skipped": args.smoke}, **info}
    dm.save_checkpoint(model, tok, ckpt_cfg, out / "models" / (f"ddi_smoke" if args.smoke else f"ddi_{name}"))

    dev_rows = res["dev"]
    (run_dir).mkdir(parents=True, exist_ok=True)
    with open(run_dir / "dev_predictions.jsonl", "w", encoding="utf-8") as fh:
        for r, p, pr in zip(dev, res["dev_pred"], res["dev_probs"]):
            fh.write(json.dumps({"pair_id": r["pair_id"], "label": r["label"], "pred": p, "probs": pr}) + "\n")
    result = {"smoke_test": args.smoke, "version": version, "seed": args.seed, "config": cfg, "alpha_weights": res["alpha_weights"],
              "best_epoch": res["best_epoch"], "history": res["history"], "dev": dev_rows, "train_seconds": train_seconds,
              "n_train": len(train), "n_dev": len(dev), "selection": "dev micro-F1 (four positive classes)", "baselines": res["baselines"],
              "warning": res["warning"], "quality_gate": ckpt_cfg["quality_gate"],
              "tokenizer_vocab_size": len(tok), **info}

    if not args.smoke:
        test = read_jsonl(Path(args.data_dir) / "test.jsonl")
        tenc = [dm.encode_marked(tok, r["marked_text"], args.max_len) for r in test]
        tm, tpred, tprobs = evaluate(model, tenc, test, tok, device)
        result["test"] = tm
        result["n_test"] = len(test)
        with open(run_dir / "test_predictions.jsonl", "w", encoding="utf-8") as fh:
            for r, p, pr in zip(test, tpred, tprobs):
                fh.write(json.dumps({"pair_id": r["pair_id"], "label": r["label"], "pred": p, "probs": pr}) + "\n")
        log("TEST micro", json.dumps(tm["micro"]))
    if args.faithfulness:
        from medsafe.explain import faithfulness

        rng = random.Random(13)
        by = {}
        for r in read_jsonl(Path(args.data_dir) / "dev.jsonl") if not args.smoke else dev:
            by.setdefault(r["label"], []).append(r)
        n = args.faithfulness
        total = sum(len(v) for v in by.values())
        pick = [r for v in by.values() for r in rng.sample(v, max(1, min(len(v), round(n * len(v) / total))))]
        result["faithfulness"] = faithfulness(model.cpu() if args.smoke else model, tok, [r["marked_text"] for r in pick],
                                              n_steps=args.ig_steps)
        result["faithfulness"]["source"] = "dev instances, stratified by label, seed 13"
        log("faithfulness", json.dumps(result["faithfulness"]))
    result["versions"] = versions()
    (run_dir / "versions.json").write_text(json.dumps(result["versions"], indent=2), encoding="utf-8")
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log(f"done: {mpath}  train_seconds={train_seconds:.1f}  dev_micro_f1={dev_rows['micro']['f1']:.4f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["search", "final"])
    ap.add_argument("--smoke", action="store_true", help="tiny random BERT, 200 train / 50 dev, 1 epoch, no test")
    ap.add_argument("--loss", choices=["ce", "focal"], default="focal")
    ap.add_argument("--gamma", type=float, default=2.0)
    ap.add_argument("--alpha", choices=["none", "inv", "sqrt_inv"], default="inv")
    ap.add_argument("--lr-encoder", type=float, default=3e-5)
    ap.add_argument("--lr-head", type=float, default=5e-4)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--search-epochs", type=int, default=3)
    ap.add_argument("--patience", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=dm.MAX_LEN)
    ap.add_argument("--dropout", type=float, default=0.2)
    ap.add_argument("--lstm-hidden", type=int, default=256)
    ap.add_argument("--head-hidden", type=int, default=256)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--amp", action="store_true")
    ap.add_argument("--limit-train", type=int, default=0)
    ap.add_argument("--limit-dev", type=int, default=0)
    ap.add_argument("--data-dir", default=str(ROOT / "artifacts" / "ddi2013"))
    ap.add_argument("--out-dir", default=str(ROOT / "artifacts"))
    ap.add_argument("--encoder", default=dm.ENCODER_ID)
    ap.add_argument("--encoder-commit", default=dm.ENCODER_COMMIT)
    ap.add_argument("--from-search", action="store_true", help="final: use the best dev config of --loss from ddi_search.json")
    ap.add_argument("--faithfulness", type=int, default=0, help="final: dev instances for the faithfulness proxy")
    ap.add_argument("--ig-steps", type=int, default=50)
    ap.add_argument("--gate-f1", type=float, default=0.3, help="final: stop if dev micro-F1 is below this at --gate-epoch")
    ap.add_argument("--gate-epoch", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        args.limit_train, args.limit_dev, args.epochs, args.search_epochs = args.limit_train or 200, args.limit_dev or 50, 1, 1
        args.out_dir = args.out_dir if "smoke" in args.out_dir else str(Path(args.out_dir) / "smoke")
    {"search": cmd_search, "final": cmd_final}[args.cmd](args)


if __name__ == "__main__":
    main()
