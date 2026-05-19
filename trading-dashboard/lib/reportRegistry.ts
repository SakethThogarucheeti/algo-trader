import type { ComponentType } from "react";
import type { AnyReport } from "@/lib/api";
import { BacktestView } from "@/components/reports/views/BacktestView";
import { MonteCarloView } from "@/components/reports/views/MonteCarloView";
import { WalkForwardView } from "@/components/reports/views/WalkForwardView";

export const REPORT_VIEWS: Record<string, ComponentType<{ report: AnyReport }>> = {
  backtest: BacktestView as ComponentType<{ report: AnyReport }>,
  monte_carlo: MonteCarloView as ComponentType<{ report: AnyReport }>,
  walk_forward: WalkForwardView as ComponentType<{ report: AnyReport }>,
};
