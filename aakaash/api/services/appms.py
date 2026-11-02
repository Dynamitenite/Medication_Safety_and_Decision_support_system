# SOURCE: NOT IN PAPERS. Serves the APPMS interaction rules from data/appms (medsafe/appms.py).
# Missing data gives status="not_ready"; nothing is invented. "No match" is never "safe".
"""Summary, sample patients and rule lookup."""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import HTTPException

from medsafe import appms
from medsafe.appms import AppmsData, AppmsMissing

from ..config import Settings
from ..schemas import (AppmsLookupResponse, AppmsMedication, AppmsPatient, AppmsPatientResponse,
                       AppmsPatientsResponse, AppmsRuleMatch, AppmsSeverityCount, AppmsSummaryResponse)

FIX = "extract the APPMS zip into data\\appms\\"
NOTE = "Not flagged means no rule matched. It does not mean the combination is safe."

_lock = threading.Lock()
_cache: dict[str, tuple[tuple, AppmsData]] = {}


def _folder(settings: Settings) -> Path:
    return settings.data_dir / "appms"


def _signature(folder: Path) -> tuple:
    return tuple((n, (folder / n).stat().st_mtime_ns) for n in appms.FILES.values())


def get_data(settings: Settings) -> AppmsData | None:
    """Parsed files, cached until a file changes. None if the folder or a file is missing."""
    folder = _folder(settings)
    if appms.missing_files(folder):
        return None
    sig = _signature(folder)
    with _lock:
        hit = _cache.get(str(folder))
        if hit and hit[0] == sig:
            return hit[1]
        try:
            data = appms.load(folder)
        except AppmsMissing:
            return None
        _cache[str(folder)] = (sig, data)
        return data


def _not_ready(cls, settings: Settings):
    gone = appms.missing_files(_folder(settings))
    where = settings.display(_folder(settings))
    reason = f"{where} is missing or incomplete ({', '.join(gone)})." if gone else "The interaction rules could not be read."
    return cls(status="not_ready", reason=reason, fix=FIX)


def summary(settings: Settings) -> AppmsSummaryResponse:
    d = get_data(settings)
    if d is None:
        return _not_ready(AppmsSummaryResponse, settings)
    flagged = [s for s in d.scenarios if s.flagged]
    ids = {p.patient_id for p in d.patients}
    return AppmsSummaryResponse(
        status="ready", patients=len(d.patients), medication_rows=len(d.medications),
        scenarios=len(d.scenarios), rules=len(d.rules), flagged_scenarios=len(flagged),
        not_flagged_scenarios=len(d.scenarios) - len(flagged),
        severity=[AppmsSeverityCount(severity=sev, scenarios=sum(1 for s in flagged if s.severity == sev))
                  for sev in appms.SEVERITIES],
        distinct_explanations=len({s.explanation for s in d.scenarios}),
        orphan_medication_rows=sum(1 for m in d.medications if m.patient_id not in ids), note=NOTE)


def _patient(p: appms.Patient) -> AppmsPatient:
    return AppmsPatient(**p.model_dump())


def patients(settings: Settings, limit: int, offset: int, q: str) -> AppmsPatientsResponse:
    d = get_data(settings)
    if d is None:
        return _not_ready(AppmsPatientsResponse, settings)
    needle = q.strip().lower()
    rows = d.patients
    if needle:
        def hit(p: appms.Patient) -> bool:
            text = " ".join(filter(None, (p.patient_id, p.state, p.district, p.primary_condition,
                                          p.secondary_condition, p.reported_drug_allergy))).lower()
            return needle in text or any(needle in m.drug_name.lower() for m in d.meds_by_patient.get(p.patient_id, []))
        rows = [p for p in rows if hit(p)]
    return AppmsPatientsResponse(status="ready", total=len(rows), limit=limit, offset=offset,
                                 patients=[_patient(p) for p in rows[offset:offset + limit]])


def patient(settings: Settings, patient_id: str) -> AppmsPatientResponse:
    d = get_data(settings)
    if d is None:
        return _not_ready(AppmsPatientResponse, settings)
    p = next((x for x in d.patients if x.patient_id == patient_id), None)
    if p is None:
        raise HTTPException(404, f"No sample patient with id {patient_id}.")
    meds = [AppmsMedication(**m.model_dump(exclude={"patient_id"})) for m in d.meds_by_patient.get(patient_id, [])]
    return AppmsPatientResponse(status="ready", patient=_patient(p), medications=meds)


def lookup(settings: Settings, drug_a: str, drug_b: str) -> AppmsLookupResponse:
    d = get_data(settings)
    if d is None:
        return _not_ready(AppmsLookupResponse, settings)
    r = appms.find_rule(d, drug_a, drug_b)
    if r is None:
        return AppmsLookupResponse(status="ready", drug_a=drug_a, drug_b=drug_b, matched=False,
                                   message=appms.NO_MATCH_TEXT)
    return AppmsLookupResponse(
        status="ready", drug_a=drug_a, drug_b=drug_b, matched=True,
        rule=AppmsRuleMatch(drug_a=r.drug_a, drug_b=r.drug_b, severity=r.severity,
                            interaction_category=r.interaction_category,
                            mechanism_or_risk=r.mechanism_or_risk, explanation=r.explanation_or_action,
                            evidence_source=r.evidence_source,
                            sample_scenarios=d.scenarios_by_pair.get(appms.pair_key(r.drug_a, r.drug_b), 0)),
        message=f"{r.severity}: {r.interaction_category}.")
