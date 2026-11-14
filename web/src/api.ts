import type { Impact, Snapshot } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public body: { error?: string; errors?: string[] }) {
    super(body.error || `HTTP ${status}`);
  }
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const body = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

const q = encodeURIComponent;
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  model: () => call<Snapshot>("/api/model"),
  version: () => call<{ version: string }>("/api/version"),
  file: (path: string) => call<{ path: string; content: string }>(`/api/file?path=${q(path)}`),
  preview: (files: Record<string, string>) => call<Snapshot>("/api/preview", json("POST", { files })),
  save: (path: string, content: string, force = false) => call<Snapshot>("/api/file", json("PUT", { path, content, force })),
  remove: (path: string, force = false) => call<Snapshot>(`/api/file?path=${q(path)}&force=${force ? 1 : 0}`, { method: "DELETE" }),
  impact: (entity: string) => call<Impact>(`/api/impact?entity=${q(entity)}`),
};
