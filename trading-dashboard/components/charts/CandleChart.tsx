"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { BASE_GRID, BASE_TOOLTIP, BASE_XAXIS, BASE_YAXIS, T } from "@/lib/echarts";
import { formatTimeIST } from "@/lib/format";
import type { Candle } from "@/lib/api";

interface CandleChartProps {
  candles: Candle[];
  height?: number;
  "data-testid"?: string;
}

export function CandleChart({ candles, height = 320, "data-testid": testId }: CandleChartProps) {
  const option = useMemo(() => {
    const labels = candles.map((c) => formatTimeIST(c.ts));
    // ECharts candlestick: [open, close, low, high]
    const data = candles.map((c) => [c.open, c.close, c.low, c.high]);

    // Default zoom to show last 60 bars
    const startPct = candles.length > 60 ? Math.round(((candles.length - 60) / candles.length) * 100) : 0;

    return {
      backgroundColor: T.surface,
      tooltip: {
        ...BASE_TOOLTIP,
        trigger: "axis",
        formatter: (params: unknown[]) => {
          const p = (params as { name: string; value: number[] }[])[0];
          if (!p) return "";
          const [o, c, l, h] = p.value;
          const col = c >= o ? T.pos : T.neg;
          return (
            `<b>${p.name}</b><br/>` +
            `<span style="color:${col}">O ₹${o.toFixed(2)}  H ₹${h.toFixed(2)}</span><br/>` +
            `<span style="color:${col}">L ₹${l.toFixed(2)}  C ₹${c.toFixed(2)}</span>`
          );
        },
      },
      grid: { ...BASE_GRID, bottom: 52 },
      xAxis: {
        ...BASE_XAXIS,
        boundaryGap: true,
        data: labels,
        axisLabel: { ...BASE_XAXIS.axisLabel, rotate: 30 },
      },
      yAxis: {
        ...BASE_YAXIS,
        axisLabel: {
          ...BASE_YAXIS.axisLabel,
          formatter: (v: number) => `₹${v.toLocaleString("en-IN")}`,
        },
      },
      dataZoom: [
        { type: "inside", start: startPct, end: 100 },
        {
          type: "slider",
          height: 20,
          bottom: 4,
          start: startPct,
          end: 100,
          borderColor: T.border,
          fillerColor: T.accent + "26",
          handleStyle: { color: T.accent },
          textStyle: { color: T.muted, fontSize: 10 },
        },
      ],
      series: [
        {
          type: "candlestick",
          data,
          barWidth: 6,
          itemStyle: {
            color: T.pos,
            color0: T.neg,
            borderColor: T.pos,
            borderColor0: T.neg,
          },
        },
      ],
    };
  }, [candles]);

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
