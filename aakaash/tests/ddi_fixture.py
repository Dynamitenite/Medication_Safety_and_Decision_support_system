# SOURCE: NOT IN PAPERS. FIXTURES ONLY: a tiny randomly initialised BERT with a hand-written vocabulary,
# saved as a checkpoint in a temp folder. It proves plumbing, never model quality.
from pathlib import Path

VOCAB = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "a", "b", "may", "raise", "the", "level", "of", "with",
         "taken", "together", "increases", "effect", ".", "-", "and", "warfarin", "aspirin", "acetaminophen",
         "bleeding", "risk", "avoid", "use", "do", "not", "w", "##arf", "##arin"]


def make_checkpoint(folder: Path, smoke: bool = True) -> Path:
    import torch
    from transformers import BertConfig, BertModel

    from medsafe import ddi_model as dm

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "vocab_src.txt").write_text("\n".join(VOCAB), encoding="utf-8")
    tok = dm.build_tokenizer(folder / "vocab_src.txt")
    torch.manual_seed(0)
    bert = BertModel(BertConfig(vocab_size=len(tok), hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                                intermediate_size=32, max_position_embeddings=64), add_pooling_layer=False)
    model_cls, _ = dm.torch_classes()
    model = model_cls(bert, 8, 8, 0.2).eval()
    out = folder / "ckpt"
    dm.save_checkpoint(model, tok, {"version": "fixture-tiny", "lstm_hidden": 8, "head_hidden": 8, "dropout": 0.2,
                                    "max_len": 64, "loss": "focal", "gamma": 2.0, "alpha": "inv",
                                    "smoke_test": smoke, "encoder": "tiny random BERT (fixture)"}, out)
    return out


def metrics_json(name: str = "focal", smoke: bool = True) -> dict:
    labels = ["effect", "mechanism", "advise", "int", "false"]
    split = {"n": 10, "labels": labels,
             "micro": {"precision": 0.5, "recall": 0.25, "f1": 1 / 3},
             "per_class": {l: {"precision": 0.1, "recall": 0.2, "f1": 0.13, "support": i + 1} for i, l in enumerate(labels)},
             "confusion_matrix": [[1 if i == j else 0 for j in range(5)] for i in range(5)]}
    return {"smoke_test": smoke, "version": f"fixture-{name}", "seed": 42, "best_epoch": 2, "encoder": "fixture",
            "config": {"loss": name if name in ("ce", "focal") else "focal", "gamma": 2.0, "alpha": "inv",
                       "lr_encoder": 3e-5, "lr_head": 5e-4, "epochs": 3, "patience": 3},
            "n_train": 20, "n_dev": 10, "n_test": 10, "dev": split, "test": split,
            "faithfulness": {"label": "a faithfulness proxy", "seed": 13, "random_draws": 5, "n_steps": 10,
                             "n_sentences": 4, "source": "fixture",
                             "by_k": {"1": {"n": 4, "skipped": 0, "mean_drop_top_k": 0.1, "mean_drop_random_k": 0.0}}}}
