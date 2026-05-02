// ── Shared types mirroring backend Session model ──────────────────────────────

export type SessionStatus =
  | "perceived"
  | "diagnosing"
  | "planning"
  | "verifying"
  | "pending_human"
  | "approved"
  | "rejected"
  | "resolved"
  | "completed"
  | "failed"
  | "escalated"
  | "analyzing"
  | "needs_review";

export interface AlarmRecord {
  ne_name: string;
  alarm_code?: string;
  alarm_name?: string;
  severity?: string;
  occur_time?: string;
  shelf?: string;
  slot?: string;
  board_type?: string;
  raw_data: Record<string, unknown>;
}

export interface Evidence {
  type: string;
  source: string;
  code?: string;
  field?: string;
  value?: string;
}

export interface DiagnosisResult {
  root_cause: string;
  confidence: number;
  evidence: Evidence[];
  uncertainty?: string;
  agent_chain: string[];
}

export interface SuggestionAction {
  step: number;
  action: string;
  estimated_time?: string;
  service_impact?: string;
}

export interface Suggestion {
  root_cause: string;
  suggested_actions: SuggestionAction[];
  required_tools: string[];
  fallback_plan?: string;
  risk_level: string;
  needs_approval: boolean;
}

export interface Impact {
  affected_links: string[];
  affected_services: string[];
  affected_ne: string[];
}

export interface Session {
  session_id: string;
  input_type: "csv" | "image" | "pdf";
  structured_data: AlarmRecord[];
  diagnosis_result?: DiagnosisResult;
  impact?: Impact;
  suggestion?: Suggestion;
  human_feedback?: Record<string, unknown>;
  status: SessionStatus;
  current_step: string;
  created_at: string;
}

// Lightweight session summary returned by GET /v1/sessions
export interface SessionSummary {
  session_id: string;
  status: SessionStatus;
  current_step: string;
  created_at: string;
  input_type: "csv" | "image" | "pdf";
  ne_count: number;
  root_cause?: string;
}

export type PipelineStep =
  | "init"
  | "perceived"
  | "diagnosing"
  | "planning"
  | "verifying"
  | "pending_human"
  | "resolved";

export type NodeState = "waiting" | "running" | "completed" | "pending_human" | "failed";

const STEP_ORDER: PipelineStep[] = [
  "init",
  "perceived",
  "diagnosing",
  "planning",
  "verifying",
  "pending_human",
  "resolved",
];

export function getNodeState(
  status: SessionStatus,
  currentStep: string,
  nodeStep: PipelineStep,
): NodeState {
  if (status === "failed" || status === "escalated") return "failed";
  const currentIdx = STEP_ORDER.indexOf(currentStep as PipelineStep);
  const nodeIdx = STEP_ORDER.indexOf(nodeStep);
  if (currentIdx < nodeIdx) return "waiting";
  if (currentIdx === nodeIdx) {
    if (status === "pending_human") return "pending_human";
    return "running";
  }
  return "completed";
}

export const PIPELINE_NODES: { step: PipelineStep; label: string; icon: string }[] = [
  { step: "perceived", label: "Perception", icon: "📄" },
  { step: "diagnosing", label: "Diagnosis", icon: "🔍" },
  { step: "planning", label: "Impact + Planning", icon: "💡" },
  { step: "verifying", label: "Verification", icon: "✓" },
  { step: "pending_human", label: "Human Review", icon: "👤" },
];

// ── Knowledge Graph types ──────────────────────────────────────────────────────

export interface KGNode {
  id: string;
  label: string;
  type: "Alarm" | "Fault" | "Device" | "Topology" | "Rule" | "Community";
  props: Record<string, unknown>;
}

export interface KGEdge {
  source: string;
  target: string;
  relation: string;
  props?: Record<string, unknown>;
}

export interface SubgraphPath {
  path: string[];
  relations: string[];
  description: string;
}

export interface CommunitySummary {
  id: string;
  name: string;
  summary: string;
  member_count: number;
  entities: string[];
}

export interface KGRule {
  id: string;
  name: string;
  content: string;
  applicable_alarms: string[];
}

export interface KGQueryResult {
  subgraph_paths: SubgraphPath[];
  community_summaries: CommunitySummary[];
  rules: KGRule[];
  query_latency_ms: number;
  seed_entities: string[];
  subgraph_stats: { nodes: number; edges: number };
  fallback?: string;
}

export interface KGGraphData {
  nodes: KGNode[];
  edges: KGEdge[];
}

export interface KGGraphStats {
  node_count: number;
  edge_count: number;
  community_count: number;
  alarm_count: number;
  fault_count: number;
  device_count: number;
}

export interface KGVisualizationElement {
  data: {
    id: string;
    label?: string;
    nodeType?: KGNode["type"];
    color?: string;
    size?: number;
    source?: string;
    target?: string;
  };
}

export interface KGVisualizationResponse {
  elements: {
    nodes: KGVisualizationElement[];
    edges: KGVisualizationElement[];
  };
  layout?: string;
  stats?: KGGraphStats;
}

export interface GraphBuildStatus {
  build_id: string;
  status: "building" | "completed" | "failed";
  stats: {
    nodes_created: number;
    relations_created: number;
    communities_found: number;
    parse_errors: number;
  };
  started_at: string;
  completed_at?: string;
  error?: string;
}
