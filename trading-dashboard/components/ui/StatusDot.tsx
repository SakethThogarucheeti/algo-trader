"use client";

import { T } from "@/lib/echarts";

interface StatusDotProps {
  status: "live" | "reconnecting" | "connecting";
}

const STATUS_COLOR: Record<StatusDotProps["status"], string> = {
  live: T.pos,
  reconnecting: T.neg,
  connecting: T.muted,
};

export function StatusDot({ status }: StatusDotProps) {
  const color = STATUS_COLOR[status];
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          backgroundColor: color,
          boxShadow: status === "live" ? `0 0 6px ${color}` : "none",
        }}
      />
      <span style={{ color, fontSize: 11, fontFamily: "ui-monospace, monospace" }}>{status}</span>
    </span>
  );
}
