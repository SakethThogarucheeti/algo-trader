"use client";

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { BASE_GRID, BASE_LEGEND, BASE_TOOLTIP, BASE_XAXIS, BASE_YAXIS, SERIES_COLORS, T } from "@/lib/echarts";
import { formatTimeIST } from "@/lib/format";

export interface LineSeriesData {
  ts: string;
  value: number | null;
}

export interface LineSeries {
  name: string;
  data: LineSeriesData[];
  dashed?: boolean;
  areaGradient?: boolean;
  showSymbol?: boolean;
}

interface LineChartProps {
  series: LineSeries[];
  height?: number;
  yFormatter?: (v: number) => string;
  tooltipFormatter?: (params: unknown) => string;
  "data-testid"?: string;
}

export function LineChart({
  series,
  height = 240,
  yFormatter,
  tooltipFormatter,
  "data-testid": testId,
}: LineChartProps) {
  const option = useMemo(() => {
    // Build unified sorted time axis across all series
    const allTs = [
      ...new Set(series.flatMap((s) => s.data.map((p) => p.ts))),
    ].sort();

    const labels = allTs.map((ts) => formatTimeIST(ts));

    const echartsSeries = series.map((s, i) => {
      const byTs = Object.fromEntries(s.data.map((p) => [p.ts, p.value]));
      const color = SERIES_COLORS[i % SERIES_COLORS.length];

      const seriesConfig: Record<string, unknown> = {
        name: s.name,
        type: "line",
        smooth: false,
        symbol: s.showSymbol ? "circle" : "none",
        symbolSize: 5,
        lineStyle: {
          color,
          width: 1.5,
          type: s.dashed ? "dashed" : "solid",
        },
        data: allTs.map((ts) => byTs[ts] ?? null),
        connectNulls: false,
      };

      if (s.areaGradient) {
        seriesConfig.areaStyle = {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: color + "40" },
              { offset: 1, color: color + "00" },
            ],
          },
        };
      }

      return seriesConfig;
    });

    return {
      backgroundColor: T.surface,
      tooltip: {
        ...BASE_TOOLTIP,
        ...(tooltipFormatter ? { formatter: tooltipFormatter } : {}),
      },
      legend: series.length > 1 ? { ...BASE_LEGEND, data: series.map((s) => s.name) } : undefined,
      grid: { ...BASE_GRID, top: series.length > 1 ? 28 : 12 },
      xAxis: { ...BASE_XAXIS, data: labels },
      yAxis: {
        ...BASE_YAXIS,
        ...(yFormatter ? { axisLabel: { ...BASE_YAXIS.axisLabel, formatter: yFormatter } } : {}),
      },
      series: echartsSeries,
    };
  }, [series, yFormatter, tooltipFormatter]);

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
