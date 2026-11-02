# SOURCE: NOT IN PAPERS. FIXTURES ONLY: every patient, medicine and date below is hand-written to
# exercise code paths. None of it is real data and none of it may appear in the UI.
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from api import auth, db
from api.app import app
from api.config import Settings, get_settings
from api.services import appms as appms_service, catalogue as catalogue_service, prefill

from fixtures_catalogue import write_artifacts

PATIENTS = """patient_id,age_years,gender,state,district,residence_type,primary_condition,secondary_condition,reported_drug_allergy,egfr_category,data_origin
P1,40,Female,StateA,DistX,Urban,Condone,None,None,60-89,SYNTHETIC
P2,70,Other/Not specified,StateB,DistY,Rural,Condtwo,Condthree,Fixallergy,<30,SYNTHETIC
P3,50,Male,StateC,DistZ,Urban,Nevercopied,None,None,90+,SYNTHETIC
"""
MEDS = """medication_record_id,patient_id,drug_name,strength,route,indication,frequency,duration_days,start_date_synthetic,data_origin
P1-M1,P1,Alphadrug,5 mg,oral,Indone (synthetic scenario),Once daily,30,2026-01-01,SYNTHETIC
P1-M2,P1,Betadrug,10 mg,oral,Indtwo,Twice daily,7,,SYNTHETIC
P2-M1,P2,Gammadrug,2 mg,oral,Other (synthetic scenario),As needed,5,2026-03-10,SYNTHETIC
"""
SCEN_HEAD = ("scenario_id,patient_id,drug_a,drug_b,known_interaction_in_seed_rules,severity_label,"
             "interaction_category,mechanism_or_risk,xai_explanation,evidence_source,label_scope,data_origin\n")
RULES_HEAD = "drug_a,drug_b,severity_label,interaction_category,mechanism_or_risk,explanation_or_action,evidence_source\n"

PW = "correct horse battery"
TABLES = (db.User, db.LoginSession, db.Profile, db.Allergy, db.Condition, db.MedicineRecord)
OWNED = {"/api/allergies": {"allergen": "Pollenx", "severity": "mild"},
         "/api/conditions": {"name": "Illone", "kind": "illness", "status": "current"},
         "/api/medicine-records": {"display_name": "Typedrug"}}


def _settings(tmp_path, with_data=True):
    folder = tmp_path / "data" / "appms"
    if with_data:
        folder.mkdir(parents=True)
        for name, text in (("patients.csv", PATIENTS), ("medications.csv", MEDS),
                           ("patient_drug_pair_scenarios.csv", SCEN_HEAD), ("ddi_seed_rules.csv", RULES_HEAD)):
            (folder / name).write_text(text, encoding="utf-8")
    return Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art", trace_path=tmp_path / "t.md",
                    encoder_name="tfidf", classifier_name="x")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-anywhere-else")
    monkeypatch.setattr(prefill, "pick", lambda xs: xs[0])
    settings = _settings(tmp_path)
    write_artifacts(settings.artifacts_dir)
    app.dependency_overrides[get_settings] = lambda: settings
    catalogue_service.clear_cache()
    auth.reset_rate_limit()
    yield settings
    app.dependency_overrides.clear()
    catalogue_service.clear_cache()
    db.dispose_all()


def sign_in(email="a@example.com", pw=PW):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code in (200, 201), r.text
    return c


def count(settings, model, **where):
    with db.session_maker(settings)() as s:
        q = select(func.count()).select_from(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return s.scalar(q)


def user_id(settings, email):
    with db.session_maker(settings)() as s:
        return s.scalar(select(db.User.id).where(db.User.email == email))


# ---- sign in creates an account and pre-fills -------------------------------------------------
def test_new_email_creates_account_and_prefills(env):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "  New@Example.com ", "password": PW})
    assert r.status_code == 201 and r.json() == {"email": "new@example.com", "created": True}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie

    p = c.get("/api/profile").json()
    assert p["sex"] == "female"
    assert all(p[k] is None for k in ("name", "date_of_birth", "age", "height_cm", "weight_kg", "bmi", "blood_group", "notes"))

    conds = c.get("/api/conditions").json()
    assert [(x["name"], x["status"], x["kind"], x["outcome"], x["onset_date"]) for x in conds] == \
        [("Condone", "current", "illness", "ongoing", None)]
    assert c.get("/api/allergies").json() == []

    meds = {m["display_name"]: m for m in c.get("/api/medicine-records").json()}
    a, b = meds["Alphadrug"], meds["Betadrug"]
    assert (a["dose"], a["frequency"], a["reason"]) == ("5 mg", "Once daily", "Indone")  # file note removed
    assert (a["start_date"], a["end_date"]) == ("2026-01-01", "2026-01-30")   # start + 30 days - 1
    assert a["duration_days"] == 30 and a["outcome"] is None and a["catalogue_id"] is None and a["source"] == "typed"
    assert (b["start_date"], b["end_date"], b["status"], b["duration_days"]) == (None, None, "not_stated", None)


def test_prefill_copies_only_real_fields(env):
    prefill.pick = lambda xs: xs[-1]  # last patient that has medicines: P2 (P3 has none and is skipped)
    c = sign_in("two@example.com")
    p = c.get("/api/profile").json()
    assert p["sex"] is None  # "Other/Not specified" is not turned into a sex
    assert sorted(x["name"] for x in c.get("/api/conditions").json()) == ["Condthree", "Condtwo"]
    allergies = c.get("/api/allergies").json()
    assert [(x["allergen"], x["severity"], x["reaction"]) for x in allergies] == [("Fixallergy", "unknown", None)]
    meds = c.get("/api/medicine-records").json()
    assert [m["display_name"] for m in meds] == ["Gammadrug"]
    assert (meds[0]["start_date"], meds[0]["end_date"]) == ("2026-03-10", "2026-03-14")
    assert meds[0]["reason"] is None  # "Other" alone is not a reason
    everything = json.dumps([p, c.get("/api/conditions").json(), allergies, meds, c.get("/api/auth/me").json()])
    for leaked in ("P1", "P2", "P3", "StateB", "DistY", "Rural", "<30", "SYNTHETIC", "synthetic", "Nevercopied", "oral"):
        assert leaked not in everything


def test_signup_without_sample_files_gives_empty_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "x" * 20)
    settings = _settings(tmp_path, with_data=False)
    app.dependency_overrides[get_settings] = lambda: settings
    auth.reset_rate_limit()
    try:
        c = sign_in("empty@example.com")
        assert c.get("/api/profile").json()["sex"] is None
        assert c.get("/api/conditions").json() == [] and c.get("/api/allergies").json() == []
        assert c.get("/api/medicine-records").json() == []
    finally:
        app.dependency_overrides.clear()
        db.dispose_all()


# ---- passwords, sessions, rate limit ----------------------------------------------------------
def test_wrong_password_rejected_and_right_accepted(env):
    sign_in("a@example.com")
    c = TestClient(app)
    bad = c.post("/api/auth/login", json={"email": "a@example.com", "password": "not the password"})
    assert bad.status_code == 401 and bad.json()["detail"] == "Email or password is incorrect."
    assert "set-cookie" not in bad.headers and c.get("/api/auth/me").status_code == 401
    good = c.post("/api/auth/login", json={"email": "A@Example.com", "password": PW})
    assert good.status_code == 200 and good.json()["created"] is False
    assert c.get("/api/auth/me").json()["email"] == "a@example.com"
    assert count(env, db.User) == 1  # same account, not a second one


def test_password_is_hashed_in_storage(env):
    sign_in("a@example.com")
    with db.session_maker(env)() as s:
        stored = s.scalar(select(db.User.password_hash))
    assert stored.startswith("$argon2id$") and PW not in stored


def test_input_validation_on_login(env):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "nope", "password": PW}).status_code == 422
    assert c.post("/api/auth/login", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert count(env, db.User) == 0


def test_rate_limit_after_repeated_failures(env):
    sign_in("a@example.com")
    c = TestClient(app)
    wrong = {"email": "a@example.com", "password": "not the password"}
    assert [c.post("/api/auth/login", json=wrong).status_code for _ in range(5)] == [401] * 5
    blocked = c.post("/api/auth/login", json=wrong)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    assert c.post("/api/auth/login", json={"email": "a@example.com", "password": PW}).status_code == 429
    other = c.post("/api/auth/login", json={"email": "b@example.com", "password": PW})
    assert other.status_code == 201  # only the failing email is blocked


@pytest.mark.parametrize("method,url", [
    ("get", "/api/auth/me"), ("delete", "/api/account"), ("get", "/api/profile"), ("put", "/api/profile"),
    ("get", "/api/allergies"), ("post", "/api/allergies"), ("put", "/api/allergies/1"), ("delete", "/api/allergies/1"),
    ("get", "/api/conditions"), ("post", "/api/conditions"), ("put", "/api/conditions/1"), ("delete", "/api/conditions/1"),
    ("get", "/api/medicine-records"), ("post", "/api/medicine-records"),
    ("put", "/api/medicine-records/1"), ("delete", "/api/medicine-records/1"),
])
def test_protected_routes_need_a_session(env, method, url):
    r = getattr(TestClient(app), method)(url, **({"json": {}} if method in ("post", "put") else {}))
    assert r.status_code == 401


def test_logout_revokes_the_session_and_tampered_cookie_fails(env):
    c = sign_in("a@example.com")
    cookie = c.cookies.get(auth.COOKIE)
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401
    replay = TestClient(app)
    replay.cookies.set(auth.COOKIE, cookie)
    assert replay.get("/api/auth/me").status_code == 401  # server-side session is gone
    live = sign_in("a@example.com")
    token, _, sig = live.cookies.get(auth.COOKIE).partition(".")
    forged = TestClient(app)
    forged.cookies.set(auth.COOKIE, f"{token}.{'0' * len(sig)}")
    assert forged.get("/api/auth/me").status_code == 401


# ---- ownership isolation ----------------------------------------------------------------------
def test_user_cannot_read_or_change_another_users_rows(env):
    a, b = sign_in("a@example.com"), sign_in("b@example.com")
    ids = {url: a.post(url, json=body).json()["id"] for url, body in OWNED.items()}
    for url, body in OWNED.items():
        item = f"{url}/{ids[url]}"
        assert ids[url] not in [row["id"] for row in b.get(url).json()]
        hijack = {k: ("Hijack" if k in ("allergen", "name", "display_name") else v) for k, v in body.items()}
        assert b.put(item, json=hijack).status_code == 404
        assert b.delete(item).status_code == 404
    # A's rows are untouched
    assert "Pollenx" in [x["allergen"] for x in a.get("/api/allergies").json()]
    assert "Illone" in [x["name"] for x in a.get("/api/conditions").json()]
    assert "Typedrug" in [x["display_name"] for x in a.get("/api/medicine-records").json()]
    assert "Hijack" not in json.dumps([a.get(u).json() for u in OWNED])
    # B's own lists never contain A's custom rows
    mine = json.dumps([b.get(u).json() for u in OWNED])
    assert not any(w in mine for w in ("Pollenx", "Illone", "Typedrug", "Hijack"))


def test_profile_is_per_account_and_takes_no_id(env):
    a, b = sign_in("a@example.com"), sign_in("b@example.com")
    assert a.put("/api/profile", json={"name": "Person A", "height_cm": 170, "weight_kg": 70}).status_code == 200
    assert b.get("/api/profile").json()["name"] is None
    assert a.put("/api/profile", json={"name": "x", "user_id": 2}).status_code == 422  # unknown field refused


# ---- profile, allergies, conditions -----------------------------------------------------------
def test_profile_update_computes_age_and_bmi(env):
    c = sign_in()
    dob = date.today().replace(year=date.today().year - 30) - timedelta(days=1)
    r = c.put("/api/profile", json={"name": " Person A ", "date_of_birth": dob.isoformat(), "sex": "male",
                                    "height_cm": 170, "weight_kg": 70, "blood_group": "O+", "notes": ""})
    body = r.json()
    assert r.status_code == 200 and body["name"] == "Person A" and body["notes"] is None
    assert (body["age"], body["bmi"], body["blood_group"]) == (30, 24.2, "O+")
    assert c.get("/api/profile").json() == body


@pytest.mark.parametrize("patch", [{"height_cm": 500}, {"height_cm": 10}, {"weight_kg": 1}, {"weight_kg": 900},
                                   {"sex": "robot"}, {"blood_group": "Z+"}, {"date_of_birth": "1800-01-01"},
                                   {"date_of_birth": (date.today() + timedelta(days=1)).isoformat()}])
def test_profile_ranges_are_validated(env, patch):
    assert sign_in().put("/api/profile", json=patch).status_code == 422


def test_allergy_crud(env):
    c = sign_in()
    made = c.post("/api/allergies", json={"allergen": "Pollenx", "reaction": "Rash after spring walks", "severity": "severe"})
    assert made.status_code == 201
    i = made.json()["id"]
    assert c.put(f"/api/allergies/{i}", json={"allergen": "Pollenx", "severity": "mild"}).json()["severity"] == "mild"
    assert c.post("/api/allergies", json={"allergen": "  "}).status_code == 422
    assert c.post("/api/allergies", json={"allergen": "x", "severity": "huge"}).status_code == 422
    assert c.delete(f"/api/allergies/{i}").status_code == 204
    assert c.delete(f"/api/allergies/{i}").status_code == 404


def test_condition_rules(env):
    c = sign_in()
    ok = c.post("/api/conditions", json={"name": "Fluone", "kind": "illness", "status": "past", "onset_date": "2025-01-01",
                                        "resolved_date": "2025-01-10", "outcome": "cured"})
    assert ok.status_code == 201 and ok.json()["outcome"] == "cured"
    base = {"name": "Illtwo", "kind": "illness"}
    assert c.post("/api/conditions", json={**base, "status": "current", "resolved_date": "2025-01-10"}).status_code == 422
    assert c.post("/api/conditions", json={**base, "status": "past", "onset_date": "2025-02-01",
                                           "resolved_date": "2025-01-01"}).status_code == 422
    assert c.post("/api/conditions", json={**base, "status": "current", "outcome": "cured"}).status_code == 422
    assert [x["name"] for x in c.get("/api/conditions?status=past").json()] == ["Fluone"]
    assert "Fluone" not in [x["name"] for x in c.get("/api/conditions?status=current").json()]


# ---- medicine records -------------------------------------------------------------------------
def test_medicine_course_status_over_the_api(env):
    c = sign_in()
    today = date.today()

    def add(**kw):
        return c.post("/api/medicine-records", json={"display_name": "Typedrug", **{k: str(v) for k, v in kw.items()}}).json()

    ongoing = add(start_date=today - timedelta(days=9))
    ended = add(start_date=today - timedelta(days=20), end_date=today - timedelta(days=1), outcome="improved")
    ends_today = add(start_date=today - timedelta(days=2), end_date=today)
    later = add(start_date=today + timedelta(days=3), end_date=today + timedelta(days=5))
    undated = add()
    assert (ongoing["status"], ongoing["duration_days"], ongoing["end_date"]) == ("current", 10, None)
    assert (ended["status"], ended["duration_days"], ended["outcome"]) == ("past", 20, "improved")
    assert ends_today["status"] == "current" and ends_today["duration_days"] == 3
    assert (later["status"], later["duration_days"]) == ("upcoming", 3)
    assert (undated["status"], undated["duration_days"]) == ("not_stated", None)


def test_medicine_course_validation(env):
    c = sign_in()
    post = lambda **kw: c.post("/api/medicine-records", json={"display_name": "Typedrug", **kw}).status_code
    assert post(start_date="2026-02-01", end_date="2026-01-01") == 422
    assert post(end_date="2026-01-01") == 422
    assert post(outcome="wonderful") == 422
    assert post(display_name="") == 422


def test_catalogue_pick_takes_name_and_ingredients_from_the_catalogue(env):
    c = sign_in()
    cat = catalogue_service.get_catalogue(env)
    expected = list(cat.row(cat.by_id["5"])["ingredients"])
    r = c.post("/api/medicine-records", json={"catalogue_id": "5", "display_name": "Client chosen name"})
    body = r.json()
    assert r.status_code == 201 and body["display_name"] == "Metfo 500 Tablet"
    assert body["ingredients"] == expected and body["catalogue_id"] == "5" and expected
    assert c.post("/api/medicine-records", json={"catalogue_id": "no-such-id", "display_name": "x"}).status_code == 404
    typed = c.post("/api/medicine-records", json={"display_name": "Typedrug"}).json()
    assert typed["ingredients"] == [] and typed["catalogue_id"] is None  # nothing invented for typed names
    upd = c.put(f"/api/medicine-records/{typed['id']}", json={"catalogue_id": "5", "display_name": "ignored"}).json()
    assert upd["display_name"] == "Metfo 500 Tablet" and upd["ingredients"] == expected


def test_catalogue_pick_when_catalogue_missing_is_refused(env):
    c = sign_in()
    (env.artifacts_dir / "catalogue.json").unlink()
    catalogue_service.clear_cache()
    assert c.post("/api/medicine-records", json={"catalogue_id": "5", "display_name": "x"}).status_code == 503
    assert c.post("/api/medicine-records", json={"display_name": "Typedrug"}).status_code == 201


# ---- deletes ----------------------------------------------------------------------------------
def test_deleting_an_item_removes_only_that_row(env):
    c = sign_in()
    keep = c.post("/api/allergies", json={"allergen": "Keepone"}).json()["id"]
    drop = c.post("/api/allergies", json={"allergen": "Dropone"}).json()["id"]
    assert c.delete(f"/api/allergies/{drop}").status_code == 204
    assert [x["id"] for x in c.get("/api/allergies").json()] == [keep]
    assert count(env, db.Profile) == 1 and count(env, db.Condition) == 1  # pre-filled rows remain


def test_account_deletion_removes_every_row_and_nothing_else(env):
    a, b = sign_in("a@example.com"), sign_in("b@example.com")
    for url, body in OWNED.items():
        a.post(url, json=body)
        b.post(url, json=body)
    uid_a, uid_b = user_id(env, "a@example.com"), user_id(env, "b@example.com")
    assert all(count(env, t, user_id=uid_a) > 0 for t in TABLES[1:])
    before_b = {t.__tablename__: count(env, t, user_id=uid_b) for t in TABLES[1:]}

    r = a.delete("/api/account")
    assert r.status_code == 204
    assert a.get("/api/auth/me").status_code == 401
    assert count(env, db.User, id=uid_a) == 0
    assert all(count(env, t, user_id=uid_a) == 0 for t in TABLES[1:])
    assert {t.__tablename__: count(env, t, user_id=uid_b) for t in TABLES[1:]} == before_b
    assert b.get("/api/auth/me").status_code == 200
    # the email is free again and starts from fresh starting details
    again = TestClient(app).post("/api/auth/login", json={"email": "a@example.com", "password": "another password"})
    assert again.status_code == 201
