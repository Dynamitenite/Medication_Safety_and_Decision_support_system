# SOURCE: NOT IN PAPERS (own tooling). Creates or resets the synthetic demo account used for the paper screenshots.
"""Seeds Arjun Nair (arjunnair@gmail.com): profile, 2 allergies, 2 conditions, 2 past and 4 current medicines.
Synthetic data only. Medicines are resolved through the real catalogue, so ingredients come from it.

Demo design (see data/appms/ddi_seed_rules.csv):
  * Warfarin + Ecosprin 150 (aspirin) is a seed rule, High: the profile card "Highest risk among your medicines".
  * Severe Amoxicillin allergy; no current medicine contains it. Adding the brand "Abomox 500mg Capsule" live
    gives a Critical allergy alert.

Idempotent. An existing account keeps its password; a missing account is created with the password read from
artifacts/screens/CREDENTIALS.txt (never printed). Run from aakaash/:  ..\.venv\Scripts\python.exe scripts\seed_demo_account.py"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select  # noqa: E402

from api import auth  # noqa: E402
from api.config import get_settings  # noqa: E402
from api.db import Allergy, Condition, MedicineRecord, Profile, User, session_maker  # noqa: E402
from api.services import catalogue  # noqa: E402

EMAIL = "arjunnair@gmail.com"
CRED = ROOT / "artifacts" / "screens" / "CREDENTIALS.txt"

PROFILE = dict(name="Arjun Nair", date_of_birth=date(1968, 3, 14), sex="male", height_cm=172.0, weight_kg=78.0,
               blood_group="B+", notes="Demo account for the paper screenshots. Dummy data.")
ALLERGIES = [
    dict(allergen="Amoxicillin", reaction="Anaphylaxis, throat swelling", severity="severe"),
    dict(allergen="Diclofenac", reaction="Mild skin rash", severity="mild"),
]
CONDITIONS = [
    dict(name="GERD", kind="illness", status="current", outcome="ongoing"),
    dict(name="Coronary Artery Disease", kind="illness", status="current", outcome="ongoing"),
]
# Past courses are typed (no catalogue id); current courses are catalogue picks.
PAST = [
    dict(display_name="Enalapril", ingredients=["Enalapril"], reason="Hypertension", dose="5 mg",
         frequency="Once daily", start_date=date(2026, 2, 20), end_date=date(2026, 2, 26)),
    dict(display_name="Ibuprofen", ingredients=["Ibuprofen"], reason="Osteoarthritis", dose="200 mg",
         frequency="Twice daily", start_date=date(2026, 9, 9), end_date=date(2026, 9, 13)),
]
CURRENT = [  # (catalogue id, reason, dose, frequency); no two share an ingredient
    ("97095", "Atrial fibrillation", "2 mg", "Once daily"),      # Genericart Warfarin 2mg Tablet
    ("72318", "Coronary artery disease", "150 mg", "Once daily"),  # Ecosprin 150 Tablet (aspirin)
    ("94197", "Type 2 diabetes", "1000 mg", "Twice daily"),      # Glycomet 1gm Tablet SR
    ("71087", "High cholesterol", "10 mg", "Once at night"),     # Danavish Atorvastatin 10mg Tablet
]
START = date(2026, 6, 1)


def password() -> str:
    kv = dict(l.split(": ", 1) for l in CRED.read_text(encoding="utf8").strip().splitlines() if ": " in l)
    return kv["password"]


def main() -> None:
    s = get_settings()
    cat = catalogue.get_catalogue(s)
    if cat is None:
        sys.exit("catalogue not available")
    with session_maker(s)() as db:
        user = db.scalar(select(User).where(User.email == EMAIL))
        if user is None:
            user = User(email=EMAIL, password_hash=auth.hash_password(password()))
            db.add(user)
            db.flush()
            print("account created")
        else:
            print("account kept; password unchanged")
        for m in (Allergy, Condition, MedicineRecord, Profile):
            db.execute(delete(m).where(m.user_id == user.id))
        db.add(Profile(user_id=user.id, **PROFILE))
        db.add_all(Allergy(user_id=user.id, **a) for a in ALLERGIES)
        db.add_all(Condition(user_id=user.id, **c) for c in CONDITIONS)
        for p in PAST:
            db.add(MedicineRecord(user_id=user.id, **{**p, "ingredients": json.dumps(p["ingredients"])}))
        for cid, reason, dose, freq in CURRENT:
            row = cat.row(cat.by_id[cid])
            db.add(MedicineRecord(user_id=user.id, catalogue_id=cid, display_name=row["name"],
                                  ingredients=json.dumps(list(row["ingredients"])), reason=reason, dose=dose,
                                  frequency=freq, start_date=START, source="typed"))
            print("current:", row["name"], row["ingredients"])
        db.commit()


if __name__ == "__main__":
    main()
