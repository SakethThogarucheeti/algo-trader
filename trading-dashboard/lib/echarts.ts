export const T = {
  bg: "#0f1117",
  surface: "#1a1d27",
  border: "#2a2d3a",
  grid: "#1e2130",
  text: "#e2e8f0",
  muted: "#64748b",
  pos: "#22c55e",
  neg: "#ef4444",
  neutral: "#f59e0b",
  accent: "#6366f1",
  font: 'ui-monospace, "Cascadia Code", "JetBrains Mono", monospace',
} as const;

export const SERIES_COLORS = [
  T.accent,
  T.pos,
  T.neutral,
  T.neg,
  "#06b6d4",
  "#a855f7",
  "#f97316",
  "#84cc16",
];

export const BASE_TOOLTIP = {
  trigger: "axis" as const,
  backgroundColor: T.grid,
  borderColor: T.border,
  textStyle: { color: T.text, fontSize: 11, fontFamily: T.font },
};

export const BASE_XAXIS = {
  type: "category" as const,
  boundaryGap: false,
  axisLine: { lineStyle: { color: T.border } },
  axisTick: { show: false },
  axisLabel: { color: T.muted, fontSize: 10, fontFamily: T.font },
  splitLine: { show: false },
};

export const BASE_YAXIS = {
  scale: true,
  axisLine: { show: false },
  axisTick: { show: false },
  axisLabel: { color: T.muted, fontSize: 10, fontFamily: T.font },
  splitLine: { lineStyle: { color: T.grid, type: "dashed" as const } },
};

export const BASE_GRID = {
  top: 12,
  right: 60,
  bottom: 36,
  left: 16,
  containLabel: true,
};

export const BASE_LEGEND = {
  top: 4,
  textStyle: { color: T.muted, fontSize: 10, fontFamily: T.font },
};
