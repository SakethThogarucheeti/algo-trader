"use client";

import type { BacktestReport } from "@/lib/api";
import { T } from "@/lib/echarts";
import { formatPct, formatRupee } from "@/lib/format";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { TradePnlBar } from "@/components/charts/TradePnlBar";

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "6px 0",
        borderBottom: `1px solid ${T.border}`,
        fontSize: 13,
      }}
    >
      <span style={{ color: T.muted }}>{label}</span>
      <span style={{ color: T.text, fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
  );
}

export function BacktestView({ report }: { report: BacktestReport }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header strip */}
      <div
        style={{
          display: "flex",
          gap: 32,
          padding: "12px 16px",
          backgroundColor: T.surface,
          border: `1px solid ${T.border}`,
          borderRadius: 8,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Algo</div>
          <div style={{ color: T.text, fontWeight: 600 }}>{report.algo_name}</div>
        </div>
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Period</div>
          <div style={{ color: T.text }}>{report.start.slice(0, 10)} → {report.end.slice(0, 10)}</div>
        </div>
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Session</div>
          <div style={{ color: T.text, fontFamily: "monospace" }}>{report.session_id}</div>
        </div>
      </div>

      {/* Charts row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <EquityCurveChart equityCurve={report.equity_curve} height={280} />
        </div>
        <div>
          <DrawdownChart equityCurve={report.equity_curve} height={280} />
        </div>
      </div>

      {/* Trade P&L bar */}
      {report.trades.length > 0 && (
        <TradePnlBar trades={report.trades} height={220} />
      )}

      {/* Metrics + trade table row */}
      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 16 }}>
        {/* Metrics card */}
        <div
          style={{
            backgroundColor: T.surface,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            padding: 16,
          }}
        >
          <div style={{ color: T.muted, fontSize: 11, fontWeight: 600, textTransform: "uppercase", marginBottom: 8 }}>
            Metrics
          </div>
          <MetricRow label="Sharpe Ratio" value={report.sharpe_ratio.toFixed(3)} />
          <MetricRow label="Max Drawdown" value={formatPct(report.max_drawdown)} />
          <MetricRow label="Win Rate" value={formatPct(report.win_rate)} />
          <MetricRow label="Profit Factor" value={report.profit_factor.toFixed(3)} />
          <MetricRow label="CAGR" value={formatPct(report.cagr)} />
          <MetricRow label="Calmar Ratio" value={report.calmar_ratio.toFixed(3)} />
          <MetricRow label="Total Trades" value={String(report.total_trades)} />
          <MetricRow label="Initial Equity" value={formatRupee(report.initial_equity)} />
          <MetricRow label="Final Equity" value={formatRupee(report.final_equity)} />
        </div>

        {/* Trade table */}
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
            Trades
          </div>
          {report.trades.length === 0 ? (
            <p style={{ color: T.muted, fontSize: 13 }}>No trades</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: T.muted }}>
                  {["Symbol", "Side", "Qty", "Entry", "Exit", "P&L"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.trades.map((t, i) => (
                  <tr
                    key={i}
                    style={{
                      borderTop: `1px solid ${T.border}`,
                      color: T.text,
                    }}
                  >
                    <td style={{ padding: "4px 8px" }}>{t.symbol}</td>
                    <td style={{ padding: "4px 8px" }}>{t.side}</td>
                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.qty}</td>
                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.entry_price.toFixed(2)}</td>
                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.exit_price.toFixed(2)}</td>
                    <td
                      style={{
                        padding: "4px 8px",
                        textAlign: "right",
                        color: t.pnl >= 0 ? T.pos : T.neg,
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {t.pnl >= 0 ? "+" : ""}
                      {t.pnl.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
