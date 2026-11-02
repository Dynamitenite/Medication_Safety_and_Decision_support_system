# SOURCE: NOT IN PAPERS. Own app rules for the "Add new medicine" risk analysis. The level names
# Critical and High follow the tier labels of P10 (Shakarbaev, IJMI 215), labels only; "Medium" and
# every assignment rule below are our own. No score, no model.
"""Pure logic: level mapping, the overall level, and the allergy name match."""
from __future__ import annotations

from typing import Literal

from .appms_match import COUNTER_IONS, ingredient_keys
from .names import norm
from .synonyms import canonical

Level = Literal["Medium", "High", "Critical"]
LEVELS: tuple[Level, ...] = ("Medium", "High", "Critical")  # lowest to highest
# the interaction rules' tiers; "Moderate" is shown to users as Medium
RULE_LEVEL: dict[str, Level] = {"moderate": "Medium", "high": "High", "critical": "Critical"}
# the severity the user recorded for an allergy
ALLERGY_LEVEL: dict[str, Level] = {"mild": "Medium", "moderate": "High", "severe": "Critical", "unknown": "High"}


def highest(levels) -> Level | None:
    """The highest level in `levels`, or None when there is none."""
    found = [l for l in levels if l is not None]
    return max(found, key=LEVELS.index) if found else None


def allergy_matches(allergen: str, ingredient_name: str, ingredient_key: str | None = None) -> bool:
    """True when the allergen names this ingredient. Two exact rules, nothing fuzzy:
    1. the allergen's name keys (normalised, approved synonyms, trailing salt words dropped) meet
       the ingredient's keys: "amoxycillin" matches "Amoxicillin Trihydrate";
    2. the allergen appears as whole words inside the ingredient name: "penicillin" matches
       "Benzathine Penicillin G" but not "Amoxicillin" (no class knowledge).
    An allergen that is only a counter-ion or salt word ("sodium") never uses rule 2."""
    a_keys = ingredient_keys(allergen)
    i_keys = ingredient_keys(ingredient_name, *([ingredient_key] if ingredient_key else []))
    if not a_keys or not i_keys:
        return False
    if a_keys & i_keys:
        return True
    for a in {norm(allergen), canonical(allergen)}:
        if not a or all(w in COUNTER_IONS for w in a.split()):
            continue
        if any(f" {a} " in f" {t} " for t in i_keys | {norm(ingredient_name)}):
            return True
    return False
