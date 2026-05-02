"use client";

import { useEffect, useState } from "react";
import { getGraphVisualization, queryKnowledgeGraph } from "~/lib/api";
import { GraphCanvas } from "~/components/GraphCanvas";
import type { KGQueryResult, KGVisualizationElement, KGGraphStats, KGVisualizationResponse } from "~/lib/types";

interface KnowledgeGraphProps {
  alarmRecords?: unknown[];
  initialKgResult?: KGQueryResult;
  height?: number;
}

export function KnowledgeGraph({ alarmRecords, initialKgResult, height = 300 }: KnowledgeGraphProps) {
  const [vizData, setVizData] = useState<KGVisualizationResponse | null>(null);
  const [kgResult, setKgResult] = useState<KGQueryResult | null>(initialKgResult ?? null);
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"graph" | "communities" | "rules">("graph");

  useEffect(() => {
    setLoading(true);
    getGraphVisualization("optical_network")
      .then((data) => {
        setVizData(data);
      })
      .catch(() => setVizData(null))
      .finally(() => setLoading(false));
  }, []);

  const handleQuery = async () => {
    if (!alarmRecords?.length) return;
    setLoading(true);
    try {
      const result = await queryKnowledgeGraph(alarmRecords, 2);
      setKgResult(result as KGQueryResult);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  const selectedEl = selectedNode && vizData
    ? vizData.elements.nodes.find((e) => e.data.id === selectedNode)
    : null;

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500 font-mono">知识图谱</span>
          {kgResult && (
            <span className="text-[10px] text-zinc-600">
              查询耗时 {(kgResult.query_latency_ms ?? 0).toFixed(0)}ms
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleQuery}
            disabled={loading || !alarmRecords?.length}
            className="px-2.5 py-1 text-xs bg-blue-900/40 text-blue-300 border border-blue-800 rounded hover:bg-blue-900/60 disabled:opacity-40 transition-colors"
          >
            {loading ? "查询中…" : "关联查询"}
          </button>
        </div>
      </div>

      {/* Graph tab */}
      {activeTab === "graph" && (
        <>
          {loading && !vizData ? (
            <div className="h-48 flex items-center justify-center text-zinc-600 text-sm">
              加载图谱…
            </div>
          ) : vizData ? (
            <GraphCanvas
              elements={[...vizData.elements.nodes, ...vizData.elements.edges]}
              stats={vizData.stats ?? undefined}
              height={height}
              onNodeClick={(id) => setSelectedNode(id === selectedNode ? null : id)}
            />
          ) : (
            <div className="h-48 flex items-center justify-center text-zinc-600 text-sm border border-zinc-800 rounded">
              图谱为空，请先构建知识库
            </div>
          )}

          {/* Node detail */}
          {selectedEl && (
            <div className="mt-2 p-3 border border-zinc-800 rounded bg-zinc-900/50">
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: selectedEl.data.color }}
                />
                <span className="text-sm font-semibold text-zinc-200">{selectedEl.data.label}</span>
                <span className="text-xs text-zinc-500">{selectedEl.data.nodeType}</span>
              </div>
            </div>
          )}
        </>
      )}

      {/* Communities tab */}
      {activeTab === "communities" && (
        <div className="space-y-2">
          {kgResult?.community_summaries?.length ? (
            kgResult.community_summaries.map((c) => (
              <div key={c.id} className="p-3 border border-zinc-800 rounded bg-zinc-900/50">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold text-cyan-300">{c.name}</span>
                  <span className="text-xs text-zinc-600">{c.member_count} 实体</span>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">{c.summary}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.entities?.map((e) => (
                    <span key={e} className="px-1.5 py-0.5 text-[10px] bg-zinc-800 text-zinc-400 rounded font-mono">
                      {e}
                    </span>
                  ))}
                </div>
              </div>
            ))
          ) : (
            <p className="text-zinc-600 text-sm py-4 text-center">暂无社区摘要</p>
          )}
        </div>
      )}

      {/* Rules tab */}
      {activeTab === "rules" && (
        <div className="space-y-2">
          {kgResult?.rules?.length ? (
            kgResult.rules.map((r) => (
              <div key={r.id} className="p-3 border border-zinc-800 rounded bg-zinc-900/50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs px-1.5 py-0.5 bg-violet-900/40 text-violet-300 rounded border border-violet-800 font-mono">
                    RULE
                  </span>
                  <span className="text-sm font-semibold text-zinc-200">{r.name}</span>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">{r.content}</p>
                {r.applicable_alarms?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {r.applicable_alarms.map((a) => (
                      <span key={a} className="px-1.5 py-0.5 text-[10px] bg-red-900/30 text-red-300 rounded border border-red-800 font-mono">
                        {a}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          ) : (
            <p className="text-zinc-600 text-sm py-4 text-center">暂无诊断规则</p>
          )}
        </div>
      )}

      {/* Tab switcher (inline for compact use) */}
      <div className="flex border-b border-zinc-800 -mb-1">
        {(["graph", "communities", "rules"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              activeTab === tab
                ? "text-zinc-100 border-b-2 border-blue-500"
                : "text-zinc-500 hover:text-zinc-300 border-b-2 border-transparent"
            }`}
          >
            {tab === "graph" ? "图谱" : tab === "communities" ? "社区" : "规则"}
          </button>
        ))}
      </div>
    </div>
  );
}
