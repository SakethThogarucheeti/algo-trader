"use client";

import type { WalkForwardReport } from "@/lib/api";
import { T } from "@/lib/echarts";
import { formatPct } from "@/lib/format";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";

function MetricCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      style={{
        backgroundColor: T.surface,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        padding: "12px 16px",
      }}
    >
      <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color: color ?? T.text, fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

export function WalkForwardView({ report }: { report: WalkForwardReport }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          backgroundColor: T.surface,
          border: `1px solid ${T.border}`,
          borderRadius: 8,
          display: "flex",
          gap: 32,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Windows</div>
          <div style={{ color: T.text, fontWeight: 600 }}>{report.windows.length}</div>
        </div>
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Session</div>
          <div style={{ color: T.text, fontFamily: "monospace" }}>{report.session_id}</div>
        </div>
      </div>

      {/* Aggregate metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        <MetricCard label="Aggregate Sharpe" value={report.aggregate_sharpe.toFixed(3)} />
        <MetricCard
          label="Aggregate Max DD"
          value={formatPct(report.aggregate_max_drawdown)}
          color={T.neg}
        />
        <MetricCard
          label="Aggregate Win Rate"
          value={formatPct(report.aggregate_win_rate)}
          color={T.pos}
        />
      </div>

      {/* Combined equity curve */}
      <EquityCurveChart equityCurve={report.combined_equity_curve} height={300} />

      {/* Per-window table */}
      <div
        style={{
          backgroundColor: T.surface,
          border: `1px solid ${T.border}`,
          borderRadius: 8,
          padding: 16,
          overflowX: "auto",
        }}
      >
        <div style={{ color: T.muted, fontSize: 11, fontWeight: 600, textTransform: "uppercase", marginBottom: 8 }}>
          Windows
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ color: T.muted }}>
              {["#", "Period", "Sharpe", "Max DD", "Win Rate", "Total Trades", "Final Equity"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.windows.map((w, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${T.border}`, color: T.text }}>
                <td style={{ padding: "4px 8px", color: T.muted }}>W{i + 1}</td>
                <td style={{ padding: "4px 8px" }}>
                  {w.start.slice(0, 10)} → {w.end.slice(0, 10)}
                </td>
                <td
                  style={{
                    padding: "4px 8px",
                    color: w.sharpe_ratio >= 0 ? T.pos : T.neg,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {w.sharpe_ratio.toFixed(3)}
                </td>
                <td style={{ padding: "4px 8px", color: T.neg }}>{formatPct(w.max_drawdown)}</td>
                <td style={{ padding: "4px 8px" }}>{formatPct(w.win_rate)}</td>
                <td style={{ padding: "4px 8px", textAlign: "right" }}>{w.total_trades}</td>
                <td style={{ padding: "4px 8px", textAlign: "right" }}>
                  {w.final_equity.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
