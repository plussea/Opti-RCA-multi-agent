import { create } from "zustand";
import type { Session, SessionSummary } from "~/lib/types";

interface SessionStore {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  activeSession: Session | null;
  selectedNode: string | null;

  setSessions: (sessions: SessionSummary[]) => void;
  setActive: (id: string, session: Session) => void;
  updateActive: (patch: Partial<Session>) => void;
  setSelectedNode: (step: string | null) => void;
  clearActive: () => void;
}

export const useSessionStore = create<SessionStore>((set) => ({
  sessions: [],
  activeSessionId: null,
  activeSession: null,
  selectedNode: null,

  setSessions: (sessions) => set({ sessions }),

  setActive: (id, session) =>
    set({ activeSessionId: id, activeSession: session, selectedNode: null }),

  updateActive: (patch) =>
    set((s) => ({
      activeSession: s.activeSession ? { ...s.activeSession, ...patch } : null,
    })),

  setSelectedNode: (step) => set({ selectedNode: step }),

  clearActive: () =>
    set({ activeSessionId: null, activeSession: null, selectedNode: null }),
}));
