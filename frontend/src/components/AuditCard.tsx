"use client";

import { useState } from "react";
import { CheckCircle, XCircle, Edit3, Send } from "lucide-react";
import { Button } from "~/components/ui/button";
import { useSessionStore } from "~/store/sessionStore";
import { submitFeedback } from "~/lib/api";
import type { Session } from "~/lib/types";

interface AuditCardProps {
  session: Session;
}

export function AuditCard({ session }: AuditCardProps) {
  const [loading, setLoading] = useState<string | null>(null);
  const [action, setAction] = useState("");
  const { updateActive } = useSessionStore();

  const d = session.diagnosis_result;
  const s = session.suggestion;

  const handleDecision = async (decision: "adopted" | "modified" | "rejected") => {
    setLoading(decision);
    try {
      await submitFeedback(session.session_id, {
        decision,
        actual_action: action || (decision === "adopted" ? "采纳系统建议" : decision === "rejected" ? "驳回方案" : "修改方案"),
        effectiveness: "resolved",
      });
      updateActive({ status: decision === "adopted" ? "approved" : decision === "rejected" ? "rejected" : "completed" });
    } catch (e) {
      console.error("Feedback failed:", e);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-4 p-4">
      {/* Summary header */}
      <div className="rounded-lg bg-orange-950/30 border border-orange-800 p-3">
        <div className="text-xs text-orange-400 uppercase tracking-wider mb-2">⚠ 人工审核请求</div>
        {d && (
          <div className="text-sm font-medium text-zinc-200">
            根因: {d.root_cause}
            <span className="ml-2 text-xs text-green-400 font-mono">
              {(d.confidence * 100).toFixed(0)}% 置信
            </span>
          </div>
        )}
        {s && (
          <div className="mt-1 text-xs text-zinc-400">
            风险: {s.risk_level} · {s.suggested_actions.length} 步操作
          </div>
        )}
      </div>

      {/* Action summary */}
      {s && (
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">建议修复方案</div>
          <div className="space-y-2">
            {s.suggested_actions.map((a) => (
              <div key={a.step} className="flex items-start gap-2 text-sm">
                <span className="text-zinc-600 mt-0.5 shrink-0">{a.step}.</span>
                <span className="text-zinc-300">{a.action}</span>
                {a.estimated_time && (
                  <span className="text-xs text-zinc-500 ml-auto shrink-0">⏱ {a.estimated_time}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action modifier */}
      <div>
        <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">
          {loading === "modified" ? "修改意见（已选中）" : "补充意见（可选）"}
        </div>
        <textarea
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="例如：先尝试清洁端面，无效再 OTDR"
          className="w-full bg-zinc-900 border border-zinc-700 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 resize-none focus:outline-none focus:border-orange-600 focus:ring-1 focus:ring-orange-600"
          rows={3}
          disabled={!!loading}
        />
      </div>

      {/* Action buttons */}
      <div className="grid grid-cols-2 gap-2">
        <Button
          variant="outline"
          className="border-green-700 text-green-400 hover:bg-green-950 hover:text-green-300"
          onClick={() => handleDecision("adopted")}
          disabled={!!loading}
        >
          {loading === "adopted" ? "提交中…" : (
            <><CheckCircle className="h-4 w-4 mr-1" /> 采纳方案</>
          )}
        </Button>
        <Button
          variant="outline"
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          onClick={() => handleDecision("modified")}
          disabled={!!loading}
        >
          {loading === "modified" ? "提交中…" : (
            <><Edit3 className="h-4 w-4 mr-1" /> 修改方案</>
          )}
        </Button>
        <Button
          variant="outline"
          className="border-red-800 text-red-400 hover:bg-red-950 hover:text-red-300"
          onClick={() => handleDecision("rejected")}
          disabled={!!loading}
        >
          {loading === "rejected" ? "提交中…" : (
            <><XCircle className="h-4 w-4 mr-1" /> 驳回</>
          )}
        </Button>
        <Button
          variant="ghost"
          className="text-zinc-500 hover:text-zinc-300"
          disabled={!!loading}
        >
          <Send className="h-4 w-4 mr-1" /> 转交专家
        </Button>
      </div>
    </div>
  );
}
