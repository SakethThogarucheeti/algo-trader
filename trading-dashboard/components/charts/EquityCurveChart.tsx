"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { BASE_GRID, BASE_TOOLTIP, BASE_XAXIS, BASE_YAXIS, T } from "@/lib/echarts";
import { formatRupee } from "@/lib/format";

interface EquityCurveChartProps {
  equityCurve: [string, number][];
  height?: number;
  "data-testid"?: string;
}

export function EquityCurveChart({
  equityCurve,
  height = 280,
  "data-testid": testId,
}: EquityCurveChartProps) {
  const option = useMemo(() => {
    const labels = equityCurve.map(([ts]) => ts.substring(0, 10));
    const equities = equityCurve.map(([, eq]) => eq);

    // Compute drawdown markAreas
    let runningMax = 0;
    let inDD = false;
    let ddStart: string | null = null;
    const markAreas: [{ xAxis: string }, { xAxis: string }][] = [];

    equities.forEach((eq, i) => {
      runningMax = Math.max(runningMax, eq);
      if (eq < runningMax && !inDD) {
        inDD = true;
        ddStart = labels[i];
      } else if (eq >= runningMax && inDD) {
        inDD = false;
        markAreas.push([{ xAxis: ddStart! }, { xAxis: labels[i] }]);
        ddStart = null;
      }
    });
    if (inDD && ddStart && labels.length > 0) {
      markAreas.push([{ xAxis: ddStart }, { xAxis: labels[labels.length - 1] }]);
    }

    return {
      backgroundColor: T.surface,
      tooltip: {
        ...BASE_TOOLTIP,
        formatter: (params: unknown[]) => {
          const p = (params as { name: string; value: number }[])[0];
          return p ? `${p.name}<br/>${formatRupee(p.value)}` : "";
        },
      },
      grid: BASE_GRID,
      xAxis: { ...BASE_XAXIS, data: labels },
      yAxis: {
        ...BASE_YAXIS,
        axisLabel: {
          ...BASE_YAXIS.axisLabel,
          formatter: (v: number) => `₹${(v / 1000).toFixed(0)}K`,
        },
      },
      series: [
        {
          name: "Equity",
          type: "line",
          data: equities,
          symbol: "none",
          lineStyle: { color: T.accent, width: 2 },
          markArea: {
            silent: true,
            itemStyle: { color: T.neg + "26" },
            data: markAreas,
          },
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
