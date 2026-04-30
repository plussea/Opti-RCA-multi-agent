// API client for OmniOps backend

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost";

export async function createSession(file: File): Promise<{ session_id: string; status: string; estimated_seconds: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/v1/sessions`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function getSession(id: string) {
  const res = await fetch(`${BASE}/v1/sessions/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listSessions(): Promise<import("./types").SessionSummary[]> {
  const res = await fetch(`${BASE}/v1/sessions`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function submitFeedback(
  sessionId: string,
  feedback: {
    decision: "adopted" | "modified" | "rejected";
    actual_action: string;
    effectiveness: "resolved" | "partial" | "failed";
  },
) {
  const res = await fetch(`${BASE}/v1/sessions/${sessionId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feedback),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function getSSEUrl(sessionId: string) {
  return `${BASE}/v1/sessions/${sessionId}/stream`;
}
