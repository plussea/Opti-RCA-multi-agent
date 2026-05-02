"use client";

import type { KGRule } from "~/lib/types";

interface RuleCardProps {
  rule: KGRule;
}

export function RuleCard({ rule }: RuleCardProps) {
  return (
    <div className="p-3 border border-zinc-800 rounded bg-zinc-900/30">
      <div className="flex items-center gap-2 mb-2">
        <span className="px-1.5 py-0.5 text-[10px] bg-violet-900/40 text-violet-300 rounded border border-violet-800 font-mono font-bold">
          RULE
        </span>
        <span className="text-sm font-semibold text-zinc-200">{rule.name}</span>
      </div>
      <p className="text-xs text-zinc-400 leading-relaxed">{rule.content}</p>
      {rule.applicable_alarms?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          <span className="text-[10px] text-zinc-600 self-center">适用告警:</span>
          {rule.applicable_alarms.map((a) => (
            <span
              key={a}
              className="px-1.5 py-0.5 text-[10px] bg-red-900/30 text-red-300 rounded border border-red-800 font-mono"
            >
              {a}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
