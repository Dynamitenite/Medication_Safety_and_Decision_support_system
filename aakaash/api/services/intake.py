# SOURCE: NOT IN PAPERS. "Add new medicine": the medicine details card (verbatim US label sections
# chosen by the dosage-form rule), the risk analysis against the signed-in user's current medicines
# and allergies, and saving the confirmed list. Reuses the checker (services/catalogue.py) for rule
# hits and label sentences. Level rules: medsafe/risk.py. Missing data gives status="not_ready".
"""Medicine details, risk analysis and adding medicines for the signed-in user."""
from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from medsafe import health
from medsafe.appms_match import ingredient_keys
from medsafe.risk import ALLERGY_LEVEL, LEVELS, RULE_LEVEL, allergy_matches, highest

from ..config import Settings
from ..db import Allergy, Condition, MedicineRecord, User
from ..schemas import (AddMedicinesRequest, AddMedicinesResponse, AllergyFinding, AnalyzedMedicine, AnalyzeRequest,
                       AnalyzeResponse, AppmsResult, CheckerIngredient, CheckerMedicine, CourseIn, DetailLabel,
                       DetailSection, IngredientDetails, LevelledHit, MedicineDetailsResponse, MedicineRecordIn,
                       PairFinding, ProfileOverview)
from . import accounts, catalogue, medicines
from . import appms as appms_service
from .catalogue import INCOMPLETE_NOTE, LABEL_NOTE, UNCLEAR_NOTE, _brand_med, _generic_med, _Med, _row

DISCLAIMER = "Informational only. Not a substitute for advice from your doctor or pharmacist."
NONE_TEXT = "No known interaction found in our rules. This does not mean the combination is safe."
RULES_MISSING_TEXT = ("The interaction rules are not available right now, so no interaction level could be set. "
                      "This does not mean the combination is safe.")
OVERALL_TEXT = {
    "Critical": "This may be a serious risk. Talk to your doctor or pharmacist before taking this medicine.",
    "High": "Ask your pharmacist about this combination.",
    "Medium": "A possible interaction or allergy match was found. Read the details below.",
}
ALLERGY_NOTE = "Matched by name only. Related medicines in the same class are not checked."
LEVEL_RULE = ("Levels come only from our interaction rules and your recorded allergies. The rules' "
              "“Moderate” is shown as Medium. An allergy match takes its level from the severity you "
              "recorded: mild is Medium, moderate is High, severe is Critical, not known is High. The overall "
              "level is the highest one found. Label text is supporting evidence and never changes the level.")
WITHHELD_NOTE = "No US label in the same form is loaded, so dosage instructions are not shown. Ask your pharmacist."
WITHHELD_COMBINATION_NOTE = ("No US label for this same combination of ingredients is loaded, so dosage instructions "
                             "are not shown. Ask your pharmacist.")
MISMATCH_NOTE = {
    "wrong_form": "This US label is for a different dosage form or route than this medicine.",
    "combination_label": ("This US label is for a combination product whose ingredients are not the same as this "
                          "medicine's."),
    "single_for_combination": "This US label is for this one ingredient alone, not for this combination of ingredients.",
    "form_unknown": "The dosage form of this medicine could not be determined, so the label could not be matched by form.",
}
NAME_ONLY_NOTE = ("was entered without choosing it from the medicine list, so it was checked by its name only and "
                  "its ingredients are not known.")
CRITICAL_ACK = "This list has a Critical warning. Tick “I have read this warning” to add it."
# (key, label) of the instruction sections, in the order shown
INSTRUCTION_ORDER = [("dosage_administration", "Dosage and administration"),
                     ("patient_counseling", "Patient counselling information"),
                     ("patient_information", "Patient information"),
                     ("instructions_for_use", "Instructions for use")]


# ---- details ----------------------------------------------------------------------------------
def _section(lab: dict, key: str, label: str) -> DetailSection | None:
    text = "\n\n".join(s["text"] for s in lab["sections"].get(key, []) if s["text"].strip())
    return DetailSection(key=key, label=label, text=text) if text else None


def _same_ingredients(label_moieties: list[str], brand_keys: list[set[str]]) -> bool:
    """A combination label is about this medicine only when every label moiety is one of the
    brand's ingredients and every brand ingredient is on the label."""
    label_keys = [ingredient_keys(m) for m in label_moieties]
    return (all(any(lk & bk for bk in brand_keys) for lk in label_keys)
            and all(any(lk & bk for lk in label_keys) for bk in brand_keys))


def details(settings: Settings, cid: str) -> MedicineDetailsResponse:
    cat = catalogue.get_catalogue(settings)
    if cat is None:
        return catalogue._not_ready(MedicineDetailsResponse, settings, id=cid)
    i = _row(cat, cid)
    d = cat.detail(i)
    idx = medicines.get_index(settings)
    items = cat.comps[cat.comp[i]]["items"]
    first = {ing: w for ing, _, w in reversed(items)}  # one entry per distinct ingredient
    brand_keys = [ingredient_keys(w, cat.ingredients[ing]["key"]) for ing, w in first.items()]
    out, seen = [], set()
    for x in d["ingredient_details"]:
        if x["key"] in seen:  # a repeated ingredient is shown once
            continue
        seen.add(x["key"])
        base = dict(name=x["name"], strength=x["strength"], us_name=x["us_name"], form_match=x["form_match"],
                    combination_label=False, mismatch=None, mismatch_note=None, indications=None, boxed_warning=None)
        if not x["labels"]:
            out.append(IngredientDetails(status="ready", label=None, **base))
            continue
        ref = x["labels"][0]
        lab_rec = cat.labels.get(ref["set_id"], {})
        base["combination_label"] = not ref["single_ingredient"]
        base["label"] = DetailLabel(set_id=ref["set_id"], name=ref["product"] or ref["title"] or ref["set_id"],
                                    manufacturer=ref["manufacturer"], form=ref["form"], route=ref["route"],
                                    form_family=ref["form_family"])
        if x["form_match"] == "none":
            base["mismatch"] = "wrong_form"
        elif base["combination_label"] and not _same_ingredients(lab_rec.get("moieties", []), brand_keys):
            base["mismatch"] = "combination_label"
        elif not base["combination_label"] and len(brand_keys) > 1:
            base["mismatch"] = "single_for_combination"  # the dose of a combination can differ from either part alone
        elif x["form_match"] == "brand_form_unknown":
            base["mismatch"] = "form_unknown"
        if base["mismatch"]:
            base["mismatch_note"] = MISMATCH_NOTE[base["mismatch"]]
        if idx is None:
            out.append(medicines._not_ready(IngredientDetails, settings, **base))
            continue
        try:
            lab = medicines.load_label(settings, idx, ref["set_id"])
        except HTTPException as e:
            out.append(IngredientDetails(status="not_ready", reason=str(e.detail),
                                         fix="Add the DailyMed zip named above to the data folder.", **base))
            continue
        base["indications"] = _section(lab, "indications", "Indications and usage")
        base["boxed_warning"] = _section(lab, "boxed_warning", "Boxed warning")
        missing = [] if base["indications"] else ["Indications and usage"]
        instructions, withheld = [], None
        if base["mismatch"]:
            # never dosage or instruction text from a label of another form or another product
            withheld = WITHHELD_COMBINATION_NOTE if base["mismatch"] == "single_for_combination" else WITHHELD_NOTE
        else:
            for key, label in INSTRUCTION_ORDER:
                s = _section(lab, key, label)
                if s:
                    instructions.append(s)
                elif key in ("dosage_administration", "patient_counseling"):
                    missing.append(label)
        out.append(IngredientDetails(status="ready", instructions=instructions, missing=missing,
                                     withheld_note=withheld, **base))
    return MedicineDetailsResponse(
        status="ready", id=cid, name=d["name"], form_family=d["form_family"], composition=d["composition"],
        composition_incomplete=d["composition_incomplete"] or d["composition_conflict"],
        composition_unclear=d["composition_unclear"], label_note=LABEL_NOTE, ingredients=out)


# ---- risk analysis ----------------------------------------------------------------------------
def _record_med(cat, idx, r: MedicineRecord) -> tuple[_Med, bool]:
    """A current medicine as the checker sees it: by catalogue id, else by its stored ingredients,
    else by the name the user typed. Second value: checked by name only."""
    in_cat = bool(r.catalogue_id) and r.catalogue_id in cat.by_id
    names = [n for n in json.loads(r.ingredients or "[]") if n.strip()]
    by_name = not in_cat and not names
    if in_cat:
        m = _brand_med(cat, r.catalogue_id)
    else:
        ings = [_generic_med(cat, idx, n).ings[0] for n in (names or [r.display_name])]
        m = _Med(CheckerMedicine(key="", catalogue_id=None, name=r.display_name, manufacturer=None,
                                 kind="generic" if by_name else "brand",
                                 ingredients=[CheckerIngredient(name=g.name, us_name=g.us_name, label_set_id=g.ref,
                                                                label_name=g.label_name) for g in ings],
                                 composition_incomplete=False), ings, None)
    m.out = m.out.model_copy(update={"key": f"record:{r.id}"})
    return m, by_name


def _current_records(db: Session, user: User, today: date) -> list[MedicineRecord]:
    rows = db.scalars(select(MedicineRecord).where(MedicineRecord.user_id == user.id).order_by(MedicineRecord.id))
    return [r for r in rows if health.course_status(r.start_date, r.end_date, today) in ("current", "not_stated")]


def _comp_notes(*meds: _Med) -> list[str]:
    notes = [f"{m.out.name}: {INCOMPLETE_NOTE}" for m in meds if m.out.composition_incomplete and not m.out.composition_unclear]
    return notes + [f"{m.out.name}: {UNCLEAR_NOTE}" for m in meds if m.out.composition_unclear]


def analyze(db: Session, settings: Settings, user: User, ids: list[str], today: date | None = None) -> AnalyzeResponse:
    today = today or date.today()
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Each medicine can be added only once.")
    cat = catalogue.get_catalogue(settings)
    if cat is None:
        return catalogue._not_ready(AnalyzeResponse, settings)
    idx = medicines.get_index(settings)
    new = [_brand_med(cat, c) for c in ids]
    cur = []
    for r in _current_records(db, user, today):
        m, by_name = _record_med(cat, idx, r)
        cur.append((m, r, by_name))
    rules = appms_service.get_data(settings)
    rules_status = (AppmsResult(status="ready", source_label=catalogue.RULES_LABEL) if rules is not None
                    else catalogue._rules(None, new[0], new[0]))

    roster = [AnalyzedMedicine(medicine=m.out, role="new") for m in new]
    roster += [AnalyzedMedicine(medicine=m.out, role="current", record_id=r.id, dates_not_entered=r.start_date is None,
                                checked_by_name_only=by_name) for m, r, by_name in cur]
    name_only = {m.out.key: f"{m.out.name} {NAME_ONLY_NOTE}" for m, _, by_name in cur if by_name}

    pairs, checked = [], 0
    jobs = [(a, "new", b, "current") for a in new for b, _, _ in cur]
    jobs += [(new[x], "new", new[y], "new") for x in range(len(new)) for y in range(x + 1, len(new))]
    for a, ar, b, br in jobs:
        checked += 1
        res = catalogue._rules(rules, a, b)
        hits = [LevelledHit(a_ingredient=h.a_ingredient, b_ingredient=h.b_ingredient, level=RULE_LEVEL[h.severity],
                            rule_tier=h.severity, explanation=h.explanation) for h in res.hits]
        text = catalogue._text(settings, idx, a, b)
        shared = sorted({g.name for g in a.ings for h in b.ings if g.key == h.key})
        if not (hits or text.matches_total or shared):
            continue
        notes = _comp_notes(a, b) + [name_only[m.out.key] for m in (a, b) if m.out.key in name_only]
        pairs.append(PairFinding(a=a.out, b=b.out, a_role=ar, b_role=br, level=highest(h.level for h in hits),
                                 hits=hits, text_match=text, shared_ingredients=shared, notes=notes))
    rank = {lv: k for k, lv in enumerate(reversed(LEVELS))}
    pairs.sort(key=lambda p: (rank.get(p.level, len(LEVELS)), -p.text_match.matches_total))

    allergies = list(db.scalars(select(Allergy).where(Allergy.user_id == user.id).order_by(Allergy.id)))
    found = []
    for m in new:
        for al in allergies:
            hit = sorted({g.name for g in m.ings if allergy_matches(al.allergen, g.name, g.key)})
            if hit:
                found.append(AllergyFinding(medicine=m.out, allergy_id=al.id, allergen=al.allergen, reaction=al.reaction,
                                            severity=al.severity, level=ALLERGY_LEVEL[al.severity], ingredients=hit,
                                            note=ALLERGY_NOTE, notes=_comp_notes(m)))
    found.sort(key=lambda f: rank[f.level])

    overall = highest([p.level for p in pairs] + [f.level for f in found])
    text = OVERALL_TEXT[overall] if overall else (NONE_TEXT if rules is not None else RULES_MISSING_TEXT)
    return AnalyzeResponse(status="ready", overall=overall, overall_text=text, levels=list(LEVELS), rules=rules_status,
                           medicines=roster, allergies_checked=len(allergies), allergy_note=ALLERGY_NOTE,
                           allergy_findings=found, pairs=pairs, pairs_checked=checked, disclaimer=DISCLAIMER,
                           level_rule=LEVEL_RULE)


def overview(db: Session, settings: Settings, user: User, today: date | None = None) -> ProfileOverview:
    """Profile tiles: counts, and the highest level the interaction rules give any pair of current
    medicines. Read-only; uses the same rules as the risk analysis."""
    today = today or date.today()
    records = _current_records(db, user, today)
    n_all = db.scalar(select(func.count()).select_from(Allergy).where(Allergy.user_id == user.id)) or 0
    n_cond = db.scalar(select(func.count()).select_from(Condition).where(
        Condition.user_id == user.id, Condition.status == "current")) or 0
    base = dict(current_medicines=len(records), allergies=n_all, current_conditions=n_cond)
    cat = catalogue.get_catalogue(settings)
    rules = appms_service.get_data(settings)
    if len(records) < 2 or cat is None or rules is None:
        why = ("Fewer than two current medicines." if len(records) < 2
               else "The interaction rules or the medicine catalogue are not available right now.")
        return ProfileOverview(risk_status="not_enough_data", risk_note=why, **base)
    idx = medicines.get_index(settings)
    meds = [_record_med(cat, idx, r)[0] for r in records]
    levels, checked = [], 0
    for x in range(len(meds)):
        for y in range(x + 1, len(meds)):
            checked += 1
            res = catalogue._rules(rules, meds[x], meds[y])
            levels += [RULE_LEVEL[h.severity] for h in res.hits]
    top = highest(levels)
    return ProfileOverview(risk_status="found" if top else "none_found", highest_risk=top, pairs_checked=checked,
                           risk_note=NONE_TEXT if not top else "", **base)


def analyze_request(db: Session, settings: Settings, user: User, body: AnalyzeRequest) -> AnalyzeResponse:
    return analyze(db, settings, user, [m.catalogue_id for m in body.medicines])


# ---- adding -----------------------------------------------------------------------------------
def course_record(item: CourseIn, today: date) -> MedicineRecordIn:
    """The record to save. Start defaults to today; a duration gives the end date (both days counted)."""
    start = item.start_date or today
    end = item.end_date or (start + timedelta(days=item.duration_days - 1) if item.duration_days else None)
    if end is not None and end < start:
        raise HTTPException(422, "The end date cannot be before the start date (today, when no start date is given).")
    return MedicineRecordIn(catalogue_id=item.catalogue_id, display_name=item.catalogue_id, reason=item.reason,
                            dose=item.dose, frequency=item.frequency, start_date=start, end_date=end,
                            source=item.source, notes=f"Food: {item.food}" if item.food else None)


def add(db: Session, settings: Settings, user: User, body: AddMedicinesRequest,
        today: date | None = None) -> AddMedicinesResponse:
    """Run the analysis again on the server, then save. A Critical result needs the acknowledgement;
    nothing else blocks adding."""
    today = today or date.today()
    result = analyze(db, settings, user, [x.catalogue_id for x in body.items], today)
    if result.status != "ready":
        raise HTTPException(503, result.reason or "The medicine catalogue is not available right now.")
    if result.overall == "Critical" and not body.acknowledged_warning:
        raise HTTPException(409, CRITICAL_ACK)
    added = [accounts.create_medicine(db, settings, user, course_record(x, today)) for x in body.items]
    return AddMedicinesResponse(overall=result.overall, added=added)
