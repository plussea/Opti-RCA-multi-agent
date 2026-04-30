"use client";

import useSWR from "swr";
import { listSessions, getSession } from "~/lib/api";
import { useSessionStore } from "~/store/sessionStore";
import { Badge } from "~/components/ui/badge";
import { ScrollArea } from "~/components/ui/scroll-area";
import type { SessionStatus } from "~/lib/types";

const STATUS_COLORS: Record<SessionStatus, string> = {
  analyzing: "bg-blue-900 text-blue-200",
  diagnosing: "bg-blue-900 text-blue-200 animate-pulse",
  planning: "bg-blue-900 text-blue-200",
  verifying: "bg-blue-900 text-blue-200",
  pending_human: "bg-orange-900 text-orange-200",
  approved: "bg-green-900 text-green-200",
  rejected: "bg-red-900 text-red-200",
  resolved: "bg-green-900 text-green-200",
  completed: "bg-green-900 text-green-200",
  failed: "bg-red-900 text-red-200",
  escalated: "bg-red-900 text-red-200",
  perceived: "bg-blue-900 text-blue-200",
  needs_review: "bg-orange-900 text-orange-200",
};

export function SessionList() {
  const { sessions, setSessions, setActive, activeSessionId } = useSessionStore();

  const { data, isLoading } = useSWR("sessions", listSessions, {
    refreshInterval: 5000,
    onSuccess: (newSessions) => {
      if (JSON.stringify(newSessions) !== JSON.stringify(sessions)) {
        setSessions(newSessions);
      }
    },
  });

  const handleSelect = async (sessionId: string) => {
    if (sessionId === activeSessionId) return;
    try {
      const session = await getSession(sessionId);
      setActive(sessionId, session);
    } catch {
      // ignore
    }
  };

  const displayedSessions = data ?? sessions;

  return (
    <ScrollArea className="flex-1">
      <div className="p-3 flex flex-col gap-2">
        <div className="text-xs font-semibold text-zinc-500 px-2 uppercase tracking-wider">
          案件列表
        </div>
        {isLoading && displayedSessions.length === 0 && (
          <div className="px-2 py-4 text-xs text-zinc-600 text-center">加载中…</div>
        )}
        {displayedSessions.length === 0 && !isLoading && (
          <div className="px-2 py-4 text-xs text-zinc-600 text-center">
            暂无案件，上传 CSV 开始分析
          </div>
        )}
        {displayedSessions.map((s) => (
          <button
            key={s.session_id}
            onClick={() => handleSelect(s.session_id)}
            className={`
              w-full text-left rounded-lg border p-3 transition-all
              hover:border-zinc-600 hover:bg-zinc-900
              ${s.session_id === activeSessionId
                ? "border-blue-600 bg-blue-950/30"
                : "border-zinc-800 bg-zinc-900/50"
              }
            `}
          >
            <div className="flex justify-between items-center gap-2">
              <span className="font-mono text-xs text-zinc-300 truncate flex-1">
                {s.session_id.split("_").slice(1).join("_")}
              </span>
              <Badge
                variant={s.status as SessionStatus}
                className="shrink-0 text-[10px]"
              >
                {s.status}
              </Badge>
            </div>
            {s.root_cause && (
              <div className="mt-1 text-xs text-zinc-500 truncate">{s.root_cause}</div>
            )}
            <div className="mt-1 text-[10px] text-zinc-600">
              {new Date(s.created_at).toLocaleTimeString("zh-CN")} · {s.ne_count} 网元
            </div>
          </button>
        ))}
      </div>
    </ScrollArea>
  );
}
