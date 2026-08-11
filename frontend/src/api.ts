import type { CompressResult, SessionPayload, VoiceSession, VoiceStatus } from "./types";

// Same-origin in a built deployment (the API serves the frontend); explicit host in dev.
const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export function fetchSession() {
  return fetch(`${API_BASE}/api/session`).then(unwrap<SessionPayload>);
}

export function analyzeClip(file: Blob, fileName: string, lap?: number) {
  const form = new FormData();
  form.append("file", file, fileName);
  if (lap !== undefined) form.append("lap", String(lap));
  return fetch(`${API_BASE}/api/analyze`, { method: "POST", body: form }).then(unwrap<SessionPayload>);
}

export function addBaselineClip(file: Blob, fileName: string) {
  const form = new FormData();
  form.append("file", file, fileName);
  return fetch(`${API_BASE}/api/baseline`, { method: "POST", body: form }).then(unwrap<SessionPayload>);
}

export function resetSession() {
  return fetch(`${API_BASE}/api/session/reset`, { method: "POST" }).then(unwrap<SessionPayload>);
}

export function resetBaseline() {
  return fetch(`${API_BASE}/api/baseline/reset`, { method: "POST" }).then(unwrap<SessionPayload>);
}

export function compose(message: string, wordBudget: number) {
  return fetch(`${API_BASE}/api/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, wordBudget }),
  }).then(unwrap<CompressResult>);
}

export function voiceStatus() {
  return fetch(`${API_BASE}/api/voice/status`).then(unwrap<VoiceStatus>);
}

export function createVoiceSession(eventId: number | null) {
  return fetch(`${API_BASE}/api/voice/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ eventId }),
  }).then(unwrap<VoiceSession>);
}
