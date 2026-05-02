"use client";

import type { SubgraphPath } from "~/lib/types";

interface MiniSubgraphProps {
  paths: SubgraphPath[];
  seedEntities?: string[];
}

export function MiniSubgraph({ paths, seedEntities = [] }: MiniSubgraphProps) {
  if (!paths?.length) {
    return <p className="text-zinc-600 text-xs py-2">无关联路径</p>;
  }

  return (
    <div className="space-y-2">
      {seedEntities.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          <span className="text-[10px] text-zinc-600 self-center">种子实体:</span>
          {seedEntities.map((e) => (
            <span key={e} className="px-1.5 py-0.5 text-[10px] bg-blue-900/30 text-blue-300 rounded border border-blue-800 font-mono">
              {e}
            </span>
          ))}
        </div>
      )}
      {paths.map((p, i) => (
        <div key={i} className="flex items-start gap-1.5 text-xs">
          <span className="text-zinc-600 shrink-0 mt-0.5">›</span>
          <div className="flex flex-wrap items-center gap-0.5">
            {p.path.map((node, j) => (
              <span key={j} className="flex items-center gap-0.5">
                <span
                  className={
                    seedEntities.includes(node)
                      ? "px-1 py-0.5 bg-blue-900/40 text-blue-200 rounded font-mono"
                      : "px-1 py-0.5 bg-zinc-800 text-zinc-300 rounded font-mono"
                  }
                >
                  {node}
                </span>
                {j < p.path.length - 1 && (
                  <span className="text-zinc-600 px-0.5">
                    {p.relations[j]?.replace(/_/g, " ") ?? "→"}
                  </span>
                )}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
