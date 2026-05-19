"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchSignals } from "@/lib/api";
import { formatTimeIST } from "@/lib/format";
import { T } from "@/lib/echarts";
import { useDashboardStore } from "@/store";

const STEP_COLOR: Record<string, string> = {
  SIGNAL_ACCEPTED: T.pos,
  SIGNAL_REJECTED: T.neg,
  SIGNAL_GENERATED: T.neutral,
};

function contextSummary(ctx: string): string {
  try {
    const obj = JSON.parse(ctx) as Record<string, unknown>;
    if (obj.reason) return String(obj.reason);
    if (obj.qty) return `qty=${obj.qty}`;
    return Object.entries(obj)
      .slice(0, 2)
      .map(([k, v]) => `${k}=${v}`)
      .join(" ");
  } catch {
    return ctx.slice(0, 40);
  }
}

export function SignalsTable() {
  const sessionId = useDashboardStore((s) => s.sessionId);
  const { data: signals = [] } = useQuery({
    queryKey: ["signals", sessionId],
    queryFn: () => fetchSignals(sessionId),
    refetchInterval: 10_000,
  });

  return (
    <div style={{ fontFamily: "ui-monospace, monospace", overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ color: T.muted }}>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Time (IST)</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Symbol</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Algo</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Step</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Context</th>
          </tr>
        </thead>
        <tbody>
          {signals.length === 0 && (
            <tr>
              <td colSpan={5} style={{ color: T.muted, padding: "8px" }}>
                No signals today
              </td>
            </tr>
          )}
          {signals.map((s, i) => (
            <tr key={i} style={{ borderTop: `1px solid ${T.border}` }}>
              <td style={{ padding: "6px 8px", color: T.muted }}>
                {formatTimeIST(s.created_at, true)} IST
              </td>
              <td style={{ padding: "6px 8px", color: T.text, fontWeight: 600 }}>{s.symbol}</td>
              <td style={{ padding: "6px 8px", color: T.muted }}>{s.algo_name}</td>
              <td style={{ padding: "6px 8px" }}>
                <span style={{ color: STEP_COLOR[s.step] ?? T.text }}>{s.step}</span>
              </td>
              <td style={{ padding: "6px 8px", color: T.muted }}>{contextSummary(s.context)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
