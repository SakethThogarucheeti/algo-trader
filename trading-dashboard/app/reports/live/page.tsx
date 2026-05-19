import { T } from "@/lib/echarts";
import { fetchLiveReport } from "@/lib/api";
import type { LiveReport } from "@/lib/api";
import Link from "next/link";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        backgroundColor: T.surface,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
      }}
    >
      <div
        style={{
          color: T.muted,
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          marginBottom: 12,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string | number }) {
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

function pctStr(v: number | null, decimals = 2): string {
  if (v === null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(decimals)}%`;
}

function rupeeStr(v: number): string {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(v);
}

export default async function LiveReportPage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string; date?: string }>;
}) {
  const { period: rawPeriod, date } = await searchParams;
  const period = (rawPeriod as "day" | "week" | "month") ?? "day";

  let report: LiveReport | null = null;
  let error: string | null = null;
  try {
    report = await fetchLiveReport(period, date);
  } catch (e) {
    error = String(e);
  }

  const periodLinks = (["day", "week", "month"] as const).map((p) => ({
    label: p.charAt(0).toUpperCase() + p.slice(1),
    href: `/reports/live?period=${p}${date ? `&date=${date}` : ""}`,
    active: p === period,
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Link href="/reports" style={{ color: T.muted, fontSize: 12, textDecoration: "none" }}>
            ← Reports
          </Link>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: T.text }}>Live Report</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {periodLinks.map(({ label, href, active }) => (
            <Link
              key={label}
              href={href}
              style={{
                padding: "6px 14px",
                backgroundColor: active ? T.accent : T.surface,
                border: `1px solid ${active ? T.accent : T.border}`,
                borderRadius: 6,
                color: active ? "#fff" : T.text,
                fontSize: 12,
                textDecoration: "none",
              }}
            >
              {label}
            </Link>
          ))}
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: 24,
            backgroundColor: T.surface,
            border: `1px solid ${T.neg}`,
            borderRadius: 8,
            color: T.neg,
            fontSize: 13,
          }}
        >
          Failed to load report: {error}
        </div>
      )}

      {report && (
        <>
          <div
            style={{
              padding: "8px 16px",
              backgroundColor: T.grid,
              borderRadius: 6,
              color: T.muted,
              fontSize: 12,
              marginBottom: 16,
            }}
          >
            {report.start ? `${report.start.slice(0, 10)} → ${report.end?.slice(0, 10)}` : ""}
          </div>

          <Section title="Signal Funnel">
            <StatRow label="Candles Emitted" value={report.signal_funnel.candles_emitted} />
            <StatRow label="Signals Generated" value={report.signal_funnel.signals_generated} />
            <StatRow label="Signals Accepted" value={report.signal_funnel.signals_accepted} />
            <StatRow label="Signals Rejected" value={report.signal_funnel.signals_rejected} />
            <StatRow
              label="Acceptance Rate"
              value={`${(report.signal_funnel.acceptance_rate * 100).toFixed(1)}%`}
            />
            {Object.entries(report.signal_funnel.rejection_reasons).map(([reason, count]) => (
              <StatRow key={reason} label={`  ${reason}`} value={count} />
            ))}
          </Section>

          <Section title="Order Funnel">
            <StatRow label="Placed" value={report.order_funnel.placed} />
            <StatRow label="Filled" value={report.order_funnel.filled} />
            <StatRow label="Rejected" value={report.order_funnel.rejected} />
            <StatRow label="Cancelled" value={report.order_funnel.cancelled} />
            <StatRow
              label="Fill Rate"
              value={`${(report.order_funnel.fill_rate * 100).toFixed(1)}%`}
            />
          </Section>

          <Section title="P&L Summary">
            <StatRow label="Gross P&L" value={rupeeStr(report.pnl_summary.gross)} />
            <StatRow label="Trading Costs" value={`-${rupeeStr(report.pnl_summary.costs)}`} />
            <StatRow label="Net P&L" value={rupeeStr(report.pnl_summary.net)} />
            {report.pnl_summary.algo_pct != null && (
              <StatRow label="Algo Return" value={pctStr(report.pnl_summary.algo_pct / 100)} />
            )}
          </Section>

          {report.benchmark && (
            <Section title="Benchmark: Nifty 50">
              <StatRow label="Nifty Open" value={report.benchmark.nifty_open?.toLocaleString("en-IN") ?? "—"} />
              <StatRow label="Nifty Close" value={report.benchmark.nifty_close?.toLocaleString("en-IN") ?? "—"} />
              <StatRow
                label="Nifty Return"
                value={report.benchmark.pct_return !== null ? `${report.benchmark.pct_return >= 0 ? "+" : ""}${report.benchmark.pct_return.toFixed(2)}%` : "—"}
              />
              {report.benchmark.algo_pct !== null && (
                <StatRow label="Algo Return" value={`${report.benchmark.algo_pct >= 0 ? "+" : ""}${report.benchmark.algo_pct.toFixed(2)}%`} />
              )}
              {report.benchmark.alpha !== null && (
                <StatRow
                  label="Alpha"
                  value={`${report.benchmark.alpha >= 0 ? "+" : ""}${report.benchmark.alpha.toFixed(2)}% (${report.benchmark.alpha >= 0 ? "outperforming" : "underperforming"})`}
                />
              )}
            </Section>
          )}

          {report.trades_by_symbol.length > 0 && (
            <Section title="Trades by Symbol">
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ color: T.muted }}>
                    {["Symbol", "Buys", "Sells", "Volume", "Cash Flow"].map((h) => (
                      <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.trades_by_symbol.map((row) => (
                    <tr key={row.symbol} style={{ borderTop: `1px solid ${T.border}`, color: T.text }}>
                      <td style={{ padding: "4px 8px" }}>{row.symbol}</td>
                      <td style={{ padding: "4px 8px", textAlign: "right" }}>{row.buys}</td>
                      <td style={{ padding: "4px 8px", textAlign: "right" }}>{row.sells}</td>
                      <td style={{ padding: "4px 8px", textAlign: "right" }}>{row.volume}</td>
                      <td
                        style={{
                          padding: "4px 8px",
                          textAlign: "right",
                          color: row.cash_flow >= 0 ? T.pos : T.neg,
                        }}
                      >
                        {row.cash_flow >= 0 ? "+" : ""}
                        {rupeeStr(row.cash_flow)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}

          <Section title="System Health">
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: T.muted }}>
                  {["Module", "Last Seen", "Status"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontWeight: 500 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.system_health.map((h) => (
                  <tr key={h.module} style={{ borderTop: `1px solid ${T.border}`, color: T.text }}>
                    <td style={{ padding: "4px 8px" }}>{h.module}</td>
                    <td style={{ padding: "4px 8px", color: T.muted }}>
                      {new Date(h.last_seen).toLocaleString()}
                    </td>
                    <td style={{ padding: "4px 8px" }}>
                      <span style={{ color: (h as { stale: boolean }).stale ? T.neg : T.pos }}>
                        {(h as { stale: boolean }).stale ? "STALE" : "OK"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </>
      )}
    </div>
  );
}
