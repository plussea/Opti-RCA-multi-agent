// API client for OmniOps backend
import type {
  KGGraphStats,
  KGVisualizationResponse,
} from "./types";

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

// ── Knowledge Graph API ────────────────────────────────────────────────────────

export async function buildKnowledgeGraph(domain = "optical_network") {
  const form = new FormData();
  form.append("file", new Blob([], { type: "application/octet-stream" }), "");
  form.append("domain", domain);
  const res = await fetch(`${BASE}/v1/knowledge/builds?domain=${domain}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ build_id: string; status: string }>;
}

export async function getBuildStatus(buildId: string) {
  const res = await fetch(`${BASE}/v1/knowledge/builds/${buildId}/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getGraphMetadata(domain = "optical_network") {
  const res = await fetch(`${BASE}/v1/knowledge/graphs/${domain}/metadata`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function queryKnowledgeGraph(
  structuredData: unknown[],
  hops = 2,
) {
  const res = await fetch(`${BASE}/v1/knowledge/graph/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ structured_data: structuredData, hops }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getGraphVisualization(domain = "optical_network") {
  const res = await fetch(`${BASE}/v1/knowledge/graph/visualization?domain=${domain}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<KGVisualizationResponse>;
}

export async function clearGraph(domain = "optical_network") {
  const res = await fetch(`${BASE}/v1/knowledge/graphs/${domain}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
