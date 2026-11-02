# SOURCE: NOT IN PAPERS. Loader for the APPMS interaction-rule files (IEEE DataPort, DOI
# 10.21227/9er6-w543), read from data/appms/ at run time. Nothing is copied into the repo.
"""APPMS is synthetic: its labels are a pure function of the 9 seed rules in ddi_seed_rules.csv.
Do not train or score a model on it. It serves as (a) a source of interaction rules and
severity, (b) sample patients, (c) a coverage test. "Not flagged" means no rule matched; it is
not proof of safety. Files are plain CSV; the literal text "None" in a condition or allergy
column means the patient has none and is loaded as null."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

FILES = {
    "patients": "patients.csv",
    "medications": "medications.csv",
    "scenarios": "patient_drug_pair_scenarios.csv",
    "rules": "ddi_seed_rules.csv",
}
SEVERITIES = ("Critical", "High", "Moderate")
Severity = Literal["Critical", "High", "Moderate"]
NOT_FLAGGED_LABEL = "Not flagged by seed rules"
NO_MATCH_TEXT = "No known interaction found in our rules. This does not mean the combination is safe."


class Patient(BaseModel):
    patient_id: str
    age_years: int
    gender: str
    state: str
    district: str
    residence_type: str
    primary_condition: str | None
    secondary_condition: str | None
    reported_drug_allergy: str | None
    egfr_category: str


class Medication(BaseModel):
    medication_record_id: str
    patient_id: str
    drug_name: str
    strength: str
    route: str
    indication: str
    frequency: str
    duration_days: int
    start_date: date | None = None  # column start_date_synthetic; not served by the /api/appms routes


class Scenario(BaseModel):
    scenario_id: str
    patient_id: str
    drug_a: str
    drug_b: str
    flagged: bool
    severity: Severity | None
    interaction_category: str
    mechanism_or_risk: str
    explanation: str


class Rule(BaseModel):
    drug_a: str
    drug_b: str
    severity: Severity
    interaction_category: str
    mechanism_or_risk: str
    explanation_or_action: str
    evidence_source: str


@dataclass(frozen=True)
class AppmsData:
    patients: list[Patient]
    medications: list[Medication]
    scenarios: list[Scenario]
    rules: list[Rule]
    meds_by_patient: dict[str, list[Medication]] = field(default_factory=dict)
    rule_by_pair: dict[frozenset[str], Rule] = field(default_factory=dict)
    scenarios_by_pair: dict[frozenset[str], int] = field(default_factory=dict)


class AppmsMissing(Exception):
    """data/appms or one of its files is absent."""


def pair_key(a: str, b: str) -> frozenset[str]:
    return frozenset((a.strip().lower(), b.strip().lower()))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _none(v: str) -> str | None:
    v = v.strip()
    return None if v in ("", "None") else v


def _date(v: str | None) -> date | None:
    try:
        return date.fromisoformat((v or "").strip())
    except ValueError:
        return None


def missing_files(folder: Path) -> list[str]:
    return [n for n in FILES.values() if not (folder / n).is_file()]


def load(folder: Path) -> AppmsData:
    gone = missing_files(folder)
    if gone:
        raise AppmsMissing(f"missing in data/appms: {', '.join(gone)}")
    patients = [Patient(patient_id=r["patient_id"], age_years=int(r["age_years"]), gender=r["gender"],
                        state=r["state"], district=r["district"], residence_type=r["residence_type"],
                        primary_condition=_none(r["primary_condition"]),
                        secondary_condition=_none(r["secondary_condition"]),
                        reported_drug_allergy=_none(r["reported_drug_allergy"]),
                        egfr_category=r["egfr_category"])
                for r in _rows(folder / FILES["patients"])]
    meds = [Medication(medication_record_id=r["medication_record_id"], patient_id=r["patient_id"],
                       drug_name=r["drug_name"], strength=r["strength"], route=r["route"],
                       indication=r["indication"], frequency=r["frequency"],
                       duration_days=int(r["duration_days"]), start_date=_date(r.get("start_date_synthetic", "")))
            for r in _rows(folder / FILES["medications"])]
    scen = []
    for r in _rows(folder / FILES["scenarios"]):
        flagged = r["known_interaction_in_seed_rules"].strip() == "1"
        scen.append(Scenario(scenario_id=r["scenario_id"], patient_id=r["patient_id"], drug_a=r["drug_a"],
                             drug_b=r["drug_b"], flagged=flagged,
                             severity=r["severity_label"] if flagged else None,
                             interaction_category=r["interaction_category"],
                             mechanism_or_risk=r["mechanism_or_risk"], explanation=r["xai_explanation"]))
    rules = [Rule(drug_a=r["drug_a"], drug_b=r["drug_b"], severity=r["severity_label"],
                  interaction_category=r["interaction_category"], mechanism_or_risk=r["mechanism_or_risk"],
                  explanation_or_action=r["explanation_or_action"], evidence_source=r["evidence_source"])
             for r in _rows(folder / FILES["rules"])]
    by_patient: dict[str, list[Medication]] = {}
    for m in meds:
        by_patient.setdefault(m.patient_id, []).append(m)
    counts: dict[frozenset[str], int] = {}
    for s in scen:
        k = pair_key(s.drug_a, s.drug_b)
        counts[k] = counts.get(k, 0) + 1
    return AppmsData(patients, meds, scen, rules, by_patient,
                     {pair_key(r.drug_a, r.drug_b): r for r in rules}, counts)


def find_rule(data: AppmsData, a: str, b: str) -> Rule | None:
    return data.rule_by_pair.get(pair_key(a, b))
