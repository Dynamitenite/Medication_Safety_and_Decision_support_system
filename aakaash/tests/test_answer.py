# SOURCE: NOT IN PAPERS. FIXTURES ONLY: hand-written passages, a fake provider and httpx.MockTransport. No
# network call is made and no real key is used; "SECRET-KEY-VALUE-123" below is a made-up string whose only
# job is to prove that the key never appears in a response, an exception or a log line.
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from api import auth, db
from api.app import app
from api.config import Settings, get_settings
from api.services import answer as answer_service, catalogue as catalogue_service, medicines
from medsafe import answer as A, index as index_mod, llm

from fixtures_catalogue import LABELS, ROWS, write_artifacts
from fixtures_index import write_index

PW = "correct horse battery"
KEY = "SECRET-KEY-VALUE-123"
PARSED = {sid: {"set_id": sid, "sections": {
    "indications": [{"text": "Indicated for fixture pain. Second sentence."}],
    "dosage_administration": [{"text": "Take 2 tablets every 6 hours. Do not exceed 8 tablets in 24 hours."}]}}
    for sid in ("L-apap-1", "L-apap-2", "L-apap-inj", "L-warf", "L-metf", "L-albut", "L-nacl", "L-cacl", "L-kcl", "L-combo")}


class FakeProvider(llm.LLMProvider):
    name, model = "fake", "fake-1"

    def __init__(self, reply="", error=None):
        self.reply, self.error, self.calls = reply, error, []

    def is_configured(self):
        return True

    def generate(self, system, user, *, temperature=0, max_output_tokens=512):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return llm.LLMResult(text=self.reply, provider=self.name, model=self.model, usage={})


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-anywhere-else")
    s = Settings(data_dir=tmp_path / "data", artifacts_dir=tmp_path / "art", trace_path=tmp_path / "t.md",
                 encoder_name="tfidf", classifier_name="x")
    write_artifacts(s.artifacts_dir, ROWS, LABELS)
    write_index(s.artifacts_dir, LABELS)
    monkeypatch.setattr(medicines, "load_label", lambda _s, _i, sid: PARSED[sid])
    app.dependency_overrides[get_settings] = lambda: s
    catalogue_service.clear_cache()
    medicines.clear_cache()
    index_mod.clear_cache()
    auth.reset_rate_limit()
    llm.reset()
    yield s
    app.dependency_overrides.clear()
    catalogue_service.clear_cache()
    medicines.clear_cache()
    index_mod.clear_cache()
    llm.reset()
    db.dispose_all()


def signed_in():
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": "a@example.com", "password": PW}).status_code in (200, 201)
    return c


def use(monkeypatch, provider):
    monkeypatch.setattr(llm, "get_provider", lambda: provider)
    return provider


# ---- citation verifier ------------------------------------------------------------------------------
def test_verifier_drops_sentence_with_unknown_id():
    v = A.verify_citations("It treats pain [c1]. It cures everything [zzz]. Take with water [c1, c2].", {"c1", "c2"})
    assert v.text == "It treats pain [c1]. Take with water [c1, c2]."
    assert v.dropped == ["It cures everything [zzz]."] and v.cited == ["c1", "c2"] and not v.not_found


def test_verifier_citation_after_the_full_stop_and_numeric_ids():
    v = A.verify_citations("It treats pain. [c1]\nIt is a tablet [1].", {"c1"})
    assert v.text == "It treats pain. [c1]" and v.dropped == ["It is a tablet [1]."]


def test_verifier_answer_with_only_unknown_ids_becomes_not_found():
    v = A.verify_citations("Invented fact [nope].", {"c1"})
    assert v.not_found and v.text == A.NOT_FOUND and v.dropped


def test_verifier_counts_uncited_sentences_and_exact_not_found():
    assert A.verify_citations("Fact one [c1]. Fact two.", {"c1"}).uncited == 1
    v = A.verify_citations("Not found in the retrieved label text.", {"c1"})
    assert v.not_found and v.text == "Not found in the retrieved label text." and v.cited == []


# ---- numbers and units ------------------------------------------------------------------------------
def test_numbers_and_units_consistency():
    src = "Take 2 tablets every 6 hours. Do not exceed 8 tablets (1,000 mg) in 24 hours."
    assert A.unmatched_numbers(src, "Take two tablets about every 6 hours; at most 8 tablets or 1000 mg a day (24 hours).") == []
    assert A.unmatched_numbers(src, "Take 3 tablets every 6 hours.") == ["3 tablet"]
    assert A.unmatched_numbers(src, "Take 6 mg every 6 hours.") == ["6 mg"]  # the number exists, with another unit
    assert A.unmatched_numbers(src, "Stop after 7 days.") == ["7 day"]


# ---- other guards -----------------------------------------------------------------------------------
def test_doctor_line_added_once_for_critical_and_high_not_medium():
    assert A.with_doctor_line("It may matter.", "Critical") == "It may matter. Talk to your doctor or pharmacist."
    assert A.with_doctor_line("It may matter. Talk to your doctor or pharmacist", "High").count("Talk to your doctor") == 1
    assert A.with_doctor_line("It may matter.", "Medium") == "It may matter."


def test_safety_claims_are_detected():
    assert all(A.makes_safety_claim(t) for t in ("This combination is safe.", "There is no risk.", "It is harmless."))
    assert not A.makes_safety_claim("This may not be safe; ask a doctor.")


# ---- provider: retries, limiter, key hygiene --------------------------------------------------------
def gemini(handler, **kw):
    sleeps = []
    p = llm.GeminiProvider(KEY, "m-1", client=httpx.Client(transport=httpx.MockTransport(handler)),
                           sleep=sleeps.append, **kw)
    return p, sleeps


OK = {"candidates": [{"content": {"parts": [{"text": "Hello."}]}, "finishReason": "STOP"}],
      "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1, "totalTokenCount": 4}}


def test_gemini_request_shape_and_result():
    seen = {}

    def h(req):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return httpx.Response(200, json=OK)

    p, _ = gemini(h)
    r = p.generate("SYS", "USER", temperature=0, max_output_tokens=50)
    assert seen["url"].endswith("/v1beta/models/m-1:generateContent") and KEY not in seen["url"] and seen["key"] == KEY
    assert seen["body"] == {"systemInstruction": {"parts": [{"text": "SYS"}]},
                            "contents": [{"role": "user", "parts": [{"text": "USER"}]}],
                            "generationConfig": {"temperature": 0, "maxOutputTokens": 50}}
    assert (r.text, r.provider, r.model) == ("Hello.", "gemini", "m-1") and r.usage["totalTokenCount"] == 4


def test_gemini_retries_429_then_gives_up_with_rate_limited():
    calls = []

    def h(req):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": f"quota for {KEY}"}})

    p, sleeps = gemini(h)
    with pytest.raises(llm.LLMUnavailable) as e:
        p.generate("s", "u")
    assert len(calls) == 3 and len(sleeps) == 2 and e.value.kind == "rate_limited"
    assert "rate limited" in e.value.reason and "Try again in" in e.value.reason and KEY not in repr(e.value.__dict__)


def test_gemini_retries_5xx_then_succeeds():
    codes = iter([503, 500, 200])
    p, sleeps = gemini(lambda req: (lambda c: httpx.Response(c, json=OK if c == 200 else {}))(next(codes)))
    assert p.generate("s", "u").text == "Hello." and len(sleeps) == 2


def test_gemini_long_retry_after_is_reported_not_slept():
    p, sleeps = gemini(lambda req: httpx.Response(429, headers={"retry-after": "45"}, json={}))
    with pytest.raises(llm.LLMUnavailable) as e:
        p.generate("s", "u")
    assert e.value.retry_after == 45 and "45 seconds" in e.value.reason and sleeps == []


def test_gemini_timeout_and_bad_key_and_400_are_unavailable():
    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)

    p, _ = gemini(boom)
    with pytest.raises(llm.LLMUnavailable) as e:
        p.generate("s", "u")
    assert e.value.kind == "timeout"
    p, _ = gemini(lambda req: httpx.Response(403, json={"error": {"message": "denied"}}))
    with pytest.raises(llm.LLMUnavailable) as e:
        p.generate("s", "u")
    assert e.value.kind == "bad_key"


def test_gemini_drops_temperature_when_the_model_rejects_it():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content)["generationConfig"])
        return httpx.Response(400, json={"error": {"message": "temperature is not supported"}}) if len(bodies) == 1 else httpx.Response(200, json=OK)

    p, _ = gemini(h)
    assert p.generate("s", "u").text == "Hello." and "temperature" in bodies[0] and "temperature" not in bodies[1]


def test_limiter_blocks_over_the_rpm_without_sleeping():
    t = [0.0]
    lim = llm.RateLimiter(2, clock=lambda: t[0])
    lim.acquire()
    lim.acquire()
    with pytest.raises(llm.LLMUnavailable) as e:
        lim.acquire()
    assert e.value.kind == "rate_limited" and e.value.retry_after == 60
    t[0] = 61.0
    lim.acquire()


def test_unset_key_gives_not_ready_everywhere(env, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    s = TestClient(app).get("/api/answer/status").json()
    assert s["status"] == "not_ready" and s["provider"] == "gemini" and s["model"] == "gemini-3.5-flash-lite" and "LLM_API_KEY" in s["fix"]
    c = signed_in()
    for path, body in (("ask", {"medicine_id": "1", "question": "pain?"}),
                       ("simplify", {"medicine_id": "1", "ingredient_index": 0, "section_key": "indications"}),
                       ("explain-finding", {"kind": "pair", "a": "x", "b": "y", "level": "High"})):
        r = c.post(f"/api/answer/{path}", json=body).json()
        assert r["status"] == "not_ready" and r["reason"] and r["fix"], path
        assert not r.get("answer") and not r.get("simplified") and not r.get("text")


def test_endpoints_need_sign_in(env):
    assert TestClient(app).post("/api/answer/ask", json={"medicine_id": "1", "question": "x"}).status_code == 401
    assert TestClient(app).get("/api/answer/status").status_code == 200


def test_rate_limit_through_the_api_is_not_ready_with_seconds(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    use(monkeypatch, FakeProvider(error=llm.rate_limited(17)))
    r = signed_in().post("/api/answer/ask", json={"medicine_id": "1", "question": "what is it for pain"}).json()
    assert r["status"] == "not_ready" and r["retry_after"] == 17 and "17 seconds" in r["reason"] and r["answer"] is None


def test_key_never_appears_in_responses_logs_or_errors(env, monkeypatch, caplog):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    caplog.set_level(logging.DEBUG)
    llm.reset()
    handler = lambda req: httpx.Response(500, json={"error": {"message": f"boom {KEY}"}})
    prov = llm.GeminiProvider(KEY, "m-1", client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    monkeypatch.setattr(llm, "get_provider", lambda: prov)
    c = signed_in()
    out = [c.get("/api/answer/status").text,
           c.post("/api/answer/ask", json={"medicine_id": "1", "question": "what is it for pain"}).text,
           c.post("/api/answer/simplify", json={"medicine_id": "1", "ingredient_index": 0, "section_key": "indications"}).text,
           c.post("/api/answer/explain-finding", json={"kind": "pair", "a": "x", "b": "y", "level": "High"}).text]
    assert not any(KEY in t for t in out) and KEY not in caplog.text
    assert llm.redact(f"x {KEY} y", KEY) == "x [key removed] y"
    with pytest.raises(llm.LLMUnavailable) as e:
        prov.generate("s", "u")
    assert KEY not in str(e.value) + e.value.reason + e.value.fix


# ---- features with a fake provider: exact payloads, no profile fields -------------------------------
def fill_profile(c):
    assert c.put("/api/profile", json={"name": "Zelda Quillfeather", "date_of_birth": "1980-02-03", "notes": "PROFILENOTE"}).status_code == 200
    assert c.post("/api/allergies", json={"allergen": "Zorbium", "reaction": "ALLERGYREACTION"}).status_code == 201
    assert c.post("/api/medicine-records", json={"display_name": "CURRENTMEDNAME"}).status_code == 201
    PROFILE = ("Zelda", "Quillfeather", "1980", "PROFILENOTE", "Zorbium", "ALLERGYREACTION", "CURRENTMEDNAME", "a@example.com")
    return PROFILE


def test_ask_payload_is_exact_and_has_no_profile_fields(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    c = signed_in()
    profile = fill_profile(c)
    res = c.post("/api/search/labels", json={"query": "pain and fever", "medicine_id": "1", "k": 5}).json()
    ids = [r["chunk_id"] for r in res["results"]]
    assert ids
    fake = use(monkeypatch, FakeProvider(reply=f"It is used for pain and fever [{ids[0]}]. Made up [bogus]."))
    r = c.post("/api/answer/ask", json={"medicine_id": "1", "question": "pain and fever"}).json()
    assert r["status"] == "ready" and r["citations"] == [ids[0]] and r["dropped_sentences"] == 1 and "bogus" not in r["answer"]
    assert [s["chunk_id"] for s in r["sources"] if s["cited"]] == [ids[0]]
    system, user = fake.calls[0]
    expect_body = "\n\n".join(f"[{x['chunk_id']}] ({x['section_label']})\n{x['text']}" for x in res["results"] if x["text"])
    assert user == f"Question: pain and fever\n\nLabel passages:\n\n{expect_body}"
    assert system == A.ASK_SYSTEM
    assert not any(p.lower() in (system + user).lower() for p in profile)


def test_ask_not_found_paths(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    c = signed_in()
    use(monkeypatch, FakeProvider(reply="Not found in the retrieved label text."))
    r = c.post("/api/answer/ask", json={"medicine_id": "1", "question": "pain and fever"}).json()
    assert r["status"] == "ready" and r["not_found"] and r["answer"] == "Not found in the retrieved label text." and r["citations"] == []
    # nothing usable retrieved (an injection label for a dosage question on a tablet is withheld): no model call
    fake = use(monkeypatch, FakeProvider(reply="should not be called"))
    r = c.post("/api/answer/ask", json={"medicine_id": "12", "question": "what dose should I take?"}).json()
    assert r["status"] == "ready" and r["not_found"] and r["answer"] == A.NOT_FOUND and fake.calls == []


def test_dosage_question_never_sends_a_wrong_form_passage(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    c = signed_in()
    fake = use(monkeypatch, FakeProvider(reply="Not found in the retrieved label text."))
    c.post("/api/answer/ask", json={"medicine_id": "1", "question": "what is the dose every six hours", "scope": "all"})
    sent = fake.calls[0][1] if fake.calls else ""
    assert "intravenous" not in sent and "L-apap-inj" not in sent


def test_simplify_sends_only_the_section_and_flags_changed_numbers(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    c = signed_in()
    profile = fill_profile(c)
    fake = use(monkeypatch, FakeProvider(reply="Take 2 tablets every 6 hours. Never take more than 9 tablets in a day."))
    r = c.post("/api/answer/simplify", json={"medicine_id": "1", "ingredient_index": 0, "section_key": "dosage_administration"}).json()
    assert r["status"] == "ready" and r["original"] == PARSED["L-apap-1"]["sections"]["dosage_administration"][0]["text"]
    assert r["flagged"] and r["unmatched"] == ["9 tablet"]
    system, user = fake.calls[0]
    assert user == "Label section: Dosage and administration\n\nText:\n" + r["original"] and system == A.SIMPLIFY_SYSTEM
    assert not any(p.lower() in (system + user).lower() for p in profile)
    assert c.post("/api/answer/simplify", json={"medicine_id": "1", "ingredient_index": 0, "section_key": "boxed_warning"}).status_code == 422


def test_simplify_consistent_numbers_not_flagged(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    use(monkeypatch, FakeProvider(reply="Take 2 tablets every 6 hours. Do not take more than 8 tablets in 24 hours."))
    r = signed_in().post("/api/answer/simplify", json={"medicine_id": "1", "ingredient_index": 0, "section_key": "dosage_administration"}).json()
    assert r["status"] == "ready" and not r["flagged"] and r["unmatched"] == []


def test_explain_finding_payload_exact_and_level_never_changes(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    c = signed_in()
    profile = fill_profile(c)
    fake = use(monkeypatch, FakeProvider(reply="Together they may raise bleeding risk. Level is now Medium."))
    body = {"kind": "pair", "a": "Warfarin", "b": "Aspirin", "level": "Critical", "explanation": "Both can cause bleeding.",
            "sentences": ["Aspirin may increase the anticoagulant effect of warfarin."], "predicted_class": "effect",
            "patient_name": "Zelda Quillfeather", "allergies": ["Zorbium"]}  # extra fields must be ignored
    r = c.post("/api/answer/explain-finding", json=body).json()
    assert r["status"] == "ready" and r["level"] == "Critical"
    assert r["text"].endswith("Talk to your doctor or pharmacist.") and r["text"].count("Talk to your doctor") == 1
    system, user = fake.calls[0]
    assert user == ("Two ingredients: Warfarin and Aspirin.\nExplanation from the interaction rules: Both can cause bleeding.\n"
                    "Label sentence 1: Aspirin may increase the anticoagulant effect of warfarin.\n"
                    "Model estimate of the interaction type (not a risk level): effect")
    assert "Critical" not in user and not any(p.lower() in (system + user).lower() for p in profile)
    for level in ("Medium", "High"):
        r = c.post("/api/answer/explain-finding", json={**body, "level": level}).json()
        assert r["level"] == level and r["text"].endswith("pharmacist.") == (level != "Medium")


def test_explain_allergy_sends_only_allergen_and_ingredient(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    fake = use(monkeypatch, FakeProvider(reply="The medicine contains an ingredient related to the allergen."))
    r = signed_in().post("/api/answer/explain-finding", json={"kind": "allergy", "a": "Penicillin", "b": "Amoxicillin", "level": "High"}).json()
    assert r["status"] == "ready"
    assert fake.calls[0][1] == "Allergen: Penicillin. Ingredient in the medicine: Amoxicillin."


def test_explain_finding_that_claims_safety_is_withheld(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    use(monkeypatch, FakeProvider(reply="This combination is safe to take together."))
    r = signed_in().post("/api/answer/explain-finding", json={"kind": "pair", "a": "x", "b": "y", "level": "High"}).json()
    assert r["status"] == "not_ready" and r["text"] is None and "safety" in r["reason"]


def test_status_ready_when_key_set(env, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", KEY)
    monkeypatch.setenv("LLM_MODEL", "some-model")
    llm.reset()
    s = TestClient(app).get("/api/answer/status").json()
    assert s["status"] == "ready" and s["model"] == "some-model" and KEY not in json.dumps(s)
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    s = TestClient(app).get("/api/answer/status").json()
    assert s["status"] == "not_ready" and "unknown provider" in s["reason"]
