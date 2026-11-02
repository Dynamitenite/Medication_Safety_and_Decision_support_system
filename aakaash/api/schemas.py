# SOURCE: NOT IN PAPERS. Typed request/response models for the API.
"""Every endpoint returns one of these. A component whose data is missing returns
status="not_ready" with a reason and a fix, never placeholder numbers."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DDILabel = Literal["effect", "mechanism", "advise", "int", "false"]


class ApiModel(BaseModel):
    # Fields with defaults are always present in a response, so the generated TypeScript types
    # must not mark them optional.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Readiness(ApiModel):
    status: Literal["ready", "not_ready"]
    reason: str | None = None
    fix: str | None = None


class Health(ApiModel):
    status: Literal["ok"] = "ok"


# ---- /api/status -------------------------------------------------------------------------
class ComponentStatus(Readiness):
    id: str
    label: str
    detail: dict[str, str | int | float] = Field(default_factory=dict)


class ModuleStatus(ApiModel):
    id: str
    label: str
    status: Literal["coming_soon"] = "coming_soon"
    stages: list[int]
    stage_names: list[str]
    owner: str = "to be confirmed"


class StageInfo(ApiModel):
    number: int
    name: str
    in_scope: bool  # covered by this app (stages 2, 4, 5, 6 per the project brief)


class StatusResponse(ApiModel):
    components: list[ComponentStatus]
    modules: list[ModuleStatus]
    stages: list[StageInfo]
    active_encoder: str
    active_classifier: str
    data_dir: str


# ---- DDI 2013 -----------------------------------------------------------------------------
class DDISplitStats(ApiModel):
    split: Literal["train", "dev", "test"]
    instances: int
    class_counts: dict[str, int]
    imbalance_false_to_class: dict[str, float | None]
    by_source: dict[str, int]


class DDIParserStats(ApiModel):
    """Counts straight from the parser, before the dev split is carved out of train."""
    split: Literal["train_all", "test"]
    counts: dict[str, int]


class DDIStatsResponse(Readiness):
    labels: list[str] = Field(default_factory=list)
    files_by_split: dict[str, int] = Field(default_factory=dict)
    splits: list[DDISplitStats] = Field(default_factory=list)
    parser: list[DDIParserStats] = Field(default_factory=list)
    dev_frac: float | None = None
    seed: int | None = None


class DDIExample(ApiModel):
    split: Literal["train", "dev", "test"]
    label: DDILabel
    source: str
    doc_id: str
    sent_id: str
    pair_id: str
    e1_text: str
    e2_text: str
    text: str
    marked_text: str


class DDIExamplesResponse(Readiness):
    total_matching: int = 0
    examples: list[DDIExample] = Field(default_factory=list)


# ---- DailyMed / TAC ----------------------------------------------------------------------
class ZipFileInfo(ApiModel):
    name: str
    size_bytes: int


class DailyMedStatsResponse(Readiness):
    zip_files: list[ZipFileInfo] = Field(default_factory=list)
    parts_loaded: list[str] = Field(default_factory=list)
    # is_sample/scope come from the stats file itself: a capped run must never read as a full count
    is_sample: bool | None = None
    scope: str | None = None
    sample_limit_per_part: int | None = None
    zip_entries: dict[str, int] = Field(default_factory=dict)
    labels_parsed: int | None = None
    parse_failures: int | None = None
    labels_per_section: dict[str, int] = Field(default_factory=dict)
    chunks: int | None = None
    chunks_per_section: dict[str, int] = Field(default_factory=dict)
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    distinct_ingredients: int | None = None
    distinct_active_moieties: int | None = None
    distinct_manufacturers: int | None = None
    labels_without_any_section: int | None = None
    ingredient_source: dict[str, int] = Field(default_factory=dict)
    peak_working_set_mb: float | None = None
    parse_stats: dict[str, int] = Field(default_factory=dict)
    elapsed_seconds: float | None = None
    generated_at: str | None = None


class TacStatsResponse(Readiness):
    labels_per_split: dict[str, int] = Field(default_factory=dict)
    section_names: dict[str, int] = Field(default_factory=dict)
    mention_types: dict[str, int] = Field(default_factory=dict)
    relation_types: dict[str, int] = Field(default_factory=dict)
    mentions: int | None = None
    relations: int | None = None
    reactions: int | None = None
    labels_without_text: int | None = None
    parse_failures: int | None = None


# ---- /api/trace --------------------------------------------------------------------------
TraceCategory = Literal["from_papers", "from_baseline_review", "not_in_papers", "unclassified"]
TraceStatusKind = Literal["untested", "ran", "verified", "unknown"]


class TraceRow(ApiModel):
    component: str
    file: str
    source: str
    note: str
    status: str | None = None
    category: TraceCategory
    status_kind: TraceStatusKind


class TraceResponse(Readiness):
    rows: list[TraceRow] = Field(default_factory=list)
    counts_by_category: dict[str, int] = Field(default_factory=dict)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    malformed_rows: list[str] = Field(default_factory=list)
    preamble: list[str] = Field(default_factory=list)


# ---- medicines: suggest, label, alternatives, checker ------------------------------------
SuggestType = Literal["brand", "generic", "ingredient"]


class Suggestion(ApiModel):
    name: str
    type: SuggestType
    manufacturer: str | None
    set_id: str
    label_count: int
    match: Literal["prefix", "word", "substring", "fuzzy"]


class SuggestResponse(Readiness):
    query: str = ""
    matcher: str = ""  # fuzzy backend actually used: rapidfuzz or difflib
    elapsed_ms: float | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)


class LabelSection(ApiModel):
    key: str
    label: str
    text: str


class MedicineResponse(Readiness):
    set_id: str = ""
    title: str = ""
    products: list[str] = Field(default_factory=list)
    generic_names: list[str] = Field(default_factory=list)
    manufacturer: str | None = None
    ingredients: list[str] = Field(default_factory=list)  # raw names as on the label
    active_moieties: list[str] = Field(default_factory=list)  # used for matching
    effective_time: str | None = None
    sections: list[LabelSection] = Field(default_factory=list)


class Alternative(ApiModel):
    product: str
    manufacturer: str | None
    set_id: str
    ingredients: list[str]
    label_count: int


class AlternativesResponse(Readiness):
    set_id: str = ""
    active_moieties: list[str] = Field(default_factory=list)
    note: str = ""
    total_labels: int = 0
    alternatives: list[Alternative] = Field(default_factory=list)


class CheckerRequest(ApiModel):
    set_ids: list[str] = Field(default_factory=list, max_length=10)
    # medicines with no DailyMed label: only the interaction rules can be looked up, by name
    names: list[str] = Field(default_factory=list, max_length=10)


class CheckerMedicine(ApiModel):
    set_id: str
    name: str
    manufacturer: str | None
    active_moieties: list[str]
    has_interactions_section: bool


class TextMatch(ApiModel):
    sentence: str
    matched_term: str
    in_label_set_id: str
    in_label_name: str
    section: str
    names_drug: str  # the other medicine in the pair that the sentence names


class AppmsResult(Readiness):
    source_label: str = "Interaction rules"
    severity: Literal["critical", "high", "moderate"] | None = None
    explanation: str | None = None


class TextMatchResult(ApiModel):
    source_label: str
    matches: list[TextMatch]
    matches_total: int
    notes: list[str]


class PairResult(ApiModel):
    a: CheckerMedicine
    b: CheckerMedicine
    appms: AppmsResult
    text_match: TextMatchResult
    same_active_moiety: bool


class NamePairResult(ApiModel):
    """A pair where at least one medicine has no label: interaction rules only."""
    a: str
    b: str
    a_in_database: bool
    b_in_database: bool
    appms: AppmsResult


class CheckerResponse(Readiness):
    medicines: list[CheckerMedicine] = Field(default_factory=list)
    appms: AppmsResult = Field(default_factory=lambda: AppmsResult(status="not_ready"))
    pairs: list[PairResult] = Field(default_factory=list)
    name_pairs: list[NamePairResult] = Field(default_factory=list)


# ---- APPMS interaction rules -------------------------------------------------------------
class AppmsSeverityCount(ApiModel):
    severity: Literal["Critical", "High", "Moderate"]
    scenarios: int


class AppmsUnmatched(ApiModel):
    drug_name: str
    rows: int


class AppmsMatchSummary(ApiModel):
    medication_rows: int
    rows_matched: int
    drug_names: int
    names_matched: int
    unmatched: list[AppmsUnmatched]


class AppmsSummaryResponse(Readiness):
    patients: int = 0
    medication_rows: int = 0
    scenarios: int = 0
    rules: int = 0
    flagged_scenarios: int = 0
    not_flagged_scenarios: int = 0
    severity: list[AppmsSeverityCount] = Field(default_factory=list)
    distinct_explanations: int = 0
    orphan_medication_rows: int = 0
    note: str = ""
    match: AppmsMatchSummary | None = None


class AppmsPatient(ApiModel):
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


class AppmsLabelRef(ApiModel):
    set_id: str
    name: str
    manufacturer: str | None


class AppmsMedication(ApiModel):
    medication_record_id: str
    label_count: int = 0  # DailyMed labels with the same active ingredient
    label: AppmsLabelRef | None = None  # one of them, for loading into the checker
    drug_name: str
    strength: str
    route: str
    indication: str
    frequency: str
    duration_days: int


class AppmsPatientsResponse(Readiness):
    total: int = 0
    limit: int = 0
    offset: int = 0
    patients: list[AppmsPatient] = Field(default_factory=list)


class AppmsPatientResponse(Readiness):
    patient: AppmsPatient | None = None
    medications: list[AppmsMedication] = Field(default_factory=list)


class AppmsRuleMatch(ApiModel):
    drug_a: str
    drug_b: str
    severity: Literal["Critical", "High", "Moderate"]
    interaction_category: str
    mechanism_or_risk: str
    explanation: str
    evidence_source: str
    sample_scenarios: int


class AppmsLookupResponse(Readiness):
    drug_a: str = ""
    drug_b: str = ""
    matched: bool = False
    rule: AppmsRuleMatch | None = None
    message: str = ""
