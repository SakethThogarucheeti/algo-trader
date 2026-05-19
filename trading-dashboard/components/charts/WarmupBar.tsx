"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { T } from "@/lib/echarts";

interface WarmupBarProps {
  barsSeen: number;
  warmupTarget: number;
  "data-testid"?: string;
}

export function WarmupBar({ barsSeen, warmupTarget, "data-testid": testId }: WarmupBarProps) {
  const pct = Math.min(100, Math.round((barsSeen / Math.max(warmupTarget, 1)) * 100));
  const complete = barsSeen >= warmupTarget;
  const color = complete ? T.pos : T.neutral;

  const option = useMemo(
    () => ({
      backgroundColor: "transparent",
      grid: { top: 0, bottom: 0, left: 0, right: 0 },
      xAxis: { show: false, max: 100 },
      yAxis: { show: false, type: "category" as const, data: [""] },
      series: [
        {
          type: "bar",
          data: [{ value: pct, itemStyle: { color, borderRadius: 4 } }],
          barMaxWidth: "100%",
          barMinHeight: 6,
          showBackground: true,
          backgroundStyle: { color: T.border, borderRadius: 4 },
          label: {
            show: true,
            position: "insideRight" as const,
            formatter: complete ? "✓" : `${pct}%`,
            color: T.text,
            fontSize: 10,
          },
        },
      ],
    }),
    [pct, complete, color],
  );

  return (
    <ReactECharts
      option={option}
      style={{ height: 28, width: "100%" }}
      notMerge={false}
      data-testid={testId}
    />
  );
}
