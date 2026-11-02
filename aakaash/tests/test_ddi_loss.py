# SOURCE: NOT IN PAPERS. FIXTURES ONLY: tiny hand-written tensors and label lists.
import math

import pytest

from medsafe import ddi_model as dm

torch = pytest.importorskip("torch")

LOGITS = [[2.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
TARGET = [0, 1]


def log_softmax_at(row, t):
    return row[t] - math.log(sum(math.exp(x) for x in row))


def test_focal_matches_hand_computation():
    gamma, alpha = 2.0, [0.5, 2.0, 1.0]
    terms = []
    for row, t in zip(LOGITS, TARGET):
        lp = log_softmax_at(row, t)
        terms.append(-alpha[t] * (1 - math.exp(lp)) ** gamma * lp)
    hand = sum(terms) / 2
    _, focal = dm.torch_classes()
    got = focal(gamma, alpha)(torch.tensor(LOGITS), torch.tensor(TARGET))
    assert got.item() == pytest.approx(hand, rel=1e-6)


def test_gamma_zero_is_weighted_cross_entropy_mean_over_n():
    alpha = [0.5, 2.0, 1.0]
    hand = sum(-alpha[t] * log_softmax_at(r, t) for r, t in zip(LOGITS, TARGET)) / 2
    _, focal = dm.torch_classes()
    got = focal(0.0, alpha)(torch.tensor(LOGITS), torch.tensor(TARGET))
    assert got.item() == pytest.approx(hand, rel=1e-6)


def test_gamma_zero_without_alpha_is_plain_cross_entropy():
    ce = torch.nn.functional.cross_entropy(torch.tensor(LOGITS), torch.tensor(TARGET))
    ignored = dm.make_loss("ce", 5.0, [9, 9, 9, 9, 9])  # CE ignores gamma and alpha
    assert ignored(torch.tensor(LOGITS), torch.tensor(TARGET)).item() == pytest.approx(ce.item())
    _, focal = dm.torch_classes()
    assert focal(0.0, None)(torch.tensor(LOGITS), torch.tensor(TARGET)).item() == pytest.approx(ce.item())


def test_focal_down_weights_easy_examples_and_has_finite_gradient():
    _, focal = dm.torch_classes()
    easy = torch.tensor([[10.0, 0.0, 0.0]], requires_grad=True)
    loss = focal(2.0, None)(easy, torch.tensor([0]))
    loss.backward()
    ce = torch.nn.functional.cross_entropy(easy.detach(), torch.tensor([0]))
    assert loss.item() < ce.item() * 1e-3
    assert torch.isfinite(easy.grad).all()


def test_alpha_weights_by_hand():
    counts = {"effect": 100, "mechanism": 100, "advise": 100, "int": 100, "false": 400}
    w = dm.alpha_weights(counts, "inv")        # N/(K n_c): 800/500 = 1.6 and 800/2000 = 0.4; mean (4*1.6+0.4)/5 = 1.36
    assert w[0] == pytest.approx(1.6 / 1.36) and w[4] == pytest.approx(0.4 / 1.36)
    assert sum(w) / 5 == pytest.approx(1.0)
    assert dm.alpha_weights(counts, "none") == [1.0] * 5
    s = dm.alpha_weights({"effect": 4, "mechanism": 4, "advise": 4, "int": 4, "false": 16}, "sqrt_inv")
    assert s[0] / s[4] == pytest.approx(2.0)   # 1/sqrt(4) : 1/sqrt(16)
    with pytest.raises(ValueError):
        dm.alpha_weights(counts, "bogus")


def test_metrics_micro_ignores_false_and_confusion_matrix():
    gold = ["effect", "effect", "mechanism", "false", "false", "int"]
    pred = ["effect", "false", "mechanism", "effect", "false", "advise"]
    m = dm.metrics(gold, pred)
    # positives: tp=2 (effect, mechanism); fp=2 (false->effect, int->advise); fn=2 (effect->false, int->advise)
    assert (m["micro"]["tp"], m["micro"]["fp"], m["micro"]["fn"]) == (2, 2, 2)
    assert m["micro"]["precision"] == pytest.approx(0.5) and m["micro"]["f1"] == pytest.approx(0.5)
    assert m["per_class"]["effect"]["support"] == 2 and m["per_class"]["false"]["tp"] == 1
    cm = m["confusion_matrix"]
    assert cm[dm.LABEL_INDEX["effect"]][dm.LABEL_INDEX["false"]] == 1 and sum(map(sum, cm)) == 6
