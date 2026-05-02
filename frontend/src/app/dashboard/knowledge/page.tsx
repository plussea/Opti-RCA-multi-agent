"use client";

import { useEffect, useState, useCallback } from "react";
import { getGraphVisualization } from "~/lib/api";
import { GraphCanvas } from "~/components/GraphCanvas";
import { BuildProgressCard } from "~/components/BuildProgressCard";
import { KnowledgeDocumentList } from "~/components/KnowledgeDocumentList";
import { KnowledgeDocUploader } from "~/components/KnowledgeDocUploader";
import type { KGVisualizationResponse } from "~/lib/types";

export default function KnowledgePage() {
  const [vizResponse, setVizResponse] = useState<KGVisualizationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadGraph = useCallback(() => {
    getGraphVisualization("optical_network")
      .then((data) => setVizResponse(data))
      .catch(() => setVizResponse(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph, refreshKey]);

  const stats = vizResponse?.stats;
  const allElements = vizResponse
    ? [...vizResponse.elements.nodes, ...vizResponse.elements.edges]
    : [];
  const selectedEl = selectedNode && vizResponse
    ? vizResponse.elements.nodes.find((e) => e.data.id === selectedNode)
    : null;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-zinc-100">知识图谱管理</h1>
        <p className="text-sm text-zinc-500 mt-1">GraphRAG — 光网络告警领域知识库</p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: graph + node detail */}
        <div className="col-span-2 space-y-4">
          <div className="border border-zinc-800 rounded-lg bg-zinc-900/30 p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-zinc-200">图谱可视化</h2>
              {stats && (
                <div className="flex gap-3 text-xs text-zinc-500">
                  <span className="font-mono">{stats.node_count} 节点</span>
                  <span>·</span>
                  <span className="font-mono">{stats.edge_count} 边</span>
                  <span>·</span>
                  <span className="font-mono text-cyan-400">{stats.community_count} 社区</span>
                </div>
              )}
            </div>

            {loading ? (
              <div className="h-96 flex items-center justify-center text-zinc-600 text-sm">
                加载中…
              </div>
            ) : allElements.length > 0 ? (
              <GraphCanvas
                elements={allElements}
                stats={stats}
                height={380}
                onNodeClick={(id) => setSelectedNode(id === selectedNode ? null : id)}
              />
            ) : (
              <div className="h-96 flex flex-col items-center justify-center text-zinc-600 text-sm border border-dashed border-zinc-800 rounded">
                <span className="text-3xl mb-2">◉</span>
                图谱为空，请上传知识文档构建图谱
              </div>
            )}
          </div>

          {/* Node detail */}
          {selectedEl && (
            <div className="border border-zinc-800 rounded-lg bg-zinc-900/30 p-4">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider mb-3">节点详情</h3>
              <div className="flex items-center gap-3 mb-3">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: selectedEl.data.color }}
                />
                <span className="text-base font-bold text-zinc-100">{selectedEl.data.label}</span>
                <span className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-400 rounded">
                  {selectedEl.data.nodeType}
                </span>
              </div>
              <div className="text-xs text-zinc-500 font-mono">
                ID: {selectedEl.data.id}
              </div>
            </div>
          )}
        </div>

        {/* Right: controls */}
        <div className="space-y-4">
          <div className="border border-zinc-800 rounded-lg bg-zinc-900/30 p-4">
            <h3 className="text-sm font-semibold text-zinc-200 mb-3">上传知识文档</h3>
            <KnowledgeDocUploader
              onUploadSuccess={() => {
                setLoading(true);
                setRefreshKey((k) => k + 1);
              }}
            />
          </div>
          <BuildProgressCard />
          <KnowledgeDocumentList />
        </div>
      </div>
    </div>
  );
}