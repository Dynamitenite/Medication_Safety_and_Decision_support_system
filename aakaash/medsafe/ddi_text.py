# SOURCE: NOT IN PAPERS. Own preprocessing: marks two drug names in a label sentence with the same
# entity markers that medsafe/ddi2013.py writes for the training data (<e1></e1> <e2></e2>).
# The nearest-pair rule is our own choice. No torch import here.
"""Entity marking for app sentences."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .ddi2013 import DEFAULT_MARKERS, mark_pair
from .names import norm, term_regex


@dataclass(frozen=True)
class MarkedPair:
    text: str                      # the original sentence
    marked_text: str               # with <e1>..</e1> and <e2>..</e2>
    span1: tuple[int, int]         # character span of e1 in `text` (the earlier mention)
    span2: tuple[int, int]
    mentions1: int                 # how many times drug_1's name occurs in the sentence
    mentions2: int


def find_spans(text: str, name: str) -> list[tuple[int, int]]:
    """Every whole-word, case-insensitive occurrence of `name` (whitespace may vary)."""
    rx = term_regex([norm(name)]) if norm(name) else None
    return [m.span() for m in rx.finditer(text)] if rx else []


def choose_pair(spans1, spans2):
    """The non-overlapping (a, b) with the smallest gap between them; ties go to the earliest.
    Returns (span_of_drug_1, span_of_drug_2) or None."""
    best, best_key = None, None
    for a in spans1:
        for b in spans2:
            if a[0] < b[1] and b[0] < a[1]:
                continue  # overlap
            gap = max(a[0], b[0]) - min(a[1], b[1])
            key = (gap, min(a[0], b[0]))
            if best_key is None or key < best_key:
                best, best_key = (a, b), key
    return best


def mark_sentence(sentence: str, drug_1: str, drug_2: str) -> MarkedPair | None:
    """None when a drug is not in the sentence, the two names are the same, or every pair overlaps.
    e1 is the earlier of the two mentions, as in DDI 2013."""
    if not sentence or norm(drug_1) == norm(drug_2):
        return None
    s1, s2 = find_spans(sentence, drug_1), find_spans(sentence, drug_2)
    pick = choose_pair(s1, s2)
    if pick is None:
        return None
    first, second = sorted(pick)
    return MarkedPair(sentence, mark_pair(sentence, first, second, DEFAULT_MARKERS), first, second,
                      len(s1), len(s2))


_MARK_RX = re.compile(r"</?e[12]>")


def strip_markers(marked: str) -> str:
    return _MARK_RX.sub("", marked)


def find_source_term(sentence: str, matched_term: str, terms: list[str]) -> str | None:
    """The text in `sentence` that names the label's own drug (one of `terms`) and does not overlap
    `matched_term`; the one closest to a `matched_term` mention. None when the sentence never names it
    (labels often say "this drug"), in which case the sentence cannot be marked."""
    others = find_spans(sentence, matched_term)
    best, best_gap = None, None
    for term in terms:
        for a in find_spans(sentence, term):
            for o in others:
                if a[0] < o[1] and o[0] < a[1]:
                    continue
                gap = max(a[0], o[0]) - min(a[1], o[1])
                if best_gap is None or gap < best_gap:
                    best, best_gap = sentence[a[0]:a[1]], gap
    return best
