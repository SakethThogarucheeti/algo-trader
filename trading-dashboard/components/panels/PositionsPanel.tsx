"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchPositions } from "@/lib/api";
import { formatTimeIST, formatRupee } from "@/lib/format";
import { T } from "@/lib/echarts";
import { useDashboardStore } from "@/store";

export function PositionsPanel() {
  const sessionId = useDashboardStore((s) => s.sessionId);
  const { data: positions = [] } = useQuery({
    queryKey: ["positions", sessionId],
    queryFn: () => fetchPositions(sessionId),
    refetchInterval: 5_000,
  });

  return (
    <div style={{ fontFamily: "ui-monospace, monospace" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ color: T.muted }}>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Symbol</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Type</th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Qty</th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Avg Price</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Updated (IST)</th>
          </tr>
        </thead>
        <tbody>
          {positions.length === 0 && (
            <tr>
              <td colSpan={5} style={{ color: T.muted, padding: "8px" }}>
                No data
              </td>
            </tr>
          )}
          {positions.map((p) => (
            <tr key={p.symbol} style={{ borderTop: `1px solid ${T.border}` }}>
              <td style={{ padding: "6px 8px", color: T.text, fontWeight: 600 }}>{p.symbol}</td>
              <td style={{ padding: "6px 8px", color: T.muted }}>{p.instrument_type}</td>
              <td
                style={{
                  padding: "6px 8px",
                  textAlign: "right",
                  color: p.net_qty >= 0 ? T.pos : T.neg,
                  fontWeight: 600,
                }}
              >
                {p.net_qty >= 0 ? "+" : ""}
                {p.net_qty}
              </td>
              <td style={{ padding: "6px 8px", textAlign: "right", color: T.text }}>
                {formatRupee(p.avg_price)}
              </td>
              <td style={{ padding: "6px 8px", color: T.muted }}>
                {p.updated_at ? formatTimeIST(p.updated_at, true) + " IST" : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
