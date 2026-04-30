"use client";

import { useSSE } from "~/hooks/useSSE";
import { useSessionStore } from "~/store/sessionStore";
import { SessionList } from "~/components/SessionList";
import { AgentPipeline } from "~/components/AgentPipeline";
import { DetailDrawer } from "~/components/DetailDrawer";
import { UploadZone } from "~/components/UploadZone";

function AppContent() {
  const { activeSessionId, activeSession } = useSessionStore();

  // Connect SSE when a session is active
  useSSE({ sessionId: activeSessionId });

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* ── Left panel: header + upload + session list ── */}
      <aside className="w-64 shrink-0 flex flex-col border-r border-zinc-800 bg-zinc-950">
        <div className="px-4 py-4 border-b border-zinc-800">
          <h1 className="font-bold text-base tracking-tight">OmniOps</h1>
          <p className="text-[11px] text-zinc-600 mt-0.5 font-mono">COMMAND CENTER v0.1</p>
        </div>
        <UploadZone />
        <SessionList />
      </aside>

      {/* ── Center panel: agent pipeline ── */}
      <main className="flex-1 flex flex-col min-w-0 border-r border-zinc-800">
        <div className="px-5 py-3 border-b border-zinc-800 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-300">Agent Pipeline</h2>
          {activeSession && (
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-zinc-600">{activeSession.session_id}</span>
              <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto grid-bg">
          <AgentPipeline />
        </div>
      </main>

      {/* ── Right panel: detail drawer ── */}
      <DetailDrawer />
    </div>
  );
}

export default function Home() {
  return <AppContent />;
}
