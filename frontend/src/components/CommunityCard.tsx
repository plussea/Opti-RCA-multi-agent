"use client";

import type { CommunitySummary } from "~/lib/types";

interface CommunityCardProps {
  community: CommunitySummary;
  onClick?: () => void;
}

export function CommunityCard({ community, onClick }: CommunityCardProps) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 border border-zinc-800 rounded bg-zinc-900/30 hover:bg-zinc-900/60 hover:border-cyan-800 transition-colors"
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-cyan-500" />
          <span className="text-sm font-semibold text-cyan-200">{community.name}</span>
        </div>
        <span className="text-xs text-zinc-600">{community.member_count} 实体</span>
      </div>
      <p className="text-xs text-zinc-400 leading-relaxed line-clamp-2">{community.summary}</p>
      {community.entities?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {community.entities.slice(0, 6).map((e) => (
            <span
              key={e}
              className="px-1.5 py-0.5 text-[10px] bg-zinc-800 text-zinc-400 rounded font-mono"
            >
              {e}
            </span>
          ))}
          {community.entities.length > 6 && (
            <span className="text-[10px] text-zinc-600">+{community.entities.length - 6}</span>
          )}
        </div>
      )}
    </button>
  );
}
