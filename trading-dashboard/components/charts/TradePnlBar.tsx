"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { BASE_GRID, BASE_TOOLTIP, BASE_XAXIS, BASE_YAXIS, T } from "@/lib/echarts";
import type { TradeRecord } from "@/lib/api";

interface TradePnlBarProps {
  trades: TradeRecord[];
  height?: number;
  "data-testid"?: string;
}

export function TradePnlBar({ trades, height = 200, "data-testid": testId }: TradePnlBarProps) {
  const option = useMemo(() => {
    const labels = trades.map((t, i) => `#${i + 1} ${t.symbol}`);
    const data = trades.map((t) => ({
      value: t.pnl,
      itemStyle: { color: t.pnl >= 0 ? T.pos : T.neg },
    }));

    return {
      backgroundColor: T.surface,
      tooltip: {
        ...BASE_TOOLTIP,
        trigger: "axis" as const,
        formatter: (params: unknown[]) => {
          const p = (params as { name: string; value: number }[])[0];
          const trade = trades[labels.indexOf(p?.name)];
          if (!trade) return "";
          return (
            `${p.name}<br/>` +
            `P&L: ₹${p.value.toFixed(2)}<br/>` +
            `Entry: ₹${trade.entry_price.toFixed(2)} → ₹${trade.exit_price.toFixed(2)}<br/>` +
            `Qty: ${trade.qty}`
          );
        },
      },
      grid: BASE_GRID,
      xAxis: { ...BASE_XAXIS, data: labels, boundaryGap: true },
      yAxis: {
        ...BASE_YAXIS,
        axisLabel: {
          ...BASE_YAXIS.axisLabel,
          formatter: (v: number) => `₹${v.toFixed(0)}`,
        },
      },
      series: [
        {
          type: "bar",
          data,
          barMaxWidth: 20,
        },
      ],
    };
  }, [trades]);

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      notMerge={false}
      lazyUpdate={true}
      data-testid={testId}
    />
  );
}
