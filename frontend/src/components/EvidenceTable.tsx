"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Badge } from "~/components/ui/badge";
import type { AlarmRecord } from "~/lib/types";

const columns: ColumnDef<AlarmRecord>[] = [
  {
    accessorKey: "ne_name",
    header: "网元",
    cell: ({ row }) => (
      <span className="font-mono text-xs text-zinc-300">{row.getValue("ne_name")}</span>
    ),
  },
  {
    accessorKey: "alarm_code",
    header: "告警码",
    cell: ({ row }) => (
      <span className="font-mono text-xs text-zinc-400">{row.getValue("alarm_code") ?? "—"}</span>
    ),
  },
  {
    accessorKey: "alarm_name",
    header: "告警名称",
    cell: ({ row }) => (
      <span className="text-xs">{row.getValue("alarm_name") ?? "—"}</span>
    ),
  },
  {
    accessorKey: "severity",
    header: "级别",
    cell: ({ row }) => {
      const sev = (row.getValue("severity") as string | undefined) ?? "";
      const upper = sev.toUpperCase();
      return (
        <Badge
          variant={
            upper === "CRITICAL" || upper === "MAJOR"
              ? "destructive"
              : upper === "WARNING"
              ? "pending_human"
              : "secondary"
          }
          className="text-[10px]"
        >
          {sev || "—"}
        </Badge>
      );
    },
  },
  {
    accessorKey: "occur_time",
    header: "发生时间",
    cell: ({ row }) => {
      const t = row.getValue("occur_time") as string | undefined;
      if (!t) return "—";
      try {
        return (
          <span className="text-xs text-zinc-500">
            {new Date(t).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
          </span>
        );
      } catch {
        return t;
      }
    },
  },
];

interface EvidenceTableProps {
  records: AlarmRecord[];
}

export function EvidenceTable({ records }: EvidenceTableProps) {
  if (!records || records.length === 0) {
    return <p className="text-zinc-500 text-sm p-4">暂无告警记录</p>;
  }

  const table = useReactTable({
    data: records,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-zinc-800">
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="text-left text-xs text-zinc-500 uppercase tracking-wider font-medium px-3 py-2"
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="border-b border-zinc-900 hover:bg-zinc-900/50 transition-colors"
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
