# SOURCE: NOT IN PAPERS. Own design: a dosage-form family for a catalogue product (from its name and
# pack_size_label) and for a DailyMed label (from the SPL formCode and routeCode, or its title words).
# Plain word rules, no model. Families were chosen after looking at the real word counts of the
# catalogue (scripts/measure_forms.py prints them).
"""Pure logic (no file access). A family is a coarse class of dosage form: products in different
families are never offered as same-form alternatives. 'unknown' means no rule matched."""
from __future__ import annotations

import re

ORAL_SOLID = "oral solid"
ORAL_LIQUID = "oral liquid"
INJECTABLE = "injectable"
TOPICAL = "topical"
EYE_EAR = "eye/ear"
NASAL = "nasal"
INHALATION = "inhalation"
ORAL_CAVITY = "mouth/throat"
RECTAL_VAGINAL = "rectal/vaginal"
OTHER = "other"
UNKNOWN = "unknown"
FAMILIES = (ORAL_SOLID, ORAL_LIQUID, INJECTABLE, TOPICAL, EYE_EAR, NASAL, INHALATION, ORAL_CAVITY,
            RECTAL_VAGINAL, OTHER, UNKNOWN)

# (family, term) in priority order: the first rule whose pattern is found wins. Specific routes
# come before the generic words, so 'eye drops' is never 'drops' and 'mouth dissolving tablet'
# is a tablet. Bare 'solution', 'liquid', 'drops', 'powder' and 'emulsion' have no rule: they do not
# say how the product is taken, so they stay unknown.
_RULES: list[tuple[str, str, re.Pattern]] = [
    (fam, term, re.compile(rx, re.I)) for fam, term, rx in [
        (INJECTABLE, "injection", r"\binjections?\b|\binjectable\b"),
        (INJECTABLE, "infusion", r"\binfusions?\b"),
        (INJECTABLE, "vial", r"\bvials?\b"),
        (INJECTABLE, "ampoule", r"\bamp(?:o|ou)les?\b"),
        (INJECTABLE, "syringe", r"\bsyringes?\b"),
        (INJECTABLE, "pen", r"\bpen\b|\bcartridges?\b"),
        (NASAL, "nasal", r"\bnasal\b|\bnostril\b"),
        (INHALATION, "inhaler",r"\binhalers?\b|\bmdi\b|\bhaler\b"),
        (INHALATION, "respules", r"\brespules?\b|\bnebuli[sz]\w*|\bnebs?\b"),
        (INHALATION, "rotacap", r"\brotacaps?\b|\brespicaps?\b|\binhalation\b|\btranscaps?\b"),
        (EYE_EAR, "eye", r"\beye\b|\bophthalmic\b|\bopthalmic\b|\bocular\b"),
        (EYE_EAR, "ear", r"\bear\b|\botic\b"),
        (RECTAL_VAGINAL, "suppository", r"\bsuppositor\w+|\bpessar\w+|\benemas?\b|\bvaginal\b|\brectal\b"),
        (ORAL_SOLID, "tablet", r"\btablets?\b|\btabs?\b|\bcaplets?\b"),
        (ORAL_SOLID, "capsule", r"\bcapsules?\b|\bcaps\b|\bsoftgels?\b|\bgelatin\b"),
        (ORAL_SOLID, "chewable", r"\bchewable\b|\bchewing gums?\b|\bgums\b|\blozenges?\b|\bdispersible\b"),
        (ORAL_SOLID, "sachet", r"\bsachets?\b|\bgranules?\b|\bdisintegrating\b|\beffervescent\b"),
        (ORAL_CAVITY, "mouth", r"\bmouth\b|\bgargle\b|\btoothpaste\b|\bdental\b|\bthroat\b|\boral (?:gel|paste|spray)\b"),
        (ORAL_LIQUID, "syrup", r"\bsyrups?\b|\belixir\b|\blinctus\b|\btonic\b"),
        (ORAL_LIQUID, "suspension", r"\bsuspensions?\b|\bexpectorant\b"),
        (ORAL_LIQUID, "oral drops", r"\boral (?:drops?|solution|liquid)\b|\bpaediatric drops?\b|\bpediatric drops?\b"),
        (TOPICAL, "cream", r"\bcreams?\b|\bgels?\b|\bointments?\b|\blotions?\b|\bliniment\b|\bpaste\b"),
        (TOPICAL, "shampoo", r"\bshampoo\b|\bsoap\b|\bwash\b|\bpatch(?:es)?\b|\btransdermal\b|\bfoam\b|\bdusting\b|\bspray\b"),
        (OTHER, "kit", r"\bkits?\b|\bcombikit\b"),
    ]
]


def classify_text(text: str | None) -> tuple[str, str | None]:
    """(family, the rule's term) for a piece of text; ('unknown', None) when no rule matches."""
    t = text or ""
    for fam, term, rx in _RULES:
        if rx.search(t):
            return fam, term
    return UNKNOWN, None


def classify_product(name: str, pack: str) -> tuple[str, str | None, str | None]:
    """Family of a catalogue product: the pack label first (it is written 'strip of 10 tablets'),
    then the name. Returns (family, term, where) with where 'pack', 'name' or None."""
    fam, term = classify_text(pack)
    # a generic pack word ('capsules', 'Paste') loses to a more specific name word ('Rotacaps', 'Oral Paste')
    if fam in (ORAL_SOLID, TOPICAL):
        nfam, nterm = classify_text(name)
        if nfam in (INHALATION, OTHER) or (fam == TOPICAL and nfam in (ORAL_CAVITY, EYE_EAR, NASAL, RECTAL_VAGINAL)):
            return nfam, nterm, "name"
    if fam != UNKNOWN:
        return fam, term, "pack"
    fam, term = classify_text(name)
    if fam != UNKNOWN:
        return fam, term, "name"
    return UNKNOWN, None, None


# route (SPL routeCode displayName, upper case) -> family, for routes that decide the family
ROUTE_FAMILY = {
    "INTRAVENOUS": INJECTABLE, "INTRAMUSCULAR": INJECTABLE, "SUBCUTANEOUS": INJECTABLE, "INTRADERMAL": INJECTABLE,
    "INTRATHECAL": INJECTABLE, "EPIDURAL": INJECTABLE, "INTRA-ARTICULAR": INJECTABLE, "INTRAVITREAL": INJECTABLE,
    "INTRAVENTRICULAR": INJECTABLE, "INTRACAVERNOUS": INJECTABLE, "INTRALESIONAL": INJECTABLE,
    "INTRAPERITONEAL": INJECTABLE, "INTRAOCULAR": INJECTABLE, "PARENTERAL": INJECTABLE, "INFILTRATION": INJECTABLE,
    "OPHTHALMIC": EYE_EAR, "AURICULAR (OTIC)": EYE_EAR, "CONJUNCTIVAL": EYE_EAR,
    "NASAL": NASAL, "RESPIRATORY (INHALATION)": INHALATION, "ORAL; RESPIRATORY (INHALATION)": INHALATION,
    "TOPICAL": TOPICAL, "CUTANEOUS": TOPICAL, "TRANSDERMAL": TOPICAL,
    "RECTAL": RECTAL_VAGINAL, "VAGINAL": RECTAL_VAGINAL,
}


def classify_spl(form: str | None, routes: list[str] | None = None) -> str:
    """Family of one DailyMed product from its formCode name and route names.
    A form that names its own class (TABLET, INJECTION, CREAM, KIT ...) wins; otherwise the route
    decides for a generic form (SOLUTION, SUSPENSION, POWDER, LIQUID ...); ORAL + liquid word = oral liquid."""
    fam, _ = classify_text(form)
    # SUSPENSION/SYRUP map to oral liquid by word, but for a non-oral route the route is better
    route_fams = [ROUTE_FAMILY[r.upper()] for r in (routes or []) if r and r.upper() in ROUTE_FAMILY]
    if fam in (ORAL_SOLID, INJECTABLE, INHALATION, TOPICAL, EYE_EAR, NASAL, RECTAL_VAGINAL, OTHER, ORAL_CAVITY):
        return fam
    if route_fams:
        return route_fams[0]
    if fam == ORAL_LIQUID:
        return fam
    f = (form or "").upper()
    oral = any((r or "").upper() in ("ORAL", "SUBLINGUAL", "BUCCAL") for r in (routes or []))
    if oral and re.search(r"SOLUTION|SUSPENSION|LIQUID|DROPS?|CONCENTRATE|EMULSION", f):
        return ORAL_LIQUID
    if oral and re.search(r"POWDER|GRANULE|PELLET|FILM|STRIP|WAFER", f):
        return ORAL_SOLID
    return UNKNOWN


def describe(dosage_forms: list[dict] | None) -> str | None:
    """'Tablet, film coated · Oral' for display; up to two products, then '+ more'. None when the SPL has no form."""
    parts = []
    for p in dosage_forms or []:
        f = (p.get("form") or "").strip()
        if not f:
            continue
        r = ", ".join(x[:1] + x[1:].lower() for x in p.get("routes") or [])
        t = f[:1] + f[1:].lower() + (f" · {r}" if r else "")
        if t not in parts:
            parts.append(t)
    return "; ".join(parts[:2]) + (" + more" if len(parts) > 2 else "") if parts else None


def classify_label(dosage_forms: list[dict] | None, title: str | None) -> tuple[list[str], bool]:
    """(families, inferred) for a DailyMed label. dosage_forms is the parser's [{'form', 'routes'}].
    With no form in the SPL the title words are used and inferred is True."""
    fams: list[str] = []
    for p in dosage_forms or []:
        f = classify_spl(p.get("form"), p.get("routes"))
        if f not in fams:
            fams.append(f)
    if fams and fams != [UNKNOWN]:
        return [f for f in fams if f != UNKNOWN] or [UNKNOWN], False
    if dosage_forms:  # the SPL named a form we could not place: say unknown, do not guess from the title
        return [UNKNOWN], False
    fam, _ = classify_text(title)
    return [fam], True
