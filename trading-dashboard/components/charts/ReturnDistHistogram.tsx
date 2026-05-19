"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { BASE_GRID, BASE_TOOLTIP, BASE_XAXIS, BASE_YAXIS, T } from "@/lib/echarts";

interface ReturnDistHistogramProps {
  returnDistribution: number[];
  percentile5: number;
  percentile95: number;
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
  return { labels, counts, min, binWidth };
}

export function ReturnDistHistogram({
  returnDistribution,
  percentile5,
  percentile95,
  height = 220,
  "data-testid": testId,
}: ReturnDistHistogramProps) {
  const option = useMemo(() => {
    const { labels, counts, min, binWidth } = computeBins(returnDistribution);

    const p5Bin = min !== undefined && binWidth ? Math.floor((percentile5 - min) / binWidth) : 0;
    const p95Bin = min !== undefined && binWidth ? Math.floor((percentile95 - min) / binWidth) : labels.length - 1;

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
          itemStyle: { color: T.accent },
          barMaxWidth: 20,
          markLine: {
            silent: true,
            data: [
              {
                xAxis: labels[p5Bin] ?? labels[0],
                lineStyle: { color: T.neg, type: "dashed" },
                label: { formatter: "5th", color: T.neg, fontSize: 10 },
              },
              {
                xAxis: labels[p95Bin] ?? labels[labels.length - 1],
                lineStyle: { color: T.pos, type: "dashed" },
                label: { formatter: "95th", color: T.pos, fontSize: 10 },
              },
            ],
          },
        },
      ],
    };
  }, [returnDistribution, percentile5, percentile95]);

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
