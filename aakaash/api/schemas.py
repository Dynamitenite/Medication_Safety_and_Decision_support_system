# SOURCE: NOT IN PAPERS. Typed request/response models for the API.
"""Every endpoint returns one of these. A component whose data is missing returns
status="not_ready" with a reason and a fix, never placeholder numbers."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal

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
    # The term in the sentence that names the source ingredient (its label's own drug), when there is one.
    # With matched_term it lets the interaction-type model mark both drugs. None: the sentence cannot be marked.
    source_term: str | None = None


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


# ---- add new medicine: details, risk analysis, adding ---------------------------------------
RiskLevel = Literal["Medium", "High", "Critical"]
Mismatch = Literal["wrong_form", "combination_label", "single_for_combination", "form_unknown"]


class DetailLabel(ApiModel):
    set_id: str
    name: str  # product name on the US label, else its title
    manufacturer: str | None
    form: str | None
    route: str | None
    form_family: str


class DetailSection(ApiModel):
    key: str
    label: str
    text: str  # verbatim label text, never summarised


class IngredientDetails(Readiness):
    name: str
    strength: str | None
    us_name: str | None
    label: DetailLabel | None  # the label chosen by the dosage-form rule; None when no US label is linked
    form_match: Literal["matched", "none", "brand_form_unknown", "no_label"]
    combination_label: bool  # the label is for a combination product
    mismatch: Mismatch | None
    mismatch_note: str | None
    indications: DetailSection | None
    boxed_warning: DetailSection | None
    instructions: list[DetailSection] = Field(default_factory=list)  # dosage, counselling, patient leaflets
    missing: list[str] = Field(default_factory=list)  # section names the label does not have
    withheld_note: str | None = None  # why dosage and instruction text is not shown


class MedicineDetailsResponse(Readiness):
    id: str
    name: str | None = None
    form_family: str | None = None
    composition: str | None = None
    composition_incomplete: bool = False
    composition_unclear: bool = False
    label_note: str | None = None
    ingredients: list[IngredientDetails] = Field(default_factory=list)


class CourseIn(ApiModel):
    """A medicine to add, with the optional course the user entered."""
    catalogue_id: str = Field(min_length=1, max_length=40)
    reason: str | None = Field(None, max_length=300)
    dose: str | None = Field(None, max_length=100)
    frequency: str | None = Field(None, max_length=100)
    food: str | None = Field(None, max_length=100)  # "after food", as read or typed
    start_date: date | None = None
    end_date: date | None = None
    duration_days: int | None = Field(None, ge=1, le=3650)
    source: RecordSource = "typed"

    @field_validator("reason", "dose", "frequency", "food", mode="before")
    @classmethod
    def _blank(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def _course(self) -> "CourseIn":
        if self.end_date and self.duration_days:
            raise ValueError("Enter either a duration or an end date, not both.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date cannot be before the start date.")
        return self


class AnalyzeRequest(ApiModel):
    # Only the new medicines. The user's current medicines and allergies are read on the server;
    # any other field in the body is ignored.
    medicines: list[CourseIn] = Field(min_length=1, max_length=10)


class LevelledHit(ApiModel):
    a_ingredient: str
    b_ingredient: str
    level: RiskLevel
    rule_tier: Literal["critical", "high", "moderate"]  # the rules' own tier name
    explanation: str


class AnalyzedMedicine(ApiModel):
    medicine: CheckerMedicine
    role: Literal["new", "current"]
    record_id: int | None = None
    dates_not_entered: bool = False
    checked_by_name_only: bool = False


class PairFinding(ApiModel):
    a: CheckerMedicine
    b: CheckerMedicine
    a_role: Literal["new", "current"]
    b_role: Literal["new", "current"]
    level: RiskLevel | None  # from the interaction rules only
    hits: list[LevelledHit]
    text_match: TextMatchResult  # supporting label sentences; never changes the level
    shared_ingredients: list[str]
    notes: list[str]


class AllergyFinding(ApiModel):
    medicine: CheckerMedicine
    allergy_id: int
    allergen: str
    reaction: str | None
    severity: Severity
    level: RiskLevel
    ingredients: list[str]  # the medicine's ingredients that matched
    note: str
    notes: list[str]


class AnalyzeResponse(Readiness):
    overall: RiskLevel | None = None
    overall_text: str | None = None
    levels: list[RiskLevel] = Field(default_factory=list)  # the meter's labelled levels, lowest first
    rules: AppmsResult = Field(default_factory=lambda: AppmsResult(status="not_ready"))
    medicines: list[AnalyzedMedicine] = Field(default_factory=list)
    allergies_checked: int = 0
    allergy_note: str = ""
    allergy_findings: list[AllergyFinding] = Field(default_factory=list)
    pairs: list[PairFinding] = Field(default_factory=list)  # pairs with a rule hit, label text or a shared ingredient
    pairs_checked: int = 0
    disclaimer: str = ""
    level_rule: str = ""


class ProfileOverview(ApiModel):
    """Counts and the highest rule level among the user's current medicines, for the profile tiles."""
    current_medicines: int
    allergies: int
    current_conditions: int
    highest_risk: RiskLevel | None = None
    risk_status: Literal["found", "none_found", "not_enough_data"]
    pairs_checked: int = 0
    risk_note: str = ""


class FormFamilyCount(ApiModel):
    family: str
    products: int


class CatalogueFormsResponse(Readiness):
    total: int = 0
    families: list[FormFamilyCount] = Field(default_factory=list)


class AddMedicinesRequest(ApiModel):
    items: list[CourseIn] = Field(min_length=1, max_length=10)
    acknowledged_warning: bool = False


class AddMedicinesResponse(ApiModel):
    overall: RiskLevel | None
    added: list[MedicineRecordOut]


# ---- DDI interaction-type classifier (Focal Loss model). A model estimate only: never sets a risk level.

class DDIClassifyRequest(ApiModel):
    sentence: str = Field(min_length=1, max_length=2000)
    drug_1: str = Field(min_length=1, max_length=100)
    drug_2: str = Field(min_length=1, max_length=100)
    explain: bool = False  # also return word attributions (slower)


class DDIWord(ApiModel):
    text: str
    start: int
    end: int
    attribution: float  # signed; positive pushes toward the predicted class
    is_drug: bool


class DDIModelInfo(ApiModel):
    version: str
    loss: Literal["ce", "focal"]
    gamma: float
    alpha: str
    encoder: str
    smoke_test: bool


class DDIIgInfo(ApiModel):
    n_steps: int
    delta: float  # largest absolute convergence delta of Integrated Gradients


class DDIClassifyResponse(ApiModel):
    status: Literal["ready", "not_ready", "not_markable"]
    reason: str | None = None
    fix: str | None = None
    predicted: DDILabel | None = None
    probability: float | None = None
    probabilities: dict[str, float] | None = None
    marked_text: str | None = None
    words: list[DDIWord] | None = None
    ig: DDIIgInfo | None = None
    model: DDIModelInfo | None = None
    timing_ms: dict[str, float] | None = None
    label: str = "Model estimate"


class DDIPRF(ApiModel):
    precision: float
    recall: float
    f1: float


class DDIClassRow(DDIPRF):
    label: str
    support: int


class DDISplitMetrics(ApiModel):
    n: int
    micro: DDIPRF  # over the four positive classes (false ignored)
    per_class: list[DDIClassRow]
    labels: list[str]
    confusion_matrix: list[list[int]]  # rows gold, columns predicted


class DDIFaithK(ApiModel):
    k: int
    n: int
    skipped: int
    mean_drop_top_k: float | None = None
    mean_drop_random_k: float | None = None


class DDIFaithfulness(ApiModel):
    label: str
    source: str
    seed: int
    random_draws: int
    n_steps: int
    n_sentences: int
    by_k: list[DDIFaithK]


class DDIRun(ApiModel):
    name: str
    version: str
    smoke_test: bool
    loss: Literal["ce", "focal"]
    gamma: float
    alpha: str
    lr_encoder: float
    lr_head: float
    best_epoch: int
    seed: int
    encoder: str
    n_train: int
    n_dev: int
    n_test: int | None = None
    dev: DDISplitMetrics
    test: DDISplitMetrics | None = None
    faithfulness: DDIFaithfulness | None = None


class DDISearchRow(ApiModel):
    loss: Literal["ce", "focal"]
    gamma: float
    alpha: str
    lr_encoder: float
    lr_head: float
    best_epoch: int
    dev_micro_f1: float


class DDIMetricsResponse(Readiness):
    runs: list[DDIRun] = Field(default_factory=list)
    search: list[DDISearchRow] = Field(default_factory=list)
    search_smoke_test: bool = False


# ---- label search and similar uses ---------------------------------------------------------------
class SearchLabelsRequest(ApiModel):
    query: str = Field(min_length=1, max_length=300)
    medicine_id: str | None = None   # limit to the US labels linked to this medicine's ingredients
    set_ids: list[str] | None = Field(default=None, max_length=50)  # or to these labels
    k: int = Field(5, ge=1, le=20)
    scope: Literal["default", "all"] = "default"  # with medicine_id: the default label only, or every linked label

    @field_validator("query")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        return v


class SearchResult(ApiModel):
    chunk_id: str
    score: float  # cosine similarity between the query and this passage
    section: str
    section_label: str
    set_id: str
    product: str
    manufacturer: str | None
    form: str | None
    route: str | None
    form_family: str
    is_default_label: bool
    text: str  # verbatim label text; empty when withheld
    match_terms: list[str]  # words of the query that appear in the text (for highlighting only)
    withheld: bool = False
    withheld_note: str | None = None
    mismatch_note: str | None = None  # why this label may not fit the selected medicine


class SearchLabelsResponse(Readiness):
    encoder: str = ""
    encoder_label: str = ""
    is_deep_learning: bool = False
    restricted_to: str = ""
    labels_searched: int = 0
    elapsed_ms: float = 0
    note: str = ""
    results: list[SearchResult] = Field(default_factory=list)
    fallback_note: str | None = None  # set when the configured encoder could not be used and TF-IDF answered


class SimilarBrand(AlternativeBrand):
    ingredient_count: int


class SimilarLabelRef(ApiModel):
    set_id: str
    name: str
    manufacturer: str | None
    form: str | None
    route: str | None


class SimilarUseSuggestion(ApiModel):
    ingredient: str
    us_name: str | None
    similarity: float  # best cosine between an Indications passage of the selected ingredient and one of this ingredient
    supporting_chunks: int | None  # passages at or above the minimum similarity; None until a minimum is set
    supporting_sentence: str  # verbatim from the US label
    supporting_label: SimilarLabelRef
    matched_query_sentence: str  # the sentence of the selected ingredient's label it was compared with
    flags: list[str] = Field(default_factory=list)
    brands_total: int
    brands: list[SimilarBrand]
    brands_note: str | None = None


class SimilarUseGroup(ApiModel):
    ingredient: str
    query_labels: int
    query_passages: int
    from_combination_label: bool = False
    note: str | None = None
    suggestions: list[SimilarUseSuggestion] = Field(default_factory=list)


class SimilarUseResponse(Readiness):
    id: str = ""
    name: str = ""
    encoder: str = ""
    encoder_label: str = ""
    fallback_note: str | None = None
    is_deep_learning: bool = False
    min_similarity: float | None = None
    heading: str = ""
    note: str = ""
    combination_note: str | None = None
    groups: list[SimilarUseGroup] = Field(default_factory=list)


class IndexSummaryResponse(Readiness):
    labels: int = 0
    chunks: int = 0
    chunks_per_section: dict[str, int] = Field(default_factory=dict)
    parts_loaded: list[str] = Field(default_factory=list)
    chunk_size: int = 0
    chunk_overlap: int = 0
    chunk_unit: str = ""
    is_sample: bool = False
    encoders_built: list[str] = Field(default_factory=list)
    active_encoder: str = ""
    active_encoder_label: str = ""
    is_deep_learning: bool = False
    dimension: int | None = None
    vectors: int | None = None
    vector_bytes: int | None = None
    build_seconds: float | None = None
    configured_encoder: str = ""
    fallback_note: str | None = None  # set when ENCODER=sbert is configured but TF-IDF answered
    model: str | None = None
    model_revision: str | None = None
    device: str | None = None
    window_token_budget: int | None = None
    window_overlap_words: int | None = None


# ---- grounded answers (hosted LLM). Every response is a not_ready box when the key, the quota or the provider
# is missing; the generated part of the page is then hidden and the verbatim label text stays.
class AnswerBase(Readiness):
    provider: str | None = None
    model: str | None = None
    retry_after: int | None = None  # seconds, when rate limited
    ai_label: str = "AI-written from label text"
    disclaimer: str = "Informational only. Not a substitute for advice from your doctor or pharmacist."


class AnswerStatusResponse(AnswerBase):
    requests_per_minute: int | None = None
    note: str = ("Free-tier prompts may be used by the provider to improve its products. Only label text, ingredient names "
                 "and your question are sent; no profile data.")


class AskRequest(ApiModel):
    medicine_id: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=1, max_length=300)
    scope: Literal["default", "all"] = "default"

    @field_validator("question")
    @classmethod
    def _strip_q(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        return v


class AnswerSource(ApiModel):
    chunk_id: str
    section_label: str
    product: str
    set_id: str
    text: str  # verbatim label passage that was sent to the model
    cited: bool


class AskResponse(AnswerBase):
    kind: Literal["label", "alternatives"] = "label"  # "alternatives": a price/alternatives question, answered without the model
    alt_note: str | None = None                       # the sentence shown with the list
    alt_form_family: str | None = None
    alt_total: int = 0                                # all same ingredients, strength and form brands
    alternatives: list[AlternativeBrand] = Field(default_factory=list)  # the cheapest few of them
    answer: str | None = None
    not_found: bool = False
    note: str | None = None
    citations: list[str] = Field(default_factory=list)
    sources: list[AnswerSource] = Field(default_factory=list)
    dropped_sentences: int = 0   # sentences removed because they cited an id that was not supplied
    uncited_sentences: int = 0   # kept sentences with no citation


class SimplifyRequest(ApiModel):
    medicine_id: str = Field(min_length=1, max_length=40)
    ingredient_index: int = Field(ge=0, le=20)  # position in the details response
    section_key: str = Field(min_length=1, max_length=40)


class SimplifyResponse(AnswerBase):
    section_label: str | None = None
    original: str | None = None   # the verbatim section that was sent
    simplified: str | None = None
    flagged: bool = False         # numbers or units in the rewrite that are not in the original
    unmatched: list[str] = Field(default_factory=list)


class ExplainFindingRequest(ApiModel):
    kind: Literal["pair", "allergy"]
    a: str = Field(min_length=1, max_length=100)  # pair: first ingredient. allergy: the allergen
    b: str = Field(min_length=1, max_length=100)  # pair: second ingredient. allergy: the ingredient
    level: RiskLevel                              # from the rules; echoed back unchanged, never sent to the model
    explanation: str | None = Field(None, max_length=1500)
    sentences: list[Annotated[str, Field(max_length=600)]] = Field(default_factory=list, max_length=3)
    predicted_class: str | None = Field(None, max_length=40)


class ExplainFindingResponse(AnswerBase):
    level: RiskLevel | None = None
    text: str | None = None
    flagged: bool = False
    unmatched: list[str] = Field(default_factory=list)
