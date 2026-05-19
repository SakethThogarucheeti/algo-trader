"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { BASE_GRID, BASE_TOOLTIP, BASE_XAXIS, BASE_YAXIS, T } from "@/lib/echarts";

interface DrawdownChartProps {
  equityCurve: [string, number][];
  height?: number;
  "data-testid"?: string;
}

export function DrawdownChart({
  equityCurve,
  height = 180,
  "data-testid": testId,
}: DrawdownChartProps) {
  const option = useMemo(() => {
    const labels = equityCurve.map(([ts]) => ts.substring(0, 10));
    const equities = equityCurve.map(([, eq]) => eq);

    let runningMax = 0;
    const drawdowns = equities.map((eq) => {
      runningMax = Math.max(runningMax, eq);
      return runningMax > 0 ? -((runningMax - eq) / runningMax) : 0;
    });

    return {
      backgroundColor: T.surface,
      tooltip: {
        ...BASE_TOOLTIP,
        formatter: (params: unknown[]) => {
          const p = (params as { name: string; value: number }[])[0];
          return p ? `${p.name}<br/>${(p.value * 100).toFixed(2)}%` : "";
        },
      },
      grid: BASE_GRID,
      xAxis: { ...BASE_XAXIS, data: labels },
      yAxis: {
        ...BASE_YAXIS,
        axisLabel: {
          ...BASE_YAXIS.axisLabel,
          formatter: (v: number) => `${(v * 100).toFixed(0)}%`,
        },
      },
      series: [
        {
          name: "Drawdown",
          type: "line",
          data: drawdowns,
          symbol: "none",
          lineStyle: { color: T.neg, width: 1.5 },
          areaStyle: { color: T.neg + "4D" },
          connectNulls: false,
        },
      ],
    };
  }, [equityCurve]);

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
