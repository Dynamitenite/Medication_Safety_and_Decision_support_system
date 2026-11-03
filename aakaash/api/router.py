# SOURCE: NOT IN PAPERS. One router so the team can `app.include_router(router)` later.
"""All of Aakaash's endpoints, under the /api prefix."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from . import auth
from .config import Settings, get_settings
from .db import User, get_db
from .schemas import (AddMedicinesRequest, AddMedicinesResponse, AnalyzeRequest, AnalyzeResponse,
                      MedicineDetailsResponse, AllergyIn, AllergyOut, AlternativesResponse, AppmsLookupResponse, AppmsPatientResponse,
                      AppmsPatientsResponse, AppmsSummaryResponse, BrandAlternativesResponse, BrandResponse,
                      CatalogueFormsResponse, CatalogueSummaryResponse, CheckerRequest, CheckerResponse, ConditionIn, ConditionOut,
                      ConditionStatus, LoginRequest, LoginResponse, MeResponse, MedicineRecordIn,
                      MedicineRecordOut, MedicineResponse, ProfileIn, ProfileOut, ProfileOverview,
                      SuggestResponse, DDIExamplesResponse, DDILabel, DDIStatsResponse, DailyMedStatsResponse,
                      Health, StatusResponse, TacStatsResponse, TraceResponse, DDIClassifyRequest,
                      DDIClassifyResponse, DDIMetricsResponse, IndexSummaryResponse, SearchLabelsRequest,
                      SearchLabelsResponse, SimilarUseResponse, AnswerStatusResponse, AskRequest, AskResponse,
                      ExplainFindingRequest, ExplainFindingResponse, SimplifyRequest, SimplifyResponse)
from .services import accounts, answer, appms, catalogue, datasets, ddi, intake, medicines, retrieval, similar_use, status, trace

router = APIRouter(prefix="/api")


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health()


@router.get("/status", response_model=StatusResponse)
def get_status(settings: Settings = Depends(get_settings)) -> StatusResponse:
    return status.get_status(settings)


@router.get("/datasets/ddi2013/stats", response_model=DDIStatsResponse)
def ddi_stats(settings: Settings = Depends(get_settings)) -> DDIStatsResponse:
    return datasets.ddi_stats(settings)


@router.get("/datasets/ddi2013/examples", response_model=DDIExamplesResponse)
def ddi_examples(split: Literal["train", "dev", "test"] | None = None,
                 label: DDILabel | None = None,
                 limit: int = Query(10, ge=1, le=100),
                 settings: Settings = Depends(get_settings)) -> DDIExamplesResponse:
    return datasets.ddi_examples(settings, split, label, limit)


@router.get("/datasets/dailymed/stats", response_model=DailyMedStatsResponse)
def dailymed_stats(settings: Settings = Depends(get_settings)) -> DailyMedStatsResponse:
    return datasets.dailymed_stats(settings)


@router.get("/datasets/tac2017/stats", response_model=TacStatsResponse)
def tac_stats(settings: Settings = Depends(get_settings)) -> TacStatsResponse:
    return datasets.tac_stats(settings)


@router.post("/ddi/classify", response_model=DDIClassifyResponse)
def ddi_classify(body: DDIClassifyRequest, settings: Settings = Depends(get_settings)) -> DDIClassifyResponse:
    """Interaction type of one sentence naming two drugs. A model estimate; it never sets a risk level."""
    return ddi.classify(settings, body)


@router.get("/ddi/metrics", response_model=DDIMetricsResponse)
def ddi_metrics(settings: Settings = Depends(get_settings)) -> DDIMetricsResponse:
    return ddi.metrics(settings)


@router.get("/trace", response_model=TraceResponse)
def get_trace(settings: Settings = Depends(get_settings)) -> TraceResponse:
    return trace.get_trace(settings)


@router.get("/medicine/suggest", response_model=SuggestResponse)
def medicine_suggest(q: str = Query("", max_length=100), limit: int = Query(8, ge=1, le=25),
                     settings: Settings = Depends(get_settings)) -> SuggestResponse:
    return catalogue.suggest(settings, q, limit)


@router.get("/medicine/{catalogue_id}", response_model=BrandResponse)
def medicine_brand(catalogue_id: str, settings: Settings = Depends(get_settings)) -> BrandResponse:
    return catalogue.brand(settings, catalogue_id)


@router.get("/medicine/{catalogue_id}/details", response_model=MedicineDetailsResponse)
def medicine_details(catalogue_id: str, user: User = Depends(auth.current_user),
                     settings: Settings = Depends(get_settings)) -> MedicineDetailsResponse:
    """Verbatim US label sections for each ingredient, chosen by the dosage-form rule. Dosage and
    instruction text is left out when the label's form or ingredients differ from the medicine's."""
    return intake.details(settings, catalogue_id)


@router.get("/medicine/{catalogue_id}/alternatives", response_model=BrandAlternativesResponse)
def medicine_alternatives(catalogue_id: str, include_discontinued: bool = False,
                          limit: int = Query(100, ge=1, le=1000),
                          settings: Settings = Depends(get_settings)) -> BrandAlternativesResponse:
    return catalogue.alternatives(settings, catalogue_id, include_discontinued, limit)


@router.get("/medicine/{catalogue_id}/similar-use", response_model=SimilarUseResponse)
def medicine_similar_use(catalogue_id: str, limit: int = Query(10, ge=1, le=25),
                         settings: Settings = Depends(get_settings)) -> SimilarUseResponse:
    """Other ingredients whose US-label Indications text is closest (cosine) to this medicine's. Not a
    list of substitutes. not_ready without the label index."""
    return similar_use.similar_use(settings, catalogue_id, limit)


@router.post("/search/labels", response_model=SearchLabelsResponse)
def search_labels(body: SearchLabelsRequest, settings: Settings = Depends(get_settings)) -> SearchLabelsResponse:
    """Top-k label passages by cosine similarity, optionally limited to one medicine's linked US labels."""
    return retrieval.search_labels(settings, body)


@router.get("/answer/status", response_model=AnswerStatusResponse)
def answer_status() -> AnswerStatusResponse:
    """Provider, model and whether the hosted LLM is set up. Never includes the key."""
    return answer.status()


@router.post("/answer/ask", response_model=AskResponse)
def answer_ask(body: AskRequest, user: User = Depends(auth.current_user),
               settings: Settings = Depends(get_settings)) -> AskResponse:
    """A plain-language answer from this medicine's label passages only, with [chunk_id] citations."""
    return answer.ask(settings, body)


@router.post("/answer/simplify", response_model=SimplifyResponse)
def answer_simplify(body: SimplifyRequest, user: User = Depends(auth.current_user),
                    settings: Settings = Depends(get_settings)) -> SimplifyResponse:
    """One verbatim details section rewritten in plain words. The original is returned beside it."""
    return answer.simplify(settings, body)


@router.post("/answer/explain-finding", response_model=ExplainFindingResponse)
def answer_explain_finding(body: ExplainFindingRequest, user: User = Depends(auth.current_user)) -> ExplainFindingResponse:
    """Plain-language reading of one finding from its rule text and label sentences. Never changes the level."""
    return answer.explain_finding(body)


@router.get("/index/summary", response_model=IndexSummaryResponse)
def index_summary(settings: Settings = Depends(get_settings)) -> IndexSummaryResponse:
    return retrieval.summary(settings)


@router.get("/catalogue/summary", response_model=CatalogueSummaryResponse)
def catalogue_summary(settings: Settings = Depends(get_settings)) -> CatalogueSummaryResponse:
    return catalogue.summary(settings)


@router.get("/catalogue/forms", response_model=CatalogueFormsResponse)
def catalogue_forms(settings: Settings = Depends(get_settings)) -> CatalogueFormsResponse:
    return catalogue.forms(settings)


@router.get("/label/{set_id}", response_model=MedicineResponse)
def label_text(set_id: str, settings: Settings = Depends(get_settings)) -> MedicineResponse:
    return medicines.medicine(settings, set_id)


@router.get("/label/{set_id}/alternatives", response_model=AlternativesResponse)
def label_alternatives(set_id: str, settings: Settings = Depends(get_settings)) -> AlternativesResponse:
    return medicines.alternatives(settings, set_id)


@router.post("/checker", response_model=CheckerResponse)
def checker(body: CheckerRequest, settings: Settings = Depends(get_settings)) -> CheckerResponse:
    return catalogue.check(settings, body.catalogue_ids, body.names)


@router.get("/appms/summary", response_model=AppmsSummaryResponse)
def appms_summary(settings: Settings = Depends(get_settings)) -> AppmsSummaryResponse:
    return appms.summary(settings)


@router.get("/appms/patients", response_model=AppmsPatientsResponse)
def appms_patients(limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
                   q: str = Query("", max_length=100),
                   settings: Settings = Depends(get_settings)) -> AppmsPatientsResponse:
    return appms.patients(settings, limit, offset, q)


@router.get("/appms/patients/{patient_id}", response_model=AppmsPatientResponse)
def appms_patient(patient_id: str, settings: Settings = Depends(get_settings)) -> AppmsPatientResponse:
    return appms.patient(settings, patient_id)


@router.get("/appms/lookup", response_model=AppmsLookupResponse)
def appms_lookup(drug_a: str = Query(..., min_length=1, max_length=100),
                 drug_b: str = Query(..., min_length=1, max_length=100),
                 settings: Settings = Depends(get_settings)) -> AppmsLookupResponse:
    return appms.lookup(settings, drug_a, drug_b)


# ---- accounts, profile and medical history ---------------------------------------------------
# Everything below needs a signed-in user and only ever reads or writes that user's own rows.
@router.post("/auth/login", response_model=LoginResponse)
def auth_login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings)) -> LoginResponse:
    """Sign in. An email that has no account yet gets one (status 201) with starting details filled in."""
    return accounts.login(db, settings, body, request, response)


@router.post("/auth/logout", status_code=204)
def auth_logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    auth.end_session(db, request, response)


@router.get("/auth/me", response_model=MeResponse)
def auth_me(user: User = Depends(auth.current_user)) -> MeResponse:
    return MeResponse(email=user.email, created_at=user.created_at)


@router.delete("/account", status_code=204)
def delete_account(response: Response, user: User = Depends(auth.current_user),
                   db: Session = Depends(get_db)) -> None:
    """Delete the account and every row that belongs to it."""
    accounts.delete_account(db, user, response)


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: User = Depends(auth.current_user), db: Session = Depends(get_db)) -> ProfileOut:
    return accounts.get_profile(db, user)


@router.put("/profile", response_model=ProfileOut)
def put_profile(body: ProfileIn, user: User = Depends(auth.current_user),
                db: Session = Depends(get_db)) -> ProfileOut:
    return accounts.put_profile(db, user, body)


@router.get("/profile/overview", response_model=ProfileOverview)
def profile_overview(user: User = Depends(auth.current_user), db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings)) -> ProfileOverview:
    """Read-only: counts and the highest rule level among the current medicines. Stores nothing."""
    return intake.overview(db, settings, user)


@router.get("/allergies", response_model=list[AllergyOut])
def list_allergies(user: User = Depends(auth.current_user), db: Session = Depends(get_db)) -> list[AllergyOut]:
    return accounts.list_allergies(db, user)


@router.post("/allergies", response_model=AllergyOut, status_code=201)
def create_allergy(body: AllergyIn, user: User = Depends(auth.current_user),
                   db: Session = Depends(get_db)) -> AllergyOut:
    return accounts.create_allergy(db, user, body)


@router.put("/allergies/{item_id}", response_model=AllergyOut)
def update_allergy(item_id: int, body: AllergyIn, user: User = Depends(auth.current_user),
                   db: Session = Depends(get_db)) -> AllergyOut:
    return accounts.update_allergy(db, user, item_id, body)


@router.delete("/allergies/{item_id}", status_code=204)
def delete_allergy(item_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)) -> None:
    accounts.delete_allergy(db, user, item_id)


@router.get("/conditions", response_model=list[ConditionOut])
def list_conditions(status: ConditionStatus | None = None, user: User = Depends(auth.current_user),
                    db: Session = Depends(get_db)) -> list[ConditionOut]:
    return accounts.list_conditions(db, user, status)


@router.post("/conditions", response_model=ConditionOut, status_code=201)
def create_condition(body: ConditionIn, user: User = Depends(auth.current_user),
                     db: Session = Depends(get_db)) -> ConditionOut:
    return accounts.create_condition(db, user, body)


@router.put("/conditions/{item_id}", response_model=ConditionOut)
def update_condition(item_id: int, body: ConditionIn, user: User = Depends(auth.current_user),
                     db: Session = Depends(get_db)) -> ConditionOut:
    return accounts.update_condition(db, user, item_id, body)


@router.delete("/conditions/{item_id}", status_code=204)
def delete_condition(item_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)) -> None:
    accounts.delete_condition(db, user, item_id)


@router.get("/medicine-records", response_model=list[MedicineRecordOut])
def list_medicine_records(user: User = Depends(auth.current_user),
                          db: Session = Depends(get_db)) -> list[MedicineRecordOut]:
    return accounts.list_medicines(db, user)


@router.post("/medicine-records", response_model=MedicineRecordOut, status_code=201)
def create_medicine_record(body: MedicineRecordIn, user: User = Depends(auth.current_user),
                           db: Session = Depends(get_db),
                           settings: Settings = Depends(get_settings)) -> MedicineRecordOut:
    return accounts.create_medicine(db, settings, user, body)


@router.put("/medicine-records/{item_id}", response_model=MedicineRecordOut)
def update_medicine_record(item_id: int, body: MedicineRecordIn, user: User = Depends(auth.current_user),
                           db: Session = Depends(get_db),
                           settings: Settings = Depends(get_settings)) -> MedicineRecordOut:
    return accounts.update_medicine(db, settings, user, item_id, body)


@router.post("/medicine-records/batch", response_model=AddMedicinesResponse, status_code=201)
def add_medicine_records(body: AddMedicinesRequest, user: User = Depends(auth.current_user),
                         db: Session = Depends(get_db),
                         settings: Settings = Depends(get_settings)) -> AddMedicinesResponse:
    """Add the confirmed "To add" list. The risk analysis runs again here; a Critical result needs
    acknowledged_warning=true (409 otherwise). Nothing else blocks adding."""
    return intake.add(db, settings, user, body)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(body: AnalyzeRequest, user: User = Depends(auth.current_user), db: Session = Depends(get_db),
            settings: Settings = Depends(get_settings)) -> AnalyzeResponse:
    """Risk analysis of new medicines against the user's current medicines and allergies, both read
    here on the server. Stores nothing."""
    return intake.analyze_request(db, settings, user, body)


@router.delete("/medicine-records/{item_id}", status_code=204)
def delete_medicine_record(item_id: int, user: User = Depends(auth.current_user),
                           db: Session = Depends(get_db)) -> None:
    accounts.delete_medicine(db, user, item_id)
