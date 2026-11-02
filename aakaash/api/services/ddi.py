# SOURCE: NOT IN PAPERS. Serves the Focal Loss interaction-type classifier (medsafe/ddi_model.py) and
# its measured metrics. A model estimate only: nothing here is read by the risk-level code
# (medsafe/risk.py, services/intake.py). The model loads on the first request and stays in memory.
"""POST /api/ddi/classify and GET /api/ddi/metrics."""
from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from pathlib import Path

from medsafe import ddi_model as dm
from medsafe.ddi_text import mark_sentence

from ..config import Settings
from ..schemas import (DDIClassifyRequest, DDIClassifyResponse, DDIClassRow, DDIFaithfulness, DDIFaithK, DDIIgInfo,
                       DDIMetricsResponse, DDIModelInfo, DDIPRF, DDIRun, DDISearchRow, DDISplitMetrics, DDIWord)

FIX = "Train on Colab and place the checkpoint in artifacts/models"
CACHE_SIZE = 512

_lock = threading.Lock()
_loaded: dict = {}      # {"dir", "stamp", "model", "tok", "cfg", "load_ms"}
_cache: OrderedDict = OrderedDict()


def clear_cache() -> None:
    with _lock:
        _loaded.clear()
        _cache.clear()


def model_state(s: Settings) -> dict:
    """Readiness from the files only (no torch import): {"ready": bool, "reason", "cfg"}."""
    d = s.ddi_model_dir
    if not dm.checkpoint_present(d):
        return {"ready": False, "cfg": None,
                "reason": f"No checkpoint in {s.display(d)} (model.safetensors and config.json)."}
    return {"ready": True, "cfg": dm.read_config(d), "reason": None}


def _info(cfg: dict) -> DDIModelInfo:
    return DDIModelInfo(version=cfg.get("version", "unknown"), loss=cfg.get("loss", "focal"),
                        gamma=float(cfg.get("gamma", 0.0)), alpha=str(cfg.get("alpha", "none")),
                        encoder=str(cfg.get("encoder", "unknown")), smoke_test=bool(cfg.get("smoke_test", False)))


def _get_model(s: Settings):
    """Load once per checkpoint file (reloaded if the file changes). Caller holds the lock."""
    d = s.ddi_model_dir
    stamp = (d / dm.MODEL_FILE).stat().st_mtime
    if _loaded.get("dir") != str(d) or _loaded.get("stamp") != stamp:
        t = time.perf_counter()
        model, tok, cfg = dm.load_checkpoint(d)
        _loaded.clear()
        _loaded.update(dir=str(d), stamp=stamp, model=model, tok=tok, cfg=cfg,
                       load_ms=(time.perf_counter() - t) * 1000)
        _cache.clear()
    return _loaded


def classify(s: Settings, req: DDIClassifyRequest) -> DDIClassifyResponse:
    st = model_state(s)
    if not st["ready"]:
        return DDIClassifyResponse(status="not_ready", reason=st["reason"], fix=FIX)
    pair = mark_sentence(req.sentence, req.drug_1, req.drug_2)
    if pair is None:
        return DDIClassifyResponse(status="not_markable", reason="The sentence does not name both drugs as separate "
                                   "mentions, so the model input cannot be made.")
    key = (str(s.ddi_model_dir), pair.marked_text, req.explain)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        was_loaded = _loaded.get("dir") == str(s.ddi_model_dir)
        m = _get_model(s)
        timing = {"load": 0.0 if was_loaded else m["load_ms"]}
        info = _info(m["cfg"])
        max_len = int(m["cfg"].get("max_len", dm.MAX_LEN))
        if req.explain:
            from medsafe.explain import explain

            t = time.perf_counter()
            ex = explain(m["model"], m["tok"], pair.marked_text, max_len)
            timing["explain"] = (time.perf_counter() - t) * 1000
            probs = ex["probabilities"]
            words = [DDIWord(**w) for w in ex["words"]]
            ig = DDIIgInfo(n_steps=ex["n_steps"], delta=ex["delta"])
        else:
            t = time.perf_counter()
            probs = dm.predict_proba(m["model"], m["tok"], [pair.marked_text], max_len)[0]
            timing["classify"] = (time.perf_counter() - t) * 1000
            words, ig = None, None
        best = max(range(len(probs)), key=probs.__getitem__)
        out = DDIClassifyResponse(
            status="ready", predicted=dm.LABELS[best], probability=probs[best],
            probabilities={l: p for l, p in zip(dm.LABELS, probs)}, marked_text=pair.marked_text,
            words=words, ig=ig, model=info, timing_ms={k: round(v, 1) for k, v in timing.items()})
        _cache[key] = out
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
        return out


# ---------------------------------------------------------------- metrics

def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _split(m: dict) -> DDISplitMetrics:
    return DDISplitMetrics(
        n=m["n"], micro=DDIPRF(**{k: m["micro"][k] for k in ("precision", "recall", "f1")}),
        per_class=[DDIClassRow(label=l, support=m["per_class"][l]["support"],
                               **{k: m["per_class"][l][k] for k in ("precision", "recall", "f1")}) for l in m["labels"]],
        labels=m["labels"], confusion_matrix=m["confusion_matrix"])


def _run(name: str, j: dict) -> DDIRun:
    c = j["config"]
    f = j.get("faithfulness")
    faith = None
    if f:
        faith = DDIFaithfulness(
            label=f["label"], source=f.get("source", ""), seed=f["seed"], random_draws=f["random_draws"],
            n_steps=f["n_steps"], n_sentences=f["n_sentences"],
            by_k=[DDIFaithK(k=int(k), n=v["n"], skipped=v["skipped"], mean_drop_top_k=v["mean_drop_top_k"],
                            mean_drop_random_k=v["mean_drop_random_k"])
                  for k, v in sorted(f["by_k"].items(), key=lambda x: int(x[0]))])
    return DDIRun(name=name, version=j["version"], smoke_test=bool(j.get("smoke_test")), loss=c["loss"],
                  gamma=c["gamma"], alpha=c["alpha"], lr_encoder=c["lr_encoder"], lr_head=c["lr_head"],
                  best_epoch=j["best_epoch"], seed=j["seed"], encoder=str(j.get("encoder", "unknown")),
                  n_train=j["n_train"], n_dev=j["n_dev"], n_test=j.get("n_test"), dev=_split(j["dev"]),
                  test=_split(j["test"]) if j.get("test") else None, faithfulness=faith)


def metrics(s: Settings) -> DDIMetricsResponse:
    d = s.ddi_metrics_dir
    runs, problems = [], []
    for p in sorted(d.glob("ddi_*.json")) if d.is_dir() else []:
        if p.name == "ddi_search.json":
            continue
        try:
            runs.append(_run(p.stem.removeprefix("ddi_"), _read(p)))
        except (TypeError, KeyError, ValueError):
            problems.append(p.name)
    if not runs:
        reason = (f"No metrics files in {s.display(d)} (ddi_ce.json, ddi_focal.json)."
                  if not problems else f"Metrics files could not be read: {', '.join(problems)}.")
        return DDIMetricsResponse(status="not_ready", reason=reason,
                                  fix="Train on Colab and place the metrics JSON in artifacts/metrics")
    search, smoke = [], False
    sj = _read(d / "ddi_search.json")
    if sj:
        smoke = bool(sj.get("smoke_test"))
        for r in sj.get("runs", {}).values():
            c = r["config"]
            search.append(DDISearchRow(loss=c["loss"], gamma=c["gamma"], alpha=c["alpha"], lr_encoder=c["lr_encoder"],
                                       lr_head=c["lr_head"], best_epoch=r["best_epoch"], dev_micro_f1=r["dev_micro"]["f1"]))
    order = {"ce": 0, "focal": 1}
    runs.sort(key=lambda r: order.get(r.name, 2))
    return DDIMetricsResponse(status="ready", runs=runs, search=search, search_smoke_test=smoke)
