"use client";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "~/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { useSessionStore } from "~/store/sessionStore";
import { AuditCard } from "./AuditCard";
import { EvidenceTable } from "./EvidenceTable";
import { KnowledgeGraph } from "~/components/KnowledgeGraph";
import type { Session } from "~/lib/types";

function DiagnosisPanel({ session }: { session: Session }) {
  const d = session.diagnosis_result;
  if (!d) {
    return <p className="text-zinc-500 text-sm p-4">等待诊断结果…</p>;
  }
  return (
    <Tabs defaultValue="evidence" className="w-full">
      <TabsList>
        <TabsTrigger value="evidence">诊断证据</TabsTrigger>
        <TabsTrigger value="knowledge">知识图谱</TabsTrigger>
      </TabsList>

      <TabsContent value="evidence">
        <div className="space-y-4 p-4">
          <div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">根因结论</div>
            <div className="text-base font-semibold text-zinc-100">{d.root_cause}</div>
          </div>
          <div className="flex items-center gap-4">
            <div>
              <div className="text-xs text-zinc-500">置信度</div>
              <div className="text-lg font-bold font-mono text-green-400">
                {(d.confidence * 100).toFixed(0)}%
              </div>
            </div>
            {d.uncertainty && (
              <div>
                <div className="text-xs text-zinc-500">不确定性</div>
                <div className="text-sm text-orange-400">{d.uncertainty}</div>
              </div>
            )}
          </div>
          {d.evidence.length > 0 && (
            <div>
              <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">证据链</div>
              <div className="space-y-2">
                {d.evidence.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-zinc-600 mt-0.5">›</span>
                    <div>
                      <span className="text-zinc-300">{e.source}</span>
                      {e.code && <span className="text-zinc-500 ml-1 font-mono text-xs">{e.code}</span>}
                      {e.value && <span className="text-zinc-400 ml-1">{e.value}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {d.agent_chain.length > 0 && (
            <div>
              <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">调用链</div>
              <div className="flex flex-wrap gap-1">
                {d.agent_chain.map((agent) => (
                  <span
                    key={agent}
                    className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-400 rounded font-mono"
                  >
                    {agent}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </TabsContent>

      <TabsContent value="knowledge">
        <div className="p-4">
          <KnowledgeGraph alarmRecords={session.structured_data} height={320} />
        </div>
      </TabsContent>
    </Tabs>
  );
}

function PlanningPanel({ session }: { session: Session }) {
  const s = session.suggestion;
  if (!s) return <p className="text-zinc-500 text-sm p-4">等待方案生成…</p>;
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-3">
        <span
          className={`px-2 py-1 rounded text-xs font-bold uppercase ${
            s.risk_level === "high"
              ? "bg-red-900 text-red-300"
              : s.risk_level === "medium"
              ? "bg-orange-900 text-orange-300"
              : "bg-green-900 text-green-300"
          }`}
        >
          {s.risk_level}
        </span>
        {s.needs_approval && (
          <span className="px-2 py-1 rounded text-xs bg-orange-900/50 text-orange-300">
            需人工审核
          </span>
        )}
      </div>
      <div>
        <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">修复步骤</div>
        <div className="space-y-3">
          {s.suggested_actions.map((a) => (
            <div key={a.step} className="border-l-2 border-zinc-700 pl-3">
              <div className="text-sm font-medium text-zinc-200">
                Step {a.step}: {a.action}
              </div>
              <div className="flex gap-4 mt-1">
                {a.estimated_time && (
                  <span className="text-xs text-zinc-500">⏱ {a.estimated_time}</span>
                )}
                {a.service_impact && (
                  <span className="text-xs text-zinc-500">⚡ {a.service_impact}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
      {s.required_tools.length > 0 && (
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">所需工具</div>
          <div className="flex flex-wrap gap-1">
            {s.required_tools.map((tool) => (
              <span
                key={tool}
                className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-400 rounded"
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ImpactPanel({ session }: { session: Session }) {
  const imp = session.impact;
  if (!imp) return <p className="text-zinc-500 text-sm p-4">等待影响评估…</p>;
  return (
    <div className="space-y-4 p-4">
      {imp.affected_ne.length > 0 && (
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">受影响网元</div>
          <div className="flex flex-wrap gap-1">
            {imp.affected_ne.map((ne) => (
              <span key={ne} className="px-2 py-1 text-xs bg-red-900/30 text-red-300 rounded border border-red-800 font-mono">
                {ne}
              </span>
            ))}
          </div>
        </div>
      )}
      {imp.affected_links.length > 0 && (
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">受影响链路</div>
          <div className="flex flex-wrap gap-1">
            {imp.affected_links.map((link) => (
              <span key={link} className="px-2 py-1 text-xs bg-orange-900/30 text-orange-300 rounded border border-orange-800 font-mono">
                {link}
              </span>
            ))}
          </div>
        </div>
      )}
      {imp.affected_services.length > 0 && (
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">受影响业务</div>
          <div className="flex flex-wrap gap-1">
            {imp.affected_services.map((svc) => (
              <span key={svc} className="px-2 py-1 text-xs bg-zinc-800 text-zinc-300 rounded">
                {svc}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function renderContent(session: Session, step: string | null) {
  switch (step) {
    case "perceived":
      return <EvidenceTable records={session.structured_data} />;
    case "diagnosing":
      return <DiagnosisPanel session={session} />;
    case "planning":
      return <PlanningPanel session={session} />;
    case "verifying":
      return (
        <div className="p-4 text-sm text-zinc-400">
          {session.suggestion ? "✓ 方案自洽性校验通过" : "等待方案生成后进行校验…"}
        </div>
      );
    case "pending_human":
      return <AuditCard session={session} />;
    default:
      return (
        <div className="p-4 text-sm text-zinc-600">
          选择节点查看详情
        </div>
      );
  }
}

export function DetailDrawer() {
  const { activeSession, selectedNode, setSelectedNode } = useSessionStore();

  return (
    <Sheet
      open={!!selectedNode}
      onOpenChange={(open) => !open && setSelectedNode(null)}
    >
      <SheetContent
        side="right"
        className="bg-zinc-950 text-zinc-100 border-zinc-800 w-[440px] flex flex-col"
      >
        <SheetHeader className="shrink-0">
          <SheetTitle className="text-zinc-100">
            {selectedNode
              ? selectedNode
                  .replace("pending_human", "human_review")
                  .replace(/_/g, " ")
                  .toUpperCase()
              : ""}
          </SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto">
          {activeSession && selectedNode
            ? renderContent(activeSession, selectedNode)
            : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
