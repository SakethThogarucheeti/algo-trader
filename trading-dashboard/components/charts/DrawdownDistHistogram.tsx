"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { BASE_GRID, BASE_TOOLTIP, BASE_XAXIS, BASE_YAXIS, T } from "@/lib/echarts";

interface DrawdownDistHistogramProps {
  drawdownDistribution: number[];
  height?: number;
  "data-testid"?: string;
}

function computeBins(values: number[], nBins = 40) {
  if (values.length === 0) return { labels: [] as string[], counts: [] as number[] };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const binWidth = (max - min) / nBins || 1;
  const counts = new Array<number>(nBins).fill(0);
  values.forEach((v) => {
    const idx = Math.min(nBins - 1, Math.floor((v - min) / binWidth));
    counts[idx]++;
  });
  const labels = counts.map((_, i) => ((min + (i + 0.5) * binWidth) * 100).toFixed(1) + "%");
  return { labels, counts };
}

export function DrawdownDistHistogram({
  drawdownDistribution,
  height = 220,
  "data-testid": testId,
}: DrawdownDistHistogramProps) {
  const option = useMemo(() => {
    const { labels, counts } = computeBins(drawdownDistribution);
    return {
      backgroundColor: T.surface,
      tooltip: { ...BASE_TOOLTIP, trigger: "axis" as const },
      grid: BASE_GRID,
      xAxis: { ...BASE_XAXIS, data: labels, boundaryGap: true },
      yAxis: { ...BASE_YAXIS },
      series: [
        {
          type: "bar",
          data: counts,
          itemStyle: { color: T.neutral },
          barMaxWidth: 20,
        },
      ],
    };
  }, [drawdownDistribution]);

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
