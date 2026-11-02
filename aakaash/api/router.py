# SOURCE: NOT IN PAPERS. One router so the team can `app.include_router(router)` later.
"""All of Aakaash's endpoints, under the /api prefix."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from .config import Settings, get_settings
from .schemas import (AlternativesResponse, CheckerRequest, CheckerResponse, MedicineResponse,
                      SuggestResponse, DDIExamplesResponse, DDILabel, DDIStatsResponse, DailyMedStatsResponse,
                      Health, StatusResponse, TacStatsResponse, TraceResponse)
from .services import datasets, medicines, status, trace

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


@router.get("/trace", response_model=TraceResponse)
def get_trace(settings: Settings = Depends(get_settings)) -> TraceResponse:
    return trace.get_trace(settings)


@router.get("/medicine/suggest", response_model=SuggestResponse)
def medicine_suggest(q: str = Query("", max_length=100), limit: int = Query(8, ge=1, le=25),
                     settings: Settings = Depends(get_settings)) -> SuggestResponse:
    return medicines.suggest(settings, q, limit)


@router.get("/medicine/{set_id}", response_model=MedicineResponse)
def medicine_label(set_id: str, settings: Settings = Depends(get_settings)) -> MedicineResponse:
    return medicines.medicine(settings, set_id)


@router.get("/medicine/{set_id}/alternatives", response_model=AlternativesResponse)
def medicine_alternatives(set_id: str, settings: Settings = Depends(get_settings)) -> AlternativesResponse:
    return medicines.alternatives(settings, set_id)


@router.post("/checker", response_model=CheckerResponse)
def checker(body: CheckerRequest, settings: Settings = Depends(get_settings)) -> CheckerResponse:
    return medicines.check(settings, body.set_ids)
