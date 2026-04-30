"use client";

import { cn } from "~/lib/utils";
import type { NodeState } from "~/lib/types";

const STATE_STYLES: Record<NodeState, string> = {
  waiting:     "border-zinc-700 bg-zinc-900/50 text-zinc-500",
  running:     "border-blue-500 bg-blue-950/40 text-blue-300 animate-pulse",
  completed:   "border-green-600 bg-green-950/30 text-green-300",
  pending_human:"border-orange-500 bg-orange-950/30 text-orange-300 shadow-[0_0_12px_rgba(234,88,12,0.25)]",
  failed:      "border-red-600 bg-red-950/30 text-red-300",
};

const STATE_ICONS: Record<NodeState, string> = {
  waiting:     "⏸",
  running:     "⚙",
  completed:   "✓",
  pending_human:"👤",
  failed:      "✗",
};

interface PipelineNodeProps {
  step: string;
  label: string;
  state: NodeState;
  isSelected: boolean;
  onClick: () => void;
  confidence?: number;
  detail?: string;
  animationDelay?: number;
}

export function PipelineNode({
  step,
  label,
  state,
  isSelected,
  onClick,
  confidence,
  detail,
  animationDelay = 0,
}: PipelineNodeProps) {
  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${animationDelay}ms` }}
      className={cn(
        "relative w-full rounded-lg border-2 p-4 text-left transition-all duration-300",
        "hover:border-zinc-500 hover:bg-zinc-900/70",
        STATE_STYLES[state],
        isSelected && "ring-2 ring-white/50",
        "animate-fade-in opacity-0",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{STATE_ICONS[state]}</span>
          <div>
            <div className="font-medium text-sm text-zinc-100">{label}</div>
            {detail && (
              <div className="text-xs text-zinc-400 mt-0.5 line-clamp-1">{detail}</div>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-mono">
            {state.replace("_", " ")}
          </span>
          {confidence !== undefined && (
            <span className="text-xs font-mono font-bold text-zinc-300">
              {(confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      {/* Running indicator bar */}
      {state === "running" && (
        <div className="absolute bottom-0 left-0 h-0.5 w-full bg-blue-500/60 animate-pulse rounded-b-lg" />
      )}
    </button>
  );
}
