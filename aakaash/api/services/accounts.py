# SOURCE: NOT IN PAPERS. Account, profile and medical-history logic behind the /api routes.
"""Every function takes the signed-in User and only touches rows with user_id == user.id.
Looking up another person's row id gives the same 404 as an id that does not exist."""
from __future__ import annotations

import json
from datetime import date
from typing import TypeVar

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from medsafe import health

from .. import auth
from ..config import Settings
from ..db import Allergy, Condition, MedicineRecord, Profile, User
from ..schemas import (AllergyIn, AllergyOut, ConditionIn, ConditionOut, LoginRequest, LoginResponse,
                       MedicineRecordIn, MedicineRecordOut, ProfileIn, ProfileOut)
from . import catalogue, prefill

T = TypeVar("T", Allergy, Condition, MedicineRecord)

WRONG = "Email or password is incorrect."


# ---- sign in / out ----------------------------------------------------------------------------
def login(db: Session, settings: Settings, body: LoginRequest, request: Request, response: Response) -> LoginResponse:
    """Sign in an existing email, or create the account for a new one."""
    wait = auth.retry_after(body.email, request)
    if wait:
        raise HTTPException(429, "Too many attempts. Try again later.", headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(User.email == body.email))
    created = user is None
    if user is None:
        user = User(email=body.email, password_hash=auth.hash_password(body.password))
        db.add(user)
        db.flush()
        prefill.apply(db, settings, user)
        db.commit()
        response.status_code = 201
    elif not auth.verify_password(user.password_hash, body.password):
        auth.record_failure(body.email, request)
        raise HTTPException(401, WRONG)
    elif auth.needs_rehash(user.password_hash):
        user.password_hash = auth.hash_password(body.password)
        db.commit()
    auth.clear_failures(body.email, request)
    auth.start_session(db, user, request, response)
    return LoginResponse(email=user.email, created=created)


def delete_account(db: Session, user: User, response: Response) -> None:
    """Remove the user; the database cascade removes every row that belongs to them."""
    db.delete(user)
    db.commit()
    response.delete_cookie(auth.COOKIE, path="/")


# ---- profile ----------------------------------------------------------------------------------
def _profile(db: Session, user: User) -> Profile:
    p = db.get(Profile, user.id)
    if p is None:  # an account always has one; recreate rather than fail
        p = Profile(user_id=user.id)
        db.add(p)
        db.commit()
    return p


def profile_out(p: Profile, today: date | None = None) -> ProfileOut:
    today = today or date.today()
    return ProfileOut(name=p.name, date_of_birth=p.date_of_birth, age=health.age(p.date_of_birth, today),
                      sex=p.sex, height_cm=p.height_cm, weight_kg=p.weight_kg,
                      bmi=health.bmi(p.height_cm, p.weight_kg), blood_group=p.blood_group, notes=p.notes,
                      updated_at=p.updated_at)


def get_profile(db: Session, user: User) -> ProfileOut:
    return profile_out(_profile(db, user))


def put_profile(db: Session, user: User, body: ProfileIn) -> ProfileOut:
    p = _profile(db, user)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return profile_out(p)


# ---- shared row helpers -----------------------------------------------------------------------
def _owned(db: Session, model: type[T], item_id: int, user: User) -> T:
    row = db.scalar(select(model).where(model.id == item_id, model.user_id == user.id))
    if row is None:
        raise HTTPException(404, "Not found.")
    return row


def _save(db: Session, row, fields: dict) -> None:
    for k, v in fields.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    db.refresh(row)


def _remove(db: Session, row) -> None:
    db.delete(row)
    db.commit()


# ---- allergies --------------------------------------------------------------------------------
def list_allergies(db: Session, user: User) -> list[AllergyOut]:
    rows = db.scalars(select(Allergy).where(Allergy.user_id == user.id).order_by(Allergy.id))
    return [AllergyOut.model_validate(r, from_attributes=True) for r in rows]


def create_allergy(db: Session, user: User, body: AllergyIn) -> AllergyOut:
    row = Allergy(user_id=user.id)
    _save(db, row, body.model_dump())
    return AllergyOut.model_validate(row, from_attributes=True)


def update_allergy(db: Session, user: User, item_id: int, body: AllergyIn) -> AllergyOut:
    row = _owned(db, Allergy, item_id, user)
    _save(db, row, body.model_dump())
    return AllergyOut.model_validate(row, from_attributes=True)


def delete_allergy(db: Session, user: User, item_id: int) -> None:
    _remove(db, _owned(db, Allergy, item_id, user))


# ---- conditions -------------------------------------------------------------------------------
def list_conditions(db: Session, user: User, status: str | None) -> list[ConditionOut]:
    q = select(Condition).where(Condition.user_id == user.id)
    if status:
        q = q.where(Condition.status == status)
    return [ConditionOut.model_validate(r, from_attributes=True) for r in db.scalars(q.order_by(Condition.id))]


def create_condition(db: Session, user: User, body: ConditionIn) -> ConditionOut:
    row = Condition(user_id=user.id)
    _save(db, row, body.model_dump())
    return ConditionOut.model_validate(row, from_attributes=True)


def update_condition(db: Session, user: User, item_id: int, body: ConditionIn) -> ConditionOut:
    row = _owned(db, Condition, item_id, user)
    _save(db, row, body.model_dump())
    return ConditionOut.model_validate(row, from_attributes=True)


def delete_condition(db: Session, user: User, item_id: int) -> None:
    _remove(db, _owned(db, Condition, item_id, user))


# ---- medicine records -------------------------------------------------------------------------
def medicine_out(r: MedicineRecord, today: date | None = None) -> MedicineRecordOut:
    today = today or date.today()
    return MedicineRecordOut(
        id=r.id, catalogue_id=r.catalogue_id, display_name=r.display_name, ingredients=json.loads(r.ingredients or "[]"),
        reason=r.reason, dose=r.dose, frequency=r.frequency, start_date=r.start_date, end_date=r.end_date,
        outcome=r.outcome, source=r.source, notes=r.notes,
        status=health.course_status(r.start_date, r.end_date, today),
        duration_days=health.course_days(r.start_date, r.end_date, today))


def _medicine_fields(settings: Settings, body: MedicineRecordIn) -> dict:
    """Fields to store. A catalogue pick takes its name and ingredients from the catalogue itself;
    ingredients sent by the client are never used. A typed name has no known ingredients."""
    fields = body.model_dump()
    fields["ingredients"] = "[]"
    if body.catalogue_id:
        cat = catalogue.get_catalogue(settings)
        if cat is None:
            raise HTTPException(503, "The medicine catalogue is not available right now. "
                                     "Enter the medicine without choosing it from the list, or try again later.")
        i = cat.by_id.get(body.catalogue_id)
        if i is None:
            raise HTTPException(404, f"No medicine with id {body.catalogue_id}.")
        row = cat.row(i)
        fields["display_name"] = row["name"]
        fields["ingredients"] = json.dumps(list(row["ingredients"]))
    return fields


def list_medicines(db: Session, user: User) -> list[MedicineRecordOut]:
    rows = db.scalars(select(MedicineRecord).where(MedicineRecord.user_id == user.id).order_by(MedicineRecord.id))
    return [medicine_out(r) for r in rows]


def create_medicine(db: Session, settings: Settings, user: User, body: MedicineRecordIn) -> MedicineRecordOut:
    row = MedicineRecord(user_id=user.id)
    _save(db, row, _medicine_fields(settings, body))
    return medicine_out(row)


def update_medicine(db: Session, settings: Settings, user: User, item_id: int, body: MedicineRecordIn) -> MedicineRecordOut:
    row = _owned(db, MedicineRecord, item_id, user)
    _save(db, row, _medicine_fields(settings, body))
    return medicine_out(row)


def delete_medicine(db: Session, user: User, item_id: int) -> None:
    _remove(db, _owned(db, MedicineRecord, item_id, user))
