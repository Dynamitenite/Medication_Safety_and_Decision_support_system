# SOURCE: NOT IN PAPERS. FIXTURES ONLY: a hand-written vocabulary and hand-made batches. These tests guard the
# training path (tokenizer, label alignment, masks, constant output, loss, gate); they say nothing about quality.
import random
import sys
from pathlib import Path

import pytest

from medsafe import ddi_model as dm
from ddi_fixture import VOCAB

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture(scope="module")
def tok(tmp_path_factory):
    f = tmp_path_factory.mktemp("vocab") / "vocab.txt"
    f.write_text("\n".join(VOCAB), encoding="utf-8")
    return dm.build_tokenizer(f)


def test_tokenizer_loads_vocabulary_and_markers(tok):
    assert len(tok) == len(VOCAB) + 4          # the old bug gave 9 whatever the file held
    ids = tok.convert_tokens_to_ids(dm.MARKER_TOKENS)
    assert len(set(ids)) == 4 and tok.unk_token_id not in ids
    assert tok.unk_token_id not in tok("aspirin may raise the level of warfarin .", add_special_tokens=False)["input_ids"]
    assert dm.unk_rate(tok, ["aspirin may raise the level of warfarin ."]) == 0.0


def test_tokenizer_size_guard(tmp_path):
    f = tmp_path / "vocab.txt"
    f.write_text("\n".join(VOCAB), encoding="utf-8")
    assert len(dm.build_tokenizer(f)) == len(VOCAB) + 4
    f.write_text("", encoding="utf-8")
    with pytest.raises(Exception):             # empty vocabulary must not pass silently
        dm.build_tokenizer(f)


def _enc(tok, text):
    return dm.encode_marked(tok, text, 64)


def test_label_and_input_alignment_after_shuffled_batching(tok):
    # The label is recoverable from the input: a sentence names one of the five class words.
    words = {"increases": "effect", "raise": "mechanism", "avoid": "advise", "together": "int", "bleeding": "false"}
    rng = random.Random(0)
    texts, labels = [], []
    for _ in range(40):
        w = rng.choice(list(words))
        texts.append(f"<e1>warfarin</e1> {w} with <e2>aspirin</e2> .")
        labels.append(dm.LABEL_INDEX[words[w]])
    encs = [_enc(tok, t) for t in texts]
    order = list(range(40))
    rng.shuffle(order)
    seen = []
    for batch, y, idx in dm.iter_batches(encs, labels, 7, order, tok.pad_token_id):
        for k, j in enumerate(idx):
            word_id = next(i for i in batch["input_ids"][k].tolist() if i in {tok.convert_tokens_to_ids(w) for w in words})
            assert dm.LABELS[y[k]] == words[tok.convert_ids_to_tokens(word_id)]
            assert batch["input_ids"][k, :len(encs[j]["ids"])].tolist() == encs[j]["ids"]
            seen.append(j)
    assert sorted(seen) == list(range(40))     # every sentence exactly once


def test_masks_cover_exactly_the_entity_pieces(tok):
    e = _enc(tok, "<e1>warfarin aspirin</e1> may raise the level of <e2>acetaminophen</e2> .")
    toks = tok.convert_ids_to_tokens(e["ids"])
    assert [toks[i] for i in e["e1"]] == ["warfarin", "aspirin"]
    assert [toks[i] for i in e["e2"]] == ["acetaminophen"]
    b = dm.collate([e], tok.pad_token_id)
    assert b["e1_mask"].sum().item() == 2 and b["e2_mask"].sum().item() == 1
    assert (b["e1_mask"] * b["e2_mask"]).sum().item() == 0                       # disjoint
    assert (b["e1_mask"] * (1 - b["attention_mask"])).sum().item() == 0          # never on padding


def test_masks_non_zero_for_every_row_in_a_padded_batch(tok):
    encs = [_enc(tok, "<e1>aspirin</e1> and <e2>warfarin</e2> ."),
            _enc(tok, "<e1>aspirin</e1> may raise the level of bleeding risk with <e2>warfarin</e2> taken together .")]
    b = dm.collate(encs, tok.pad_token_id)
    assert (b["e1_mask"].sum(1) > 0).all() and (b["e2_mask"].sum(1) > 0).all()
    assert b["attention_mask"].sum(1).tolist() == [len(e["ids"]) for e in encs]


def test_masks_survive_truncation_when_entities_fit(tok):
    text = "<e1>aspirin</e1> " + "and " * 80 + "<e2>warfarin</e2> ."
    e = dm.encode_marked(tok, text, 32)
    assert e["truncated"] and len(e["ids"]) <= 32
    toks = tok.convert_ids_to_tokens(e["ids"])
    assert "<e1>" in toks or e["e1"] == [0]    # span fell back to [CLS] only when the marker was cut


def test_constant_output_detection():
    assert dm.constant_output_warning(["false"] * 10) == "predicts only one class: false"
    assert dm.constant_output_warning(["false", "effect"]) is None
    assert dm.constant_output_warning([]) is None
    gold = ["false"] * 7 + ["effect"] * 2 + ["advise"]
    b = dm.baselines(gold)
    assert b["majority"]["label"] == "false" and b["majority"]["micro_f1"] == 0.0
    assert b["most_frequent_positive"]["label"] == "effect"
    # predicting `effect` everywhere: tp 2, fp 8, fn 1 over the positives -> P 0.2, R 2/3
    p, r = 0.2, 2 / 3
    assert b["most_frequent_positive"]["micro_f1"] == pytest.approx(2 * p * r / (p + r))


def test_focal_on_hand_made_five_class_batch():
    import math

    _, focal = dm.torch_classes()
    alpha = [1.0, 2.0, 3.0, 4.0, 5.0]
    got = focal(2.0, alpha)(torch.zeros(5, 5), torch.arange(5)).item()
    assert got == pytest.approx(sum(a * 0.8 ** 2 * math.log(5) for a in alpha) / 5, rel=1e-6)
    # alpha_t follows the label index: only class 3 is the target, alpha 4.0
    one = focal(0.0, alpha)(torch.zeros(1, 5), torch.tensor([3])).item()
    assert one == pytest.approx(4.0 * math.log(5), rel=1e-6)


def test_param_groups_cover_each_parameter_once_and_split_lr(tok):
    from transformers import BertConfig, BertModel

    import train_ddi as tr

    bert = BertModel(BertConfig(vocab_size=len(tok), hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                                intermediate_size=32, max_position_embeddings=64), add_pooling_layer=False)
    model = dm.torch_classes()[0](bert, 8, 8, 0.2)
    groups = tr.param_groups(model, 3e-5, 5e-4)
    ids = [id(p) for g in groups for p in g["params"]]
    assert len(ids) == len(set(ids)) == len(list(model.parameters()))
    enc = {id(p) for n, p in model.named_parameters() if n.startswith("bert.")}
    for g in groups:
        is_enc = all(id(p) in enc for p in g["params"])
        assert is_enc or not any(id(p) in enc for p in g["params"])
        assert g["lr"] == (3e-5 if is_enc else 5e-4)
    assert any(g["weight_decay"] == 0.0 for g in groups)


def test_lr_ranges_are_enforced():
    import train_ddi as tr

    tr.check_lr_ranges({"lr_encoder": 3e-5, "lr_head": 5e-4})
    with pytest.raises(ValueError):
        tr.check_lr_ranges({"lr_encoder": 5e-4, "lr_head": 5e-4})
    with pytest.raises(ValueError):
        tr.check_lr_ranges({"lr_encoder": 3e-5, "lr_head": 1e-2})


def test_quality_gate_stops_a_collapsed_run(tok, tmp_path):
    import types

    import train_ddi as tr
    from transformers import BertConfig, BertModel

    rows = [{"marked_text": "<e1>aspirin</e1> and <e2>warfarin</e2> .", "label": "false", "pair_id": str(i)} for i in range(16)]
    bert = BertModel(BertConfig(vocab_size=len(tok), hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
                                intermediate_size=32, max_position_embeddings=64), add_pooling_layer=False)
    args = types.SimpleNamespace(seed=1, lstm_hidden=8, head_hidden=8, dropout=0.2, batch_size=8, max_len=64, amp=False,
                                 gate_f1=0.3, gate_epoch=1)
    cfg = {"loss": "ce", "gamma": 0.0, "alpha": "none", "lr_encoder": 3e-5, "lr_head": 5e-4, "epochs": 2, "patience": 2}
    with pytest.raises(SystemExit) as e:
        tr.train_run(args, cfg, bert, tok, rows, rows, tr.Log(None), gate=True)
    assert "QUALITY GATE FAILED" in str(e.value)
