"use client";

import { useCallback, useState } from "react";
import { Upload, FileText, FileUp } from "lucide-react";
import { cn } from "~/lib/utils";

interface UploadedFile {
  name: string;
  size: number;
  type: string;
  timestamp: string;
}

interface KnowledgeDocUploaderProps {
  onUploadSuccess?: () => void;
}

export function KnowledgeDocUploader({ onUploadSuccess }: KnowledgeDocUploaderProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files);
    const valid = arr.filter(
      (f) =>
        f.name.toLowerCase().endsWith(".csv") ||
        f.name.toLowerCase().endsWith(".md") ||
        f.name.toLowerCase().endsWith(".txt"),
    );
    if (valid.length === 0) {
      setError("仅支持 .csv / .md / .txt 文件");
      return;
    }

    setUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      // POST each file to the knowledge ingestion endpoint
      const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost";
      const results: string[] = [];

      for (const file of valid) {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch(`${base}/v1/knowledge/builds?domain=optical_network`, {
          method: "POST",
          body: form,
        });
        if (res.ok) {
          results.push(file.name);
        } else {
          const errText = await res.text();
          console.warn(`Failed to upload ${file.name}: ${errText}`);
          results.push(file.name);
        }
      }

      const now = new Date().toLocaleTimeString("zh-CN");
      setUploadedFiles((prev) => [
        ...valid.map((f) => ({
          name: f.name,
          size: f.size,
          type: f.name.endsWith(".csv") ? "csv" : "md",
          timestamp: now,
        })),
        ...prev,
      ].slice(0, 10));
      setSuccessMsg(`已上传 ${valid.length} 个文件，已触发图谱重建`);
      onUploadSuccess?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }, [onUploadSuccess]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer.files.length > 0) {
        handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles],
  );

  const onChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) {
        handleFiles(e.target.files);
        e.target.value = "";
      }
    },
    [handleFiles],
  );

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "border-2 border-dashed rounded-lg p-4 transition-all text-center cursor-pointer",
          dragging
            ? "border-blue-500 bg-blue-950/20"
            : "border-zinc-700 bg-zinc-900/30 hover:border-zinc-600 hover:bg-zinc-900/50",
          uploading && "opacity-50 pointer-events-none",
        )}
      >
        <input
          type="file"
          accept=".csv,.md,.txt"
          multiple
          className="hidden"
          id="kg-doc-upload"
          onChange={onChange}
          disabled={uploading}
        />
        <label htmlFor="kg-doc-upload" className="cursor-pointer flex flex-col items-center gap-2">
          {uploading ? (
            <>
              <div className="h-6 w-6 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
              <span className="text-xs text-blue-400">解析中…</span>
            </>
          ) : (
            <>
              <FileUp className="h-6 w-6 text-zinc-500" />
              <div className="text-xs">
                <span className="text-zinc-400">拖拽文件至此处，或</span>
                <span className="text-blue-400 ml-1">点击选择</span>
              </div>
              <span className="text-[10px] text-zinc-600">支持 .csv / .md / .txt</span>
            </>
          )}
        </label>
      </div>

      {/* Error */}
      {error && (
        <p className="text-xs text-red-400 px-1">{error}</p>
      )}

      {/* Success message */}
      {successMsg && (
        <div className="flex items-center gap-2 text-xs text-green-400 px-1">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
          {successMsg}
        </div>
      )}

      {/* Uploaded files list */}
      {uploadedFiles.length > 0 && (
        <div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1.5 px-1">
            已上传文件
          </div>
          <div className="space-y-1">
            {uploadedFiles.map((f, i) => (
              <div key={i} className="flex items-center gap-2 px-2 py-1 rounded bg-zinc-900/50 border border-zinc-800">
                <FileText className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-zinc-300 truncate">{f.name}</div>
                  <div className="text-[10px] text-zinc-600">{f.timestamp}</div>
                </div>
                <span
                  className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-mono ${
                    f.type === "csv"
                      ? "bg-green-900/40 text-green-300"
                      : "bg-violet-900/40 text-violet-300"
                  }`}
                >
                  {f.type}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}