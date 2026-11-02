# SOURCE: NOT IN PAPERS. Own design: match APPMS drug names to DailyMed labels by active ingredient.
"""Pure logic. A drug name matches a label when its normalised name equals one of the label's
active ingredient or active moiety names, ignoring a trailing salt, hydrate or form word
("enalapril" matches "ENALAPRIL MALEATE"). Nothing else: no synonym table, no fuzzy matching, so
"Salbutamol" does not match "ALBUTEROL" (a name difference, not a guess we make)."""
from __future__ import annotations

from collections import defaultdict

from .names import norm

FORM_WORDS = frozenset("""
anhydrous hydrate monohydrate dihydrate trihydrate hemihydrate sesquihydrate
sodium potassium calcium magnesium
hydrochloride hydrobromide sulfate bisulfate phosphate nitrate acetate citrate tartrate succinate
maleate fumarate mesylate besylate bromide chloride hcl
""".split())


def ingredient_keys(*names: str) -> set[str]:
    """Normalised names plus the same names with trailing form words removed."""
    out: set[str] = set()
    for raw in names:
        words = norm(raw).split()
        if not words:
            continue
        out.add(" ".join(words))
        while len(words) > 1 and words[-1] in FORM_WORDS:
            words = words[:-1]
            out.add(" ".join(words))
    return out


def label_keys(label: dict) -> set[str]:
    """Keys of a name-index record or a parse_label record."""
    ing = label.get("ingredients", label.get("ingredients_raw", []))
    moi = label.get("moieties", label.get("active_moieties", []))
    return ingredient_keys(*ing, *moi, *label.get("moieties_raw", label.get("active_moieties_raw", [])))


class IngredientMatcher:
    def __init__(self, labels: list[dict]):
        self.labels = labels
        by_key: dict[str, list[int]] = defaultdict(list)
        for i, l in enumerate(labels):
            for k in label_keys(l):
                by_key[k].append(i)
        self._by_key = by_key

    def match(self, drug_name: str) -> list[dict]:
        """Matching label records, deterministic order (single-ingredient labels, then generic-named, manufacturer, set id)."""
        key = norm(drug_name)
        idxs = self._by_key.get(key, [])
        def rank(i: int):
            l = self.labels[i]
            first = norm(l["products"][0]) if l["products"] else ""
            return (len(l["ingredients"]) != 1, first != key, l["manufacturer"] or "", l["set_id"])
        return [self.labels[i] for i in sorted(idxs, key=rank)]
