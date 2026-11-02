// Typed client for the FastAPI router (api/router.py). The types are generated from the API's own
// OpenAPI schema (npm run gen:types), so they cannot drift from the backend.
import type { components } from "./api-types";

type S = components["schemas"];
export type StatusResponse = S["StatusResponse"];
export type ComponentStatus = S["ComponentStatus"];
export type ModuleStatus = S["ModuleStatus"];
export type StageInfo = S["StageInfo"];
export type DDIStatsResponse = S["DDIStatsResponse"];
export type DDIExamplesResponse = S["DDIExamplesResponse"];
export type DDIExample = S["DDIExample"];
export type DailyMedStatsResponse = S["DailyMedStatsResponse"];
export type TacStatsResponse = S["TacStatsResponse"];
export type TraceResponse = S["TraceResponse"];
export type TraceRow = S["TraceRow"];
export type SuggestResponse = S["SuggestResponse"];
export type BrandSuggestion = S["BrandSuggestion"];
export type BrandResponse = S["BrandResponse"];
export type BrandRow = S["BrandRow"];
export type IngredientDetail = S["IngredientDetail"];
export type LabelRef = S["LabelRef"];
export type BrandAlternativesResponse = S["BrandAlternativesResponse"];
export type AlternativeBrand = S["AlternativeBrand"];
export type CatalogueSummaryResponse = S["CatalogueSummaryResponse"];
export type MedicineResponse = S["MedicineResponse"];
export type AlternativesResponse = S["AlternativesResponse"];
export type CheckerResponse = S["CheckerResponse"];
export type PairResult = S["PairResult"];
export type CheckerMedicine = S["CheckerMedicine"];
export type AppmsSummaryResponse = S["AppmsSummaryResponse"];
export type AppmsPatientsResponse = S["AppmsPatientsResponse"];
export type AppmsPatientResponse = S["AppmsPatientResponse"];
export type AppmsLookupResponse = S["AppmsLookupResponse"];
export type AppmsPatient = S["AppmsPatient"];
export type AppmsMedication = S["AppmsMedication"];
export type AppmsLabelRef = S["AppmsLabelRef"];
export type ProfileOut = S["ProfileOut"];
export type ProfileIn = S["ProfileIn"];
export type AllergyOut = S["AllergyOut"];
export type AllergyIn = S["AllergyIn"];
export type ConditionOut = S["ConditionOut"];
export type ConditionIn = S["ConditionIn"];
export type MedicineRecordOut = S["MedicineRecordOut"];
export type MedicineRecordIn = S["MedicineRecordIn"];
export type MeResponse = S["MeResponse"];
export type LoginResponse = S["LoginResponse"];
export type MedicineDetailsResponse = S["MedicineDetailsResponse"];
export type IngredientDetails = S["IngredientDetails"];
export type DetailSection = S["DetailSection"];
export type CourseIn = S["CourseIn"];
export type AnalyzeResponse = S["AnalyzeResponse"];
export type PairFinding = S["PairFinding"];
export type AllergyFinding = S["AllergyFinding"];
export type AnalyzedMedicine = S["AnalyzedMedicine"];
export type RiskLevel = S["LevelledHit"]["level"];
export type AddMedicinesResponse = S["AddMedicinesResponse"];
export type Readiness = { status: "ready" | "not_ready"; reason?: string | null; fix?: string | null };

const BASE: string = import.meta.env.VITE_API_BASE ?? "";

/** `detail` is the server's own sentence (for example "Email or password is incorrect."), safe to show. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status = 0,
    readonly detail = "",
  ) {
    super(message);
  }
}

/** Message to show a person: the server's sentence when there is one. */
export const errorText = (e: unknown) => (e instanceof ApiError && e.detail ? e.detail : e instanceof Error ? e.message : String(e));

/** Fired when a request finds the session has ended, so the app can send the person back to the login page. */
export const SIGNED_OUT_EVENT = "medsafe:signed-out";
const QUIET_401 = new Set(["/api/auth/login", "/api/auth/me", "/api/auth/logout"]);

/** FastAPI sends detail as a string, or as a list of {loc, msg} for a rejected form. */
function detailOf(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d?.msg === "string" ? d.msg.replace(/^Value error, /, "") : ""))
      .filter(Boolean)
      .join(" ");
  }
  return "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { credentials: "same-origin", ...init });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(
      "Cannot reach the API. Start it from the aakaash folder with: " +
        ".venv\\Scripts\\python.exe -m uvicorn api.app:app --port 8000",
    );
  }
  if (!res.ok) {
    let detail = "";
    try {
      detail = detailOf((await res.json())?.detail);
    } catch {
      /* no JSON body */
    }
    if (res.status === 401 && !QUIET_401.has(path)) window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    throw new ApiError(`API returned ${res.status} for ${path}${detail ? `: ${detail}` : ""}`, res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T,>(path: string, signal?: AbortSignal) => request<T>(path, { signal });
const send = <T,>(method: "POST" | "PUT", path: string, body: unknown) =>
  request<T>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const del = (path: string) => request<void>(path, { method: "DELETE" });

export const api = {
  status: () => get<StatusResponse>("/api/status"),
  ddiStats: () => get<DDIStatsResponse>("/api/datasets/ddi2013/stats"),
  ddiExamples: (p: { split?: string; label?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (p.split) q.set("split", p.split);
    if (p.label) q.set("label", p.label);
    q.set("limit", String(p.limit ?? 6));
    return get<DDIExamplesResponse>(`/api/datasets/ddi2013/examples?${q}`);
  },
  dailymedStats: () => get<DailyMedStatsResponse>("/api/datasets/dailymed/stats"),
  tacStats: () => get<TacStatsResponse>("/api/datasets/tac2017/stats"),
  appmsSummary: () => get<AppmsSummaryResponse>("/api/appms/summary"),
  appmsPatients: (p: { q?: string; limit?: number; offset?: number }, signal?: AbortSignal) =>
    get<AppmsPatientsResponse>(
      `/api/appms/patients?${new URLSearchParams({ q: p.q ?? "", limit: String(p.limit ?? 8), offset: String(p.offset ?? 0) })}`,
      signal,
    ),
  appmsPatient: (id: string) => get<AppmsPatientResponse>(`/api/appms/patients/${encodeURIComponent(id)}`),
  appmsLookup: (a: string, b: string) =>
    get<AppmsLookupResponse>(`/api/appms/lookup?${new URLSearchParams({ drug_a: a, drug_b: b })}`),
  trace: () => get<TraceResponse>("/api/trace"),
  suggest: (q: string, signal?: AbortSignal, limit = 8) =>
    get<SuggestResponse>(`/api/medicine/suggest?${new URLSearchParams({ q, limit: String(limit) })}`, signal),
  brand: (id: string) => get<BrandResponse>(`/api/medicine/${encodeURIComponent(id)}`),
  brandAlternatives: (id: string, includeDiscontinued: boolean) =>
    get<BrandAlternativesResponse>(
      `/api/medicine/${encodeURIComponent(id)}/alternatives?${new URLSearchParams({ include_discontinued: String(includeDiscontinued) })}`,
    ),
  catalogueSummary: () => get<CatalogueSummaryResponse>("/api/catalogue/summary"),
  label: (setId: string) => get<MedicineResponse>(`/api/label/${encodeURIComponent(setId)}`),
  labelAlternatives: (setId: string) => get<AlternativesResponse>(`/api/label/${encodeURIComponent(setId)}/alternatives`),
  login: (email: string, password: string) => send<LoginResponse>("POST", "/api/auth/login", { email, password }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  me: () => get<MeResponse>("/api/auth/me"),
  deleteAccount: () => del("/api/account"),
  profile: () => get<ProfileOut>("/api/profile"),
  saveProfile: (b: ProfileIn) => send<ProfileOut>("PUT", "/api/profile", b),
  allergies: () => get<AllergyOut[]>("/api/allergies"),
  addAllergy: (b: AllergyIn) => send<AllergyOut>("POST", "/api/allergies", b),
  saveAllergy: (id: number, b: AllergyIn) => send<AllergyOut>("PUT", `/api/allergies/${id}`, b),
  deleteAllergy: (id: number) => del(`/api/allergies/${id}`),
  conditions: () => get<ConditionOut[]>("/api/conditions"),
  addCondition: (b: ConditionIn) => send<ConditionOut>("POST", "/api/conditions", b),
  saveCondition: (id: number, b: ConditionIn) => send<ConditionOut>("PUT", `/api/conditions/${id}`, b),
  deleteCondition: (id: number) => del(`/api/conditions/${id}`),
  medicineRecords: () => get<MedicineRecordOut[]>("/api/medicine-records"),
  addMedicineRecord: (b: MedicineRecordIn) => send<MedicineRecordOut>("POST", "/api/medicine-records", b),
  saveMedicineRecord: (id: number, b: MedicineRecordIn) => send<MedicineRecordOut>("PUT", `/api/medicine-records/${id}`, b),
  deleteMedicineRecord: (id: number) => del(`/api/medicine-records/${id}`),
  medicineDetails: (id: string) => get<MedicineDetailsResponse>(`/api/medicine/${encodeURIComponent(id)}/details`),
  analyze: (medicines: CourseIn[]) => send<AnalyzeResponse>("POST", "/api/analyze", { medicines }),
  addMedicines: (items: CourseIn[], acknowledgedWarning: boolean) =>
    send<AddMedicinesResponse>("POST", "/api/medicine-records/batch", { items, acknowledged_warning: acknowledgedWarning }),
  check: (catalogueIds: string[], names: string[] = []) =>
    request<CheckerResponse>("/api/checker", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ catalogue_ids: catalogueIds, names }),
    }),
};
