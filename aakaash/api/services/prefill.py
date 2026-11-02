# SOURCE: NOT IN PAPERS. Starting details for a new account, copied from the sample patient files.
"""A new account starts with one patient's details so the screens are not empty. Only columns that
exist in the files are copied. Nothing is invented: the name, date of birth, height, weight and
blood group are left empty, and a medicine's end date is only derived from its two real columns
(start date and duration). The patient id and every identifying column are left behind."""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from medsafe import appms

from ..config import Settings
from ..db import Allergy, Condition, MedicineRecord, Profile, User
from . import appms as appms_service

SEX = {"female": "female", "male": "male"}  # "Other/Not specified" leaves the sex empty

# The sample files tag two indication values as "Infection (synthetic scenario)" and
# "Other (synthetic scenario)". The tag is a note about the file, not part of the reason, so it is
# removed. What remains is copied as it is, except the catch-all "Other", which says nothing.
_FILE_NOTE = re.compile(r"\s*\(synthetic[^)]*\)\s*$", re.IGNORECASE)

# Replaceable in tests so the chosen patient is deterministic.
pick = random.choice


@dataclass
class Prefill:
    sex: str | None = None
    conditions: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    medicines: list[appms.Medication] = field(default_factory=list)


def choose(settings: Settings) -> Prefill | None:
    """One sample patient that has at least one medicine, or None if the files are missing."""
    data = appms_service.get_data(settings)
    if data is None:
        return None
    candidates = [p for p in data.patients if data.meds_by_patient.get(p.patient_id)]
    if not candidates:
        return None
    p = pick(candidates)
    return Prefill(sex=SEX.get(p.gender.strip().lower()),
                   conditions=[c for c in (p.primary_condition, p.secondary_condition) if c],
                   allergies=[p.reported_drug_allergy] if p.reported_drug_allergy else [],
                   medicines=list(data.meds_by_patient[p.patient_id]))


def reason_of(indication: str | None) -> str | None:
    text = _FILE_NOTE.sub("", indication or "").strip()
    return None if not text or text.lower() == "other" else text


def end_date(start: date | None, duration_days: int) -> date | None:
    return start + timedelta(days=duration_days - 1) if start and duration_days > 0 else None


def apply(db: Session, settings: Settings, user: User) -> None:
    """Add the profile and the copied rows for a new user. Does not commit."""
    fill = choose(settings)
    db.add(Profile(user_id=user.id, sex=fill.sex if fill else None))
    if fill is None:
        return
    for name in fill.conditions:
        db.add(Condition(user_id=user.id, name=name, kind="illness", status="current", outcome="ongoing"))
    for allergen in fill.allergies:
        db.add(Allergy(user_id=user.id, allergen=allergen, severity="unknown"))
    for m in fill.medicines:
        db.add(MedicineRecord(user_id=user.id, display_name=m.drug_name, ingredients=json.dumps([m.drug_name]),
                              reason=reason_of(m.indication), dose=m.strength or None, frequency=m.frequency or None,
                              start_date=m.start_date, end_date=end_date(m.start_date, m.duration_days),
                              source="typed"))
