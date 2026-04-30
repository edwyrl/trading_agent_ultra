import type {
  DashboardPayloadDTO,
  SignalPluginMetaDTO,
  SignalRunRequestDTO,
  SignalRunStatus,
  SignalRunStatusDTO,
} from "../types/api";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function listRuns(status?: SignalRunStatus): Promise<SignalRunStatusDTO[]> {
  const query = status ? `?status=${status}` : "";
  return apiFetch<SignalRunStatusDTO[]>(`/api/signals/runs${query}`);
}

export function getRunDashboard(runId: string): Promise<DashboardPayloadDTO> {
  return apiFetch<DashboardPayloadDTO>(`/api/signals/runs/${runId}/dashboard`);
}

export function listPlugins(): Promise<SignalPluginMetaDTO[]> {
  return apiFetch<SignalPluginMetaDTO[]>("/api/signals/plugins");
}

export function createRun(request: SignalRunRequestDTO): Promise<SignalRunStatusDTO> {
  return apiFetch<SignalRunStatusDTO>("/api/signals/runs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
}

export function cancelRun(runId: string): Promise<SignalRunStatusDTO> {
  return apiFetch<SignalRunStatusDTO>(`/api/signals/runs/${runId}/cancel`, {
    method: "POST",
  });
}

export async function deleteRun(runId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/signals/runs/${runId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
}
