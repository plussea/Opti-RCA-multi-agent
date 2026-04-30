"use client";

import { useCallback, useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "~/components/ui/button";
import { createSession } from "~/lib/api";
import { useSessionStore } from "~/store/sessionStore";
import { cn } from "~/lib/utils";

interface UploadZoneProps {
  className?: string;
}

export function UploadZone({ className }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { setSessions } = useSessionStore();

  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Only CSV files are supported");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await createSession(file);
      // Refresh session list after short delay
      setTimeout(async () => {
        const { listSessions } = await import("~/lib/api");
        const sessions = await listSessions();
        setSessions(sessions);
      }, 1000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [setSessions]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const onChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      e.target.value = "";
    },
    [handleFile],
  );

  return (
    <div className={cn("p-3 border-b border-zinc-800", className)}>
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-zinc-700 bg-zinc-950 p-4 cursor-pointer transition-all",
          dragging && "border-blue-500 bg-blue-950/20",
          uploading && "opacity-50 pointer-events-none",
          "hover:border-zinc-500 hover:bg-zinc-900",
        )}
      >
        <Upload className="h-5 w-5 text-zinc-500" />
        <span className="text-xs text-zinc-400 text-center">
          {uploading ? "分析中…" : "拖拽 CSV 或点击上传"}
        </span>
        <input
          type="file"
          accept=".csv"
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          onChange={onChange}
          disabled={uploading}
        />
      </label>
      {error && (
        <p className="mt-2 text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}
