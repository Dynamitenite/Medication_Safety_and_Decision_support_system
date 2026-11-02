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
export type Suggestion = S["Suggestion"];
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
export type Readiness = { status: "ready" | "not_ready"; reason?: string | null; fix?: string | null };

const BASE: string = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
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
      const body = await res.json();
      if (typeof body?.detail === "string") detail = `: ${body.detail}`;
    } catch {
      /* no JSON body */
    }
    throw new ApiError(`API returned ${res.status} for ${path}${detail}`);
  }
  return (await res.json()) as T;
}

const get = <T,>(path: string, signal?: AbortSignal) => request<T>(path, { signal });

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
  medicine: (id: string) => get<MedicineResponse>(`/api/medicine/${encodeURIComponent(id)}`),
  alternatives: (id: string) => get<AlternativesResponse>(`/api/medicine/${encodeURIComponent(id)}/alternatives`),
  check: (setIds: string[]) =>
    request<CheckerResponse>("/api/checker", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ set_ids: setIds }),
    }),
};
