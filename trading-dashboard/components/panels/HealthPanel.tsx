"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/lib/api";
import { formatTimeIST } from "@/lib/format";
import { T } from "@/lib/echarts";

export function HealthPanel() {
  const { data: heartbeats = [] } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5_000,
  });

  return (
    <div style={{ fontFamily: "ui-monospace, monospace" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ color: T.muted }}>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Module</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Last Seen (IST)</th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {heartbeats.length === 0 && (
            <tr>
              <td colSpan={3} style={{ color: T.muted, padding: "8px" }}>
                No data
              </td>
            </tr>
          )}
          {heartbeats.map((hb) => (
            <tr key={hb.module} style={{ borderTop: `1px solid ${T.border}` }}>
              <td style={{ padding: "6px 8px", color: T.text }}>{hb.module}</td>
              <td style={{ padding: "6px 8px", color: T.muted }}>{formatTimeIST(hb.last_seen, true)} IST</td>
              <td style={{ padding: "6px 8px" }}>
                <span style={{ color: hb.stale ? T.neg : T.pos, fontWeight: 600 }}>
                  {hb.stale ? "STALE" : "OK"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
