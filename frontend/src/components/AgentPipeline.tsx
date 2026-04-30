"use client";

import { PipelineNode } from "./PipelineNode";
import { useSessionStore } from "~/store/sessionStore";
import { getNodeState, PIPELINE_NODES } from "~/lib/types";

export function AgentPipeline() {
  const { activeSession, selectedNode, setSelectedNode } = useSessionStore();

  if (!activeSession) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        选择或新建案件以查看流水线
      </div>
    );
  }

  const status = activeSession.status;
  const currentStep = activeSession.current_step;

  return (
    <div className="flex flex-col gap-0 p-6">
      {PIPELINE_NODES.map((n, i) => {
        const nodeState = getNodeState(
          status as Parameters<typeof getNodeState>[0],
          currentStep,
          n.step,
        );

        // Derive detail from session state
        let detail: string | undefined;
        let confidence: number | undefined;
        if (n.step === "perceived") {
          const count = activeSession.structured_data?.length;
          detail = count ? `${count} 条告警记录` : undefined;
        } else if (n.step === "diagnosing" && activeSession.diagnosis_result) {
          detail = activeSession.diagnosis_result.root_cause;
          confidence = activeSession.diagnosis_result.confidence;
        } else if (n.step === "planning" && activeSession.suggestion) {
          detail = `${activeSession.suggestion.risk_level} 风险 · ${activeSession.suggestion.suggested_actions.length} 步操作`;
        } else if (n.step === "verifying") {
          detail = nodeState === "completed" ? "拓扑校验通过" : undefined;
        } else if (n.step === "pending_human") {
          detail = nodeState === "waiting" ? "等待工程师确认…" : "待审核";
        }

        return (
          <div key={n.step} className="relative">
            <PipelineNode
              step={n.step}
              label={n.label}
              state={nodeState}
              isSelected={selectedNode === n.step}
              onClick={() => setSelectedNode(selectedNode === n.step ? null : n.step)}
              detail={detail}
              confidence={confidence}
              animationDelay={i * 80}
            />
            {i < PIPELINE_NODES.length - 1 && (
              <div
                className="absolute left-1/2 -translate-x-1/2 h-5 w-0.5"
                style={{ top: "100%" }}
              >
                <div
                  className={`w-full h-full ${
                    nodeState === "completed" ? "bg-green-600" : "bg-zinc-800"
                  }`}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
