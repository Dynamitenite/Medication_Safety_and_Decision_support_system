# SOURCE: NOT IN PAPERS. Glue for the three grounded-answer features (see medsafe/answer.py). Only label
# text, ingredient names and the user's question are put into a prompt; the signed-in user's profile is never
# read here. Any failure of the hosted model becomes a not_ready response; no request body is logged.
"""POST /api/answer/ask, /simplify, /explain-finding and GET /api/answer/status."""
from __future__ import annotations

from fastapi import HTTPException

from medsafe import answer as A
from medsafe import llm

from ..config import Settings
from ..schemas import (AnswerSource, AnswerStatusResponse, AskRequest, AskResponse, ExplainFindingRequest,
                       ExplainFindingResponse, SearchLabelsRequest, SimplifyRequest, SimplifyResponse)
from . import catalogue, intake, retrieval

ASK_K = 5
ALT_SHOWN = 5  # same count as the Alternatives page shows before "Show all"
ASK_MAX_TOKENS = 400
SIMPLIFY_MAX_TOKENS = 1200
FINDING_MAX_TOKENS = 300
# Sections that may be rewritten: why it is taken, and the instruction sections. Boxed warnings stay verbatim.
SIMPLIFIABLE = {"indications", "dosage_administration", "patient_counseling", "patient_information", "instructions_for_use"}


def _down(cls, e: llm.LLMUnavailable, **kw):
    return cls(status="not_ready", reason=e.reason, fix=e.fix, retry_after=e.retry_after, **kw)


def _ready_provider() -> llm.LLMProvider:
    """The configured provider, or LLMUnavailable. Checked before any retrieval so a missing key costs nothing."""
    p = llm.get_provider()
    if not p.is_configured():
        raise llm.LLMUnavailable("no_key", "The AI service is not set up: no API key is configured on the server.", llm.NO_KEY_FIX)
    return p


def status() -> AnswerStatusResponse:
    s = llm.status()
    return AnswerStatusResponse(status="ready" if s["ready"] else "not_ready", reason=s["reason"], fix=s["fix"],
                                provider=s["provider"], model=s["model"], requests_per_minute=llm._rpm())


# ---- ask ------------------------------------------------------------------------------------------
def _alternatives_answer(settings: Settings, body: AskRequest) -> AskResponse:
    """Price and alternatives questions: the Alternatives service's own list, no model, no provider call."""
    a = catalogue.alternatives(settings, body.medicine_id, False, 100)
    if a.status == "not_ready":
        return AskResponse(status="not_ready", reason=a.reason, fix=a.fix)
    return AskResponse(status="ready", kind="alternatives", alt_note=a.note, alt_form_family=a.form_family,
                       alt_total=a.same_total, alternatives=a.same[:ALT_SHOWN])


def ask(settings: Settings, body: AskRequest) -> AskResponse:
    if A.is_price_question(body.question):
        return _alternatives_answer(settings, body)
    try:
        prov = _ready_provider()
    except llm.LLMUnavailable as e:
        return _down(AskResponse, e)
    res = retrieval.search_labels(settings, SearchLabelsRequest(query=body.question, medicine_id=body.medicine_id,
                                                                k=ASK_K, scope=body.scope))
    if res.status == "not_ready":
        return AskResponse(status="not_ready", reason=res.reason, fix=res.fix)
    dosage = A.is_dosage_question(body.question)
    # wrong-form guard: instruction sections of another form or product are already withheld by the search;
    # for a dosage question no passage with any form or product mismatch is used at all
    usable = [r for r in res.results if r.text and not r.withheld and not (dosage and r.mismatch_note)]
    if not usable:
        why = ("No passage from a label of the same form and ingredients was found for a dosage question."
               if dosage and res.results else "No label passage was retrieved for this question.")
        return AskResponse(status="ready", answer=A.NOT_FOUND, not_found=True, note=why, provider=prov.name, model=prov.model)
    passages = [A.Passage(r.chunk_id, r.section_label, r.text) for r in usable]
    system, user = A.ask_prompt(body.question, passages)
    try:
        out = llm.generate(system, user, temperature=0, max_output_tokens=ASK_MAX_TOKENS)
    except llm.LLMUnavailable as e:
        return _down(AskResponse, e, provider=prov.name, model=prov.model)
    v = A.verify_citations(out.text, {p.chunk_id for p in passages})
    sources = [AnswerSource(chunk_id=r.chunk_id, section_label=r.section_label, product=r.product, set_id=r.set_id,
                            text=r.text, cited=r.chunk_id in v.cited) for r in usable]
    note = None
    if v.not_found and v.dropped:
        note = "The model's answer cited passages that were not supplied, so it was removed."
    elif v.dropped:
        note = f"{len(v.dropped)} sentence(s) were removed because they cited a passage that was not supplied."
    return AskResponse(status="ready", answer=v.text, not_found=v.not_found, note=note, citations=v.cited, sources=sources,
                       dropped_sentences=len(v.dropped), uncited_sentences=v.uncited, provider=out.provider, model=out.model)


# ---- simplify -------------------------------------------------------------------------------------
def simplify(settings: Settings, body: SimplifyRequest) -> SimplifyResponse:
    if body.section_key not in SIMPLIFIABLE:
        raise HTTPException(422, "This section cannot be rewritten.")
    try:
        prov = _ready_provider()
    except llm.LLMUnavailable as e:
        return _down(SimplifyResponse, e)
    d = intake.details(settings, body.medicine_id)
    if d.status == "not_ready":
        return SimplifyResponse(status="not_ready", reason=d.reason, fix=d.fix)
    if body.ingredient_index >= len(d.ingredients):
        raise HTTPException(404, "No such ingredient.")
    g = d.ingredients[body.ingredient_index]
    sec = g.indications if body.section_key == "indications" else next((s for s in g.instructions if s.key == body.section_key), None)
    if sec is None:
        raise HTTPException(404, "This label has no such section.")
    system, user = A.simplify_prompt(sec.label, sec.text)
    try:
        out = llm.generate(system, user, temperature=0, max_output_tokens=SIMPLIFY_MAX_TOKENS)
    except llm.LLMUnavailable as e:
        return _down(SimplifyResponse, e, provider=prov.name, model=prov.model)
    bad = A.unmatched_numbers(sec.text, out.text)
    return SimplifyResponse(status="ready", section_label=sec.label, original=sec.text, simplified=out.text,
                            flagged=bool(bad), unmatched=bad, provider=out.provider, model=out.model)


# ---- explain a finding ----------------------------------------------------------------------------
def explain_finding(body: ExplainFindingRequest) -> ExplainFindingResponse:
    try:
        prov = _ready_provider()
    except llm.LLMUnavailable as e:
        return _down(ExplainFindingResponse, e)
    system, user = A.finding_prompt(body.kind, body.a, body.b, body.explanation, body.sentences, body.predicted_class)
    try:
        out = llm.generate(system, user, temperature=0, max_output_tokens=FINDING_MAX_TOKENS)
    except llm.LLMUnavailable as e:
        return _down(ExplainFindingResponse, e, provider=prov.name, model=prov.model)
    if A.makes_safety_claim(out.text):
        return ExplainFindingResponse(status="not_ready", provider=out.provider, model=out.model,
                                      reason="The generated explanation made a claim about safety that this app does not allow, so it was dropped.",
                                      fix="Read the rule explanation and the label sentences above, and ask your doctor or pharmacist.")
    source = " ".join([body.a, body.b, body.explanation or "", *body.sentences])
    bad = A.unmatched_numbers(source, out.text)
    return ExplainFindingResponse(status="ready", level=body.level, text=A.with_doctor_line(out.text, body.level),
                                  flagged=bool(bad), unmatched=bad, provider=out.provider, model=out.model)
