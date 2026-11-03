# SOURCE: NOT IN PAPERS (own tooling). Step-by-step checks of the DDI training path: inputs and labels,
# tokenizer, model, overfit test, mixed precision, optimiser, loss, and a short real run.
"""Run the checks one by one; each prints real output and exits non-zero when its check fails.

  python scripts/diagnose_ddi.py inputs|tokenizer|model|overfit|amp|optim|loss|short [--smoke]
  python scripts/diagnose_ddi.py all            # everything except amp (needs a GPU)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import train_ddi as t  # noqa: E402
from medsafe import ddi_model as dm  # noqa: E402

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


def setup(a):
    d = Path(a.data_dir)
    train, dev = t.read_jsonl(d / "train.jsonl"), t.read_jsonl(d / "dev.jsonl")
    rng = random.Random(a.seed)
    args = types.SimpleNamespace(smoke=a.smoke, encoder=dm.ENCODER_ID, encoder_commit=dm.ENCODER_COMMIT)
    bert, tok, info = t.make_encoder(args, rng.sample(train, 2000) if a.smoke else train[:8], Path(a.work_dir))
    return train, dev, bert, tok, info, rng


def train_args(a, **kw):
    base = dict(seed=a.seed, lstm_hidden=256, head_hidden=256, dropout=0.2, batch_size=8, max_len=dm.MAX_LEN,
                amp=False, smoke=a.smoke, gate_f1=0.3, gate_epoch=2)
    base.update(kw)
    return types.SimpleNamespace(**base)


def stratified(rows, n, rng):
    by = {}
    for r in rows:
        by.setdefault(r["label"], []).append(r)
    out = []
    for v in by.values():
        out += rng.sample(v, max(1, min(len(v), round(n * len(v) / len(rows)))))
    rng.shuffle(out)
    return out


# ---------------------------------------------------------------- 1
def cmd_inputs(a):
    train, _, _, tok, _, rng = setup(a)
    for r in rng.sample(train, 8):
        e = dm.encode_marked(tok, r["marked_text"], dm.MAX_LEN)
        toks = tok.convert_ids_to_tokens(e["ids"])
        b = dm.collate([e], tok.pad_token_id)
        m1, m2 = b["e1_mask"][0].nonzero().flatten().tolist(), b["e2_mask"][0].nonzero().flatten().tolist()
        print("\nraw     :", r["text"])
        print("marked  :", r["marked_text"])
        print("ids     :", e["ids"])
        print("tokens  :", toks)
        print("e1 span :", e["e1"], toks[e["e1"][0]:e["e1"][-1] + 1], "| gold e1_text:", r["e1_text"])
        print("e2 span :", e["e2"], toks[e["e2"][0]:e["e2"][-1] + 1], "| gold e2_text:", r["e2_text"])
        print("e1_mask set at", m1, " e2_mask set at", m2, " label:", r["label"], "->", dm.LABEL_INDEX[r["label"]])
        check("masks non-zero and markers not [UNK]", bool(m1 and m2) and tok.unk_token not in
              [toks[i] for i in (e["e1"] + e["e2"])] or r["e1_text"].lower() == "", r["pair_id"])
        for key, text in (("e1", r["e1_text"]), ("e2", r["e2_text"])):
            got = tok.decode([e["ids"][i] for i in e[key]]).replace(" ", "").replace("##", "").lower()
            check(f"{key} tokens decode to the entity", got == text.replace(" ", "").lower() or e["truncated"], f"{got!r} vs {text!r}")
    # alignment after shuffling and batching
    sub = train[:200]
    encs = [dm.encode_marked(tok, r["marked_text"], dm.MAX_LEN) for r in sub]
    labels = [dm.LABEL_INDEX[r["label"]] for r in sub]
    order = list(range(len(sub)))
    random.Random(1).shuffle(order)
    ok = all(yb.tolist() == [labels[j] for j in idx] and bb["input_ids"][k, :len(encs[j]["ids"])].tolist() == encs[j]["ids"]
             for bb, yb, idx in dm.iter_batches(encs, labels, 8, order, tok.pad_token_id) for k, j in enumerate(idx))
    check("labels and inputs stay aligned after shuffle + batching (200 rows)", ok)
    check("label order is one list", dm.LABELS == ["effect", "mechanism", "advise", "int", "false"] and
          all(dm.LABEL_INDEX[l] == i for i, l in enumerate(dm.LABELS)), str(dm.LABELS))


# ---------------------------------------------------------------- 2
def cmd_tokenizer(a):
    train, _, bert, tok, info, _ = setup(a)
    print("encoder:", info)
    print("len(tokenizer) =", len(tok), "(base vocabulary + 4 markers; the old 'vocab size 9' was 5 specials + 4 markers)")
    ids = tok.convert_tokens_to_ids(dm.MARKER_TOKENS)
    print("marker ids:", dict(zip(dm.MARKER_TOKENS, ids)))
    check("markers are distinct, not [UNK]", len(set(ids)) == 4 and tok.unk_token_id not in ids)
    check("do_lower_case is False (cased)", tok.tokenize("Aspirin")[0] != tok.tokenize("aspirin")[0] or tok.tokenize("Aspirin") != tok.tokenize("aspirin"))
    rows = train[:500]
    rate = dm.unk_rate(tok, [r["marked_text"] for r in rows])
    print(f"[UNK] rate over {len(rows)} train sentences: {rate:.4f}")
    check("[UNK] rate below 2%", rate < 0.02, f"{rate:.4f}")
    check("embedding rows == len(tokenizer)", bert.get_input_embeddings().weight.shape[0] == len(tok),
          str(tuple(bert.get_input_embeddings().weight.shape)))
    if not a.smoke:
        check("real BioBERT vocabulary (28,996 + 4)", len(tok) == 28996 + 4, str(len(tok)))
    from transformers import BertTokenizerFast
    vocab = Path(a.work_dir) / "smoke_vocab" / "vocab.txt"
    if vocab.is_file():
        old = BertTokenizerFast(vocab_file=str(vocab), do_lower_case=False)
        print("old bug (vocab_file=) tokenizer size on the smoke vocabulary:", len(old), "vs fixed", len(tok))


# ---------------------------------------------------------------- 3
def cmd_model(a):
    import torch

    train, _, bert, tok, _, rng = setup(a)
    model_cls, loss_cls = dm.torch_classes()
    model = model_cls(bert)
    rows = rng.sample(train, 16)
    encs = [dm.encode_marked(tok, r["marked_text"], dm.MAX_LEN) for r in rows]
    b = dm.collate(encs, tok.pad_token_id)
    model.eval()
    with torch.no_grad():
        lg = model(**b)
    print("logits (eval) for 16 different sentences:")
    for r, row in zip(rows, lg.tolist()):
        print("  ", r["label"].ljust(9), [round(x, 3) for x in row])
    spread = lg.std(0).mean().item()
    print("mean std of each logit across the 16 inputs:", round(spread, 4))
    check("logits differ between inputs", spread > 1e-3, f"{spread:.5f}")
    check("attention_mask sums equal lengths", b["attention_mask"].sum(1).tolist() == [len(e["ids"]) for e in encs])
    check("all encoder parameters require grad", all(p.requires_grad for p in bert.parameters()))
    # input reaches the head
    ids2 = b["input_ids"].clone()
    ids2[:, 1] = tok.convert_tokens_to_ids("the") if "the" in tok.get_vocab() else ids2[:, 1]
    ids2[b["e1_mask"].bool()] = tok.unk_token_id
    with torch.no_grad():
        lg2 = model(input_ids=ids2, attention_mask=b["attention_mask"], e1_mask=b["e1_mask"], e2_mask=b["e2_mask"])
    check("changing the entity tokens changes the logits", (lg2 - lg).abs().max().item() > 1e-4, f"{(lg2 - lg).abs().max().item():.5f}")
    model.train()
    check("model.train() sets training flags", model.training and model.bert.training and model.drop.training)
    model.eval()
    check("model.eval() clears training flags", not model.training and not model.bert.training)
    model.train()
    y = torch.tensor([dm.LABEL_INDEX[r["label"]] for r in rows])
    loss = loss_cls(2.0, None)(model(**b), y)
    loss.backward()
    groups = {"encoder": [p for n, p in model.named_parameters() if n.startswith("bert.")],
              "lstm": list(model.lstm.parameters()), "head": list(model.head.parameters())}
    for g, ps in groups.items():
        norms = [p.grad.norm().item() for p in ps if p.grad is not None]
        fin = all(math.isfinite(x) for x in norms)
        print(f"  grad norm {g}: params with grad {len(norms)}/{len(ps)}, total {math.sqrt(sum(x * x for x in norms)):.4f}, finite {fin}")
        check(f"{g} gradients non-zero and finite", bool(norms) and fin and sum(norms) > 0)


# ---------------------------------------------------------------- 4
def run_short(a, n_train, epochs, rows_override=None, lr_enc=3e-5, lr_head=5e-4, dropout=0.2, quiet=False):
    train, dev, bert, tok, info, rng = setup(a)
    tr = rows_override if rows_override is not None else stratified(train, n_train, rng)
    dv = stratified(dev, a.n_dev, rng)
    cfg = {"loss": "focal", "gamma": 2.0, "alpha": "inv", "lr_encoder": lr_enc, "lr_head": lr_head, "epochs": epochs, "patience": epochs}
    args = train_args(a, dropout=dropout, amp=a.amp)
    return tr, dv, t.train_run(args, cfg, bert, tok, tr, dv, t.Log(None), gate=False), tok, bert


def cmd_overfit(a):
    import torch

    train, _, bert, tok, _, rng = setup(a)
    rows = rng.sample(train, 64)
    cfg = {"loss": "focal", "gamma": 2.0, "alpha": "inv", "lr_encoder": 3e-5, "lr_head": 1e-3, "epochs": 30, "patience": 30}
    args = train_args(a)
    model, res = t.train_run(args, cfg, bert, tok, rows, rows, t.Log(None))
    h = res["history"]
    print("train loss per epoch:", [round(x["train_loss"], 3) for x in h])
    # accuracy in eval mode on the same 64
    m, pred, _ = t.evaluate(model, [dm.encode_marked(tok, r["marked_text"], dm.MAX_LEN) for r in rows], rows, tok, next(model.parameters()).device)
    acc = sum(p == r["label"] for p, r in zip(pred, rows)) / len(rows)
    print("train accuracy (eval mode):", round(acc, 4), " classes predicted:", sorted(set(pred)))
    check("loss falls near zero", h[-1]["train_loss"] < 0.1, f"{h[-1]['train_loss']:.4f}")
    check("train accuracy about 100%", acc >= 0.95, f"{acc:.3f}")


# ---------------------------------------------------------------- 5
def cmd_amp(a):
    import torch

    if not torch.cuda.is_available():
        print("SKIPPED: no CUDA device. Mixed precision is off on CPU (train_run sets amp only for cuda), so fp32 vs --amp cannot be compared here.")
        print("Static facts: autocast wraps only the forward pass; FocalLoss casts logits.float(); scaler.unscale_ precedes clip_grad_norm_; masks and alpha are fp32.")
        return
    out = {}
    for amp in (False, True):
        a.amp = amp
        _, _, (model, res), _, _ = run_short(a, a.n_train, 1)
        out[amp] = res
        print("amp" if amp else "fp32", "loss", res["history"][-1]["train_loss"], "dev micro-F1", res["dev"]["micro"]["f1"], "warning", res["warning"])
    check("fp32 and amp train losses within 25%", abs(out[True]["history"][-1]["train_loss"] - out[False]["history"][-1]["train_loss"]) < 0.25 * out[False]["history"][-1]["train_loss"])
    check("amp run does not collapse to one class", out[True]["warning"] is None)


# ---------------------------------------------------------------- 6
def cmd_optim(a):
    import torch
    from transformers import get_linear_schedule_with_warmup

    train, _, bert, tok, _, rng = setup(a)
    model_cls, loss_cls = dm.torch_classes()
    model = model_cls(bert)
    opt = torch.optim.AdamW(t.param_groups(model, 3e-5, 5e-4))
    seen = set()
    for g in opt.param_groups:
        n = sum(p.numel() for p in g["params"])
        print(f"  group: {len(g['params'])} tensors, {n} params, lr {g['lr']}, weight_decay {g['weight_decay']}")
        seen |= {id(p) for p in g["params"]}
    check("every parameter in exactly one group", seen == {id(p) for p in model.parameters()} and
          sum(len(g["params"]) for g in opt.param_groups) == len(list(model.parameters())))
    enc_ids = {id(p) for n, p in model.named_parameters() if n.startswith("bert.")}
    check("encoder lr only on encoder params, head lr only on head", all(
        (g["lr"] == 3e-5) == all(id(p) in enc_ids for p in g["params"]) for g in opt.param_groups))
    steps = 1000
    sched = get_linear_schedule_with_warmup(opt, 100, steps)
    lrs = {}
    for s in range(steps + 1):
        if s in (0, 1, 50, 100, 500, 999):
            lrs[s] = [round(g["lr"], 9) for g in opt.param_groups]
        opt.step()
        sched.step()
    print("lr at steps 0, 1, 50, 100, 500, 999 (per group):")
    for s, v in lrs.items():
        print("  ", s, v)
    check("lr non-zero after step 0 and peaks at warm-up end", max(lrs[1]) > 0 and lrs[100][0] >= lrs[50][0] and lrs[500][0] < lrs[100][0])
    rows = rng.sample(train, 16)
    encs = [dm.encode_marked(tok, r["marked_text"], dm.MAX_LEN) for r in rows]
    b = dm.collate(encs, tok.pad_token_id)
    y = torch.tensor([dm.LABEL_INDEX[r["label"]] for r in rows])
    model.train()
    loss_cls(2.0, None)(model(**b), y).backward()
    gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0).item()
    print(f"global grad norm before clipping: {gn:.4f} (clip at 1.0 scales every gradient by {min(1.0, 1.0 / gn):.4f})")
    check("clipping does not shrink gradients to ~0 (scale > 0.01)", min(1.0, 1.0 / gn) > 0.01)


# ---------------------------------------------------------------- 7
def cmd_loss(a):
    import torch

    _, focal = dm.torch_classes()
    logits = torch.zeros(5, 5)
    y = torch.tensor([0, 1, 2, 3, 4])
    alpha = [1.0, 2.0, 3.0, 4.0, 5.0]
    got = focal(2.0, alpha)(logits, y).item()
    hand = sum(al * 0.8 ** 2 * math.log(5) for al in alpha) / 5
    print(f"uniform logits, gamma 2, alpha {alpha}: got {got:.6f}, hand FL = mean(alpha_t * 0.8^2 * ln 5) = {hand:.6f}")
    check("focal matches the formula on a hand-made batch", abs(got - hand) < 1e-6)
    lg = torch.tensor([[3.0, 0, 0, 0, 0], [0, 0, 0, 0, 3.0]])
    for gam in (0.0, 2.0):
        one = focal(gam, alpha)(lg, torch.tensor([0, 4])).item()
        p = math.exp(3) / (math.exp(3) + 4)
        want = (alpha[0] + alpha[4]) / 2 * (1 - p) ** gam * -math.log(p)
        check(f"gamma {gam}: alpha_t picks the target class by label index", abs(one - want) < 1e-6, f"{one:.6f} vs {want:.6f}")
    ce = torch.nn.functional.cross_entropy(lg, torch.tensor([0, 4])).item()
    check("gamma 0 without alpha is cross-entropy", abs(focal(0.0, None)(lg, torch.tensor([0, 4])).item() - ce) < 1e-6)
    counts = {"effect": 100, "mechanism": 50, "advise": 25, "int": 10, "false": 800}
    w = dm.alpha_weights(counts, "inv")
    print("alpha 'inv' for", counts, "->", [round(x, 3) for x in w])
    check("alpha follows LABELS order (rarest class gets the largest weight)", w.index(max(w)) == dm.LABEL_INDEX["int"] and w.index(min(w)) == dm.LABEL_INDEX["false"])


# ---------------------------------------------------------------- 8
def cmd_short(a):
    tr, dv, (model, res), tok, _ = run_short(a, a.n_train, 1)
    m = res["dev"]
    print(f"\nshort run: {len(tr)} train sentences, 1 epoch, {len(dv)} dev sentences, smoke={a.smoke}")
    print("train loss:", [round(h["train_loss"], 4) for h in res["history"]])
    print("class".ljust(10), "P".rjust(7), "R".rjust(7), "F1".rjust(7), "support".rjust(8))
    for l in dm.LABELS:
        c = m["per_class"][l]
        print(l.ljust(10), f"{c['precision']:7.3f} {c['recall']:7.3f} {c['f1']:7.3f} {c['support']:8d}")
    print("micro (4 positive classes): P %.3f R %.3f F1 %.3f" % (m["micro"]["precision"], m["micro"]["recall"], m["micro"]["f1"]))
    print("confusion matrix (rows gold, columns predicted):", dm.LABELS)
    for l, row in zip(dm.LABELS, m["confusion_matrix"]):
        print("  ", l.ljust(10), row)
    print("baselines:", json.dumps(res["baselines"]))
    used = sorted(set(res["dev_pred"]))
    print("classes predicted:", used)
    check("predicts all five classes", len(used) == 5, str(used))
    for name, b in res["baselines"].items():
        check(f"micro-F1 beats {name} baseline ({b['label']})", m["micro"]["f1"] > b["micro_f1"], f"{m['micro']['f1']:.3f} vs {b['micro_f1']:.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["inputs", "tokenizer", "model", "overfit", "amp", "optim", "loss", "short", "all"])
    ap.add_argument("--smoke", action="store_true", help="tiny random BERT instead of BioBERT")
    ap.add_argument("--data-dir", default=str(ROOT / "artifacts" / "ddi2013"))
    ap.add_argument("--work-dir", default=str(ROOT / "artifacts" / "work"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-train", type=int, default=3000)
    ap.add_argument("--n-dev", type=int, default=500)
    ap.add_argument("--amp", action="store_true")
    a = ap.parse_args()
    cmds = {"inputs": cmd_inputs, "tokenizer": cmd_tokenizer, "model": cmd_model, "overfit": cmd_overfit, "amp": cmd_amp,
            "optim": cmd_optim, "loss": cmd_loss, "short": cmd_short}
    todo = [c for c in cmds if c != "amp"] if a.cmd == "all" else [a.cmd]
    for c in todo:
        print(f"\n===== {c} =====")
        t0 = time.time()
        cmds[c](a)
        print(f"({time.time() - t0:.0f}s)")
    print("\nFAILED:" if FAILS else "\nall checks passed", FAILS or "")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
