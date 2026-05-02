"use client";

import { useEffect, useState } from "react";
import { getBuildStatus, buildKnowledgeGraph } from "~/lib/api";
import type { GraphBuildStatus } from "~/lib/types";

export function BuildProgressCard() {
  const [buildStatus, setBuildStatus] = useState<GraphBuildStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const poll = async () => {
    if (!buildStatus?.build_id) return;
    try {
      const status = await getBuildStatus(buildStatus.build_id) as GraphBuildStatus;
      setBuildStatus(status);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (!buildStatus || buildStatus.status === "completed" || buildStatus.status === "failed") return;
    const timer = setTimeout(poll, 2000);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildStatus?.build_id, buildStatus?.status]);

  const handleBuild = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await buildKnowledgeGraph("optical_network") as { build_id: string; status: string };
      setBuildStatus({
        build_id: result.build_id,
        status: "building",
        stats: { nodes_created: 0, relations_created: 0, communities_found: 0, parse_errors: 0 },
        started_at: new Date().toISOString(),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "构建失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 border border-zinc-800 rounded bg-zinc-900/50">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-200">图谱构建</h3>
        {buildStatus && (
          <span
            className={`text-xs px-2 py-0.5 rounded font-mono ${
              buildStatus.status === "completed"
                ? "bg-green-900/40 text-green-300"
                : buildStatus.status === "failed"
                ? "bg-red-900/40 text-red-300"
                : "bg-blue-900/40 text-blue-300"
            }`}
          >
            {buildStatus.status === "building" ? "构建中…" : buildStatus.status}
          </span>
        )}
      </div>

      {buildStatus?.status === "building" && (
        <div className="mb-3 space-y-1.5">
          <div className="flex justify-between text-xs text-zinc-500">
            <span>节点</span>
            <span className="font-mono text-zinc-300">{buildStatus.stats.nodes_created}</span>
          </div>
          <div className="w-full h-1 bg-zinc-800 rounded overflow-hidden">
            <div className="h-full bg-blue-500 animate-pulse" style={{ width: "60%" }} />
          </div>
          <div className="flex justify-between text-xs text-zinc-500">
            <span>关系</span>
            <span className="font-mono text-zinc-300">{buildStatus.stats.relations_created}</span>
          </div>
          <div className="flex justify-between text-xs text-zinc-500">
            <span>社区</span>
            <span className="font-mono text-cyan-300">{buildStatus.stats.communities_found}</span>
          </div>
        </div>
      )}

      {buildStatus?.status === "completed" && (
        <div className="mb-3 grid grid-cols-3 gap-2 text-center">
          <div className="p-2 bg-zinc-800/50 rounded">
            <div className="text-lg font-bold font-mono text-zinc-100">{buildStatus.stats.nodes_created}</div>
            <div className="text-[10px] text-zinc-500">节点</div>
          </div>
          <div className="p-2 bg-zinc-800/50 rounded">
            <div className="text-lg font-bold font-mono text-zinc-100">{buildStatus.stats.relations_created}</div>
            <div className="text-[10px] text-zinc-500">关系</div>
          </div>
          <div className="p-2 bg-zinc-800/50 rounded">
            <div className="text-lg font-bold font-mono text-cyan-300">{buildStatus.stats.communities_found}</div>
            <div className="text-[10px] text-zinc-500">社区</div>
          </div>
        </div>
      )}

      {error && <p className="mb-2 text-xs text-red-400">{error}</p>}

      <button
        onClick={handleBuild}
        disabled={loading || buildStatus?.status === "building"}
        className="w-full py-2 text-sm bg-blue-900/40 border border-blue-800 text-blue-300 rounded hover:bg-blue-900/60 disabled:opacity-40 transition-colors"
      >
        {loading ? "启动中…" : buildStatus ? "重新构建" : "构建知识图谱"}
      </button>
    </div>
  );
}
