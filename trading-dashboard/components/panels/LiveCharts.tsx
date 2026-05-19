"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchCandles, fetchTicks, fetchPnl, fetchCharts } from "@/lib/api";
import { CandleChart } from "@/components/charts/CandleChart";
import { LineChart } from "@/components/charts/LineChart";
import { PnlSummaryStrip } from "@/components/panels/PnlSummaryStrip";
import { T } from "@/lib/echarts";
import { formatRupee } from "@/lib/format";
import { useDashboardStore } from "@/store";

const INTERVALS = ["1min", "3min", "5min", "10min", "15min", "30min", "60min"];
const EMPTY_PNL_SUMMARY = { gross: 0, costs: 0, net: 0, nifty_pct: null, nifty_open: null, nifty_close: null };

export function LiveCharts() {
  const { sessionId, symbol, interval, setSymbol, setInterval } = useDashboardStore();
  const [symbolInput, setSymbolInput] = useState(symbol);

  const { data: candles = [] } = useQuery({
    queryKey: ["candles", symbol, interval],
    queryFn: () => fetchCandles(symbol, interval, 200),
    refetchInterval: 30_000,
  });

  const { data: ticks = [] } = useQuery({
    queryKey: ["ticks", symbol],
    queryFn: () => fetchTicks(symbol),
    refetchInterval: 5_000,
  });

  const { data: pnlData } = useQuery({
    queryKey: ["pnl", sessionId],
    queryFn: () => fetchPnl(sessionId),
    refetchInterval: 30_000,
  });

  const { data: charts = {} } = useQuery({
    queryKey: ["charts", sessionId],
    queryFn: () => fetchCharts(sessionId),
    refetchInterval: 30_000,
  });

  const pnlPoints = pnlData?.points ?? [];
  const pnlSummary = pnlData?.summary ?? EMPTY_PNL_SUMMARY;

  const pnlSeries = [
    {
      name: "Gross P&L",
      data: pnlPoints.map((p) => ({ ts: p.ts, value: p.cumulative_gross })),
      dashed: true,
    },
    {
      name: "Net P&L (after costs)",
      data: pnlPoints.map((p) => ({ ts: p.ts, value: p.cumulative_net })),
      showSymbol: true,
    },
  ];

  const tickSeries = [
    {
      name: symbol,
      data: ticks.map((t) => ({ ts: t.ts, value: t.price })),
      areaGradient: true,
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Candlestick */}
      <div style={{ backgroundColor: T.surface, borderRadius: 8, padding: 16 }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
          <span style={{ color: T.text, fontSize: 13, fontWeight: 600 }}>Candlestick</span>
          <input
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && setSymbol(symbolInput)}
            placeholder="Symbol"
            style={{
              backgroundColor: T.bg,
              color: T.text,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 12,
              fontFamily: "ui-monospace, monospace",
              width: 80,
            }}
          />
          <select
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
            style={{
              backgroundColor: T.bg,
              color: T.text,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 12,
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {INTERVALS.map((iv) => (
              <option key={iv} value={iv}>
                {iv}
              </option>
            ))}
          </select>
          <button
            onClick={() => setSymbol(symbolInput)}
            style={{
              backgroundColor: T.accent,
              color: "#fff",
              border: "none",
              borderRadius: 4,
              padding: "4px 12px",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Load
          </button>
        </div>
        {candles.length > 0 ? (
          <CandleChart candles={candles} />
        ) : (
          <div style={{ color: T.muted, fontSize: 12, height: 60, display: "flex", alignItems: "center" }}>
            No candle data today
          </div>
        )}
      </div>

      {/* Tick Price */}
      <div style={{ backgroundColor: T.surface, borderRadius: 8, padding: 16 }}>
        <div style={{ color: T.text, fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
          Tick Price — {symbol}
        </div>
        {ticks.length > 0 ? (
          <LineChart
            series={tickSeries}
            height={180}
            yFormatter={(v) => `₹${v.toLocaleString("en-IN")}`}
          />
        ) : (
          <div style={{ color: T.muted, fontSize: 12, height: 40, display: "flex", alignItems: "center" }}>
            No tick data today
          </div>
        )}
      </div>

      {/* P&L */}
      <div style={{ backgroundColor: T.surface, borderRadius: 8, padding: 16 }}>
        <div style={{ color: T.text, fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
          Cumulative P&L
        </div>
        <PnlSummaryStrip summary={pnlSummary} />
        {pnlPoints.length > 0 ? (
          <LineChart
            series={pnlSeries}
            height={220}
            yFormatter={formatRupee}
          />
        ) : (
          <div style={{ color: T.muted, fontSize: 12, height: 40, display: "flex", alignItems: "center", marginTop: 8 }}>
            No trades today
          </div>
        )}
      </div>

      {/* Indicator Charts */}
      {Object.entries(charts).map(([chartName, seriesMap]) => {
        const series = Object.entries(seriesMap).map(([name, pts]) => ({ name, data: pts }));
        return (
          <div key={chartName} style={{ backgroundColor: T.surface, borderRadius: 8, padding: 16 }}>
            <div style={{ color: T.text, fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{chartName}</div>
            <LineChart series={series} height={200} />
          </div>
        );
      })}
      {Object.keys(charts).length === 0 && (
        <div style={{ color: T.muted, fontSize: 12 }}>No indicator data yet — waiting for candles…</div>
      )}
    </div>
  );
}
