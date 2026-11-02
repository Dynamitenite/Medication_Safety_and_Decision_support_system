# SOURCE: NOT IN PAPERS. Typed request/response models for the API.
"""Every endpoint returns one of these. A component whose data is missing returns
status="not_ready" with a reason and a fix, never placeholder numbers."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


# ---- catalogue: suggest, brand, alternatives ---------------------------------------------
class BrandRow(ApiModel):
    id: str
    name: str
    manufacturer: str | None
    type: str
    pack_size: str
    price: float | None  # rupees per pack as listed; None when the catalogue lists 0
    discontinued: bool
    composition: str
    ingredients: list[str]
    composition_incomplete: bool  # two listed ingredients and no full composition: may hold more
    composition_conflict: bool    # the catalogue's two composition fields disagree
    composition_unclear: bool     # the composition repeats an ingredient (maybe wrong); never a match for another product
    form_family: str              # dosage-form family from the name and pack label (medsafe/forms.py); "unknown"


class BrandSuggestion(BrandRow):
    match: Literal["prefix", "word", "ingredient", "substring", "fuzzy"]
    matched_ingredient: str | None  # set when the hit is on an ingredient name


class SuggestResponse(Readiness):
    query: str = ""
    matcher: str = ""  # fuzzy backend actually used: rapidfuzz or difflib
    elapsed_ms: float | None = None
    matches: list[BrandSuggestion] = Field(default_factory=list)
    similar: list[BrandSuggestion] = Field(default_factory=list)


class LabelRef(ApiModel):
    set_id: str
    title: str
    product: str
    manufacturer: str | None
    sections: int  # sections with text; the default label has the most
    effective_time: str | None
    single_ingredient: bool
    form: str | None  # dosage form(s) from the label's SPL, e.g. "Tablet, film coated"
    route: str | None
    form_family: str  # family used for matching; "unknown" when the SPL form could not be placed
    form_inferred: bool  # no form in the SPL: the family comes from words in the title
    default: bool


class IngredientDetail(ApiModel):
    name: str  # as written in the catalogue
    strength: str | None  # None: not stated
    key: str
    us_name: str | None  # the US name when it differs (medsafe/synonyms.csv)
    link_method: Literal["ingredient name", "active moiety"] | None
    combination_only: bool  # only combination-product labels carry this ingredient
    moieties: list[str]
    form_match: Literal["matched", "none", "brand_form_unknown", "no_label"]  # default label vs the brand's form
    labels: list[LabelRef]


class SecondaryInteraction(ApiModel):
    drug: str
    effect: str


class BrandResponse(Readiness):
    brand: BrandRow | None = None
    ingredient_details: list[IngredientDetail] = Field(default_factory=list)
    short_composition: str | None = None  # the other composition field when the two disagree
    secondary_source_label: str = ""
    secondary_interactions: list[SecondaryInteraction] = Field(default_factory=list)
    price_note: str = ""
    label_note: str = ""
    default_label_rule: str = ""
    form_note: str = ""  # shown for an ingredient whose form_match is "none"
    form_unknown_note: str = ""  # shown for an ingredient whose form_match is "brand_form_unknown"


class AlternativeBrand(BrandRow):
    price_difference: float | None  # this price minus the selected brand's price
    different_pack_size: bool


class StrengthGroup(ApiModel):
    composition: str
    brands_total: int
    lowest_price: float | None
    strength_stated: bool
    brands: list[AlternativeBrand]


class BrandAlternativesResponse(Readiness):
    id: str = ""
    note: str = ""
    price_note: str = ""
    caveats: list[str] = Field(default_factory=list)
    strength_stated: bool = True
    include_discontinued: bool = False
    form_family: str = "unknown"  # the selected product's family
    composition_unclear: bool = False  # the selected product's composition repeats an ingredient: no matches
    unclear_total: int = 0
    unclear: list[AlternativeBrand] = Field(default_factory=list)  # unclear products with the same ingredient set
    same_total: int = 0
    same: list[AlternativeBrand] = Field(default_factory=list)
    different_form_total: int = 0
    different_form: list[AlternativeBrand] = Field(default_factory=list)
    form_not_stated_total: int = 0
    form_not_stated: list[AlternativeBrand] = Field(default_factory=list)
    other_strength_other_form_hidden: int = 0
    other_strength_groups_total: int = 0
    other_strength: list[StrengthGroup] = Field(default_factory=list)


class SynonymRow(ApiModel):
    name: str
    maps_to: str
    kind: str
    note: str


class UnlinkedIngredient(ApiModel):
    name: str
    us_name: str | None
    rows: int


class CatalogueSummaryResponse(Readiness):
    source: str = ""
    licence: str = ""
    original_source: str = ""
    file_date: str | None = None
    built_at: str | None = None
    brands: int = 0
    discontinued: int = 0
    composition_incomplete: int = 0
    composition_conflict: int = 0
    composition_unclear: int = 0
    from_full_composition: int = 0
    price_not_stated: int = 0
    distinct_ingredients: int = 0
    ingredients_linked: int = 0
    ingredients_linked_combination_only: int = 0
    brands_all_linked: int = 0
    brands_complete: int = 0
    brands_complete_all_linked: int = 0
    secondary_interaction_rows: int = 0
    dailymed_parts_loaded: list[str] = Field(default_factory=list)
    dailymed_labels_loaded: int = 0
    top_unlinked: list[UnlinkedIngredient] = Field(default_factory=list)
    synonyms: list[SynonymRow] = Field(default_factory=list)


# ---- DailyMed label (text tabs) -----------------------------------------------------------
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
    form: str | None = None  # dosage form and route from the label's SPL, e.g. "Tablet · Oral"
    sections: list[LabelSection] = Field(default_factory=list)


class Alternative(ApiModel):
    product: str
    manufacturer: str | None
    set_id: str
    ingredients: list[str]
    label_count: int
    form: str | None = None  # dosage form and route of this label


class AlternativesResponse(Readiness):
    set_id: str = ""
    active_moieties: list[str] = Field(default_factory=list)
    note: str = ""
    total_labels: int = 0
    alternatives: list[Alternative] = Field(default_factory=list)


# ---- checker ------------------------------------------------------------------------------
class CheckerRequest(ApiModel):
    catalogue_ids: list[str] = Field(default_factory=list, max_length=10)
    # generic names (for example a sample patient's medicines): each is one ingredient
    names: list[str] = Field(default_factory=list, max_length=10)


class CheckerIngredient(ApiModel):
    name: str
    us_name: str | None
    label_set_id: str | None  # reference label used for the label-text match
    label_name: str | None


class CheckerMedicine(ApiModel):
    key: str
    catalogue_id: str | None
    name: str
    manufacturer: str | None
    kind: Literal["brand", "generic"]
    ingredients: list[CheckerIngredient]
    composition_incomplete: bool
    composition_unclear: bool = False


class TextMatch(ApiModel):
    sentence: str
    matched_term: str
    in_label_set_id: str
    in_label_name: str
    section: str
    names_drug: str  # the other medicine in the pair that the sentence names
    source_ingredient: str  # the ingredient whose label the sentence is from
    named_ingredient: str   # the other medicine's ingredient the sentence names


class RuleHit(ApiModel):
    a_ingredient: str
    b_ingredient: str
    severity: Literal["critical", "high", "moderate"]
    explanation: str


class AppmsResult(Readiness):
    source_label: str = "Interaction rules"
    severity: Literal["critical", "high", "moderate"] | None = None
    explanation: str | None = None
    hits: list[RuleHit] = Field(default_factory=list)


class TextMatchResult(ApiModel):
    source_label: str
    matches: list[TextMatch]
    matches_total: int
    notes: list[str]


class SecondaryHit(ApiModel):
    in_product: str
    drug: str
    effect: str
    matches_ingredient: str


class SecondaryResult(ApiModel):
    source_label: str
    hits: list[SecondaryHit]


class PairResult(ApiModel):
    a: CheckerMedicine
    b: CheckerMedicine
    appms: AppmsResult
    text_match: TextMatchResult
    shared_ingredients: list[str]
    secondary: SecondaryResult
    notes: list[str]


class CheckerResponse(Readiness):
    medicines: list[CheckerMedicine] = Field(default_factory=list)
    appms: AppmsResult = Field(default_factory=lambda: AppmsResult(status="not_ready"))
    pairs: list[PairResult] = Field(default_factory=list)


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


# ---- accounts, profile and medical history ---------------------------------------------------
# Inputs trim text and turn blank text into null. Output models carry computed values (age, bmi,
# status, duration_days) that are null when the inputs they need are missing.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
Sex = Literal["female", "male", "other"]
BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
Severity = Literal["mild", "moderate", "severe", "unknown"]
ConditionKind = Literal["illness", "surgery", "injury", "other"]
ConditionStatus = Literal["current", "past"]
ConditionOutcome = Literal["cured", "ongoing", "not_cured", "unknown"]
MedicineOutcome = Literal["cured", "improved", "not_cured", "stopped", "unknown"]
CourseStatus = Literal["current", "past", "upcoming", "not_stated"]
RecordSource = Literal["typed", "scanned"]
FIRST_DOB = date(1900, 1, 1)


class EntryIn(ApiModel):
    """Base for request bodies: trims text, blank text becomes null, unknown fields are rejected."""
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    @field_validator("*", mode="before")
    @classmethod
    def _tidy(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class LoginRequest(ApiModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Enter a valid email address.")
        return v


class LoginResponse(ApiModel):
    email: str
    created: bool


class MeResponse(ApiModel):
    email: str
    created_at: datetime


class ProfileIn(EntryIn):
    name: str | None = Field(None, max_length=100)
    date_of_birth: date | None = None
    sex: Sex | None = None
    height_cm: float | None = Field(None, ge=40, le=250)
    weight_kg: float | None = Field(None, ge=2, le=400)
    blood_group: BloodGroup | None = None
    notes: str | None = Field(None, max_length=2000)

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v: date | None) -> date | None:
        if v is not None and not (FIRST_DOB <= v <= date.today()):
            raise ValueError("Date of birth must be between 1900 and today.")
        return v


class ProfileOut(ApiModel):
    name: str | None
    date_of_birth: date | None
    age: int | None
    sex: Sex | None
    height_cm: float | None
    weight_kg: float | None
    bmi: float | None
    blood_group: BloodGroup | None
    notes: str | None
    updated_at: datetime


class AllergyIn(EntryIn):
    allergen: str = Field(min_length=1, max_length=200)
    reaction: str | None = Field(None, max_length=500)
    severity: Severity = "unknown"
    notes: str | None = Field(None, max_length=2000)


class AllergyOut(ApiModel):
    id: int
    allergen: str
    reaction: str | None
    severity: Severity
    notes: str | None


class ConditionIn(EntryIn):
    name: str = Field(min_length=1, max_length=200)
    kind: ConditionKind = "illness"
    status: ConditionStatus
    onset_date: date | None = None
    resolved_date: date | None = None
    outcome: ConditionOutcome = "unknown"
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _consistent(self) -> "ConditionIn":
        if self.resolved_date and self.status != "past":
            raise ValueError("A current condition has no resolved date.")
        if self.onset_date and self.resolved_date and self.resolved_date < self.onset_date:
            raise ValueError("The resolved date cannot be before the start date.")
        if self.status == "current" and self.outcome == "cured":
            raise ValueError("A current condition cannot be marked as cured.")
        return self


class ConditionOut(ApiModel):
    id: int
    name: str
    kind: ConditionKind
    status: ConditionStatus
    onset_date: date | None
    resolved_date: date | None
    outcome: ConditionOutcome
    notes: str | None


class MedicineRecordIn(EntryIn):
    catalogue_id: str | None = Field(None, max_length=40)
    display_name: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(None, max_length=300)
    dose: str | None = Field(None, max_length=100)
    frequency: str | None = Field(None, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    outcome: MedicineOutcome | None = None
    source: RecordSource = "typed"
    notes: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _course(self) -> "MedicineRecordIn":
        if self.end_date and not self.start_date:
            raise ValueError("Enter a start date to go with the end date.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date cannot be before the start date.")
        return self


class MedicineRecordOut(ApiModel):
    id: int
    catalogue_id: str | None
    display_name: str
    ingredients: list[str]
    reason: str | None
    dose: str | None
    frequency: str | None
    start_date: date | None
    end_date: date | None
    outcome: MedicineOutcome | None
    source: RecordSource
    notes: str | None
    status: CourseStatus
    duration_days: int | None
