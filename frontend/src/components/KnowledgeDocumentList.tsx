"use client";

import { useEffect, useState } from "react";
import { getGraphMetadata, clearGraph } from "~/lib/api";
import type { KGGraphStats } from "~/lib/types";

const KNOWLEDGE_FILES = [
  {
    name: "optical_network_knowledge.md",
    label: "光网络告警知识库",
    description: "告警码、故障类型、设备型号、诊断规则、三元组关系",
    path: "/app/input/data/knowledge/optical_network_knowledge.md",
  },
];

export function KnowledgeDocumentList() {
  const [stats, setStats] = useState<KGGraphStats | null>(null);
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared] = useState(false);

  const loadStats = () => {
    getGraphMetadata("optical_network")
      .then((data) => setStats(data as KGGraphStats))
      .catch(() => setStats(null));
  };

  useEffect(() => {
    loadStats();
  }, []);

  const handleClear = async () => {
    if (!confirm("确定清空当前域的知识图谱？")) return;
    setClearing(true);
    try {
      await clearGraph("optical_network");
      setCleared(true);
      loadStats();
      setTimeout(() => setCleared(false), 2000);
    } catch {
      // ignore
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-200">知识文档</h3>
        {cleared && <span className="text-xs text-green-400">已清空</span>}
      </div>

      <div className="space-y-2">
        {KNOWLEDGE_FILES.map((file) => (
          <div
            key={file.name}
            className="p-3 border border-zinc-800 rounded bg-zinc-900/30"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-zinc-200">{file.label}</span>
              <span className="text-[10px] text-zinc-600 font-mono">md</span>
            </div>
            <p className="text-xs text-zinc-500">{file.description}</p>
          </div>
        ))}
      </div>

      {stats && (
        <div className="p-3 border border-zinc-800 rounded bg-zinc-900/30">
          <div className="text-xs text-zinc-500 mb-2">图谱统计</div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span className="text-zinc-500">Alarm</span>
              <span className="font-mono text-red-300">{stats.alarm_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Fault</span>
              <span className="font-mono text-blue-300">{stats.fault_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Device</span>
              <span className="font-mono text-green-300">{stats.device_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">社区</span>
              <span className="font-mono text-cyan-300">{stats.community_count ?? 0}</span>
            </div>
          </div>
        </div>
      )}

      <button
        onClick={handleClear}
        disabled={clearing}
        className="w-full py-2 text-xs text-red-400 border border-red-900/50 rounded hover:bg-red-900/20 disabled:opacity-40 transition-colors"
      >
        {clearing ? "清空中…" : "清空图谱"}
      </button>
    </div>
  );
}
