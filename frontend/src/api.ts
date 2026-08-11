import type { AnalyzeResponse, RaceState } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchState(): Promise<RaceState> {
  const res = await fetch(`${API_BASE}/api/laptimes`);
  if (!res.ok) throw new Error("Failed to load lap data");
  return res.json();
}

export async function analyzeClip(
  file: Blob,
  fileName: string,
  lap?: number,
): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file, fileName);
  if (lap !== undefined) form.append("lap", String(lap));

  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? "Analysis failed");
  }
  return res.json();
}

export async function resetEvents(): Promise<RaceState> {
  const res = await fetch(`${API_BASE}/api/reset`, { method: "POST" });
  if (!res.ok) throw new Error("Reset failed");
  return res.json();
}
