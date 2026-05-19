import { http, HttpResponse } from "msw";
import type { ReportSessionMeta, BacktestReport, MonteCarloReport } from "@/lib/api";

export const mockBacktestReport: BacktestReport = {
  session_type: "backtest",
  session_id: "bt-test-001",
  algo_name: "ema_crossover",
  start: "2026-01-01T00:00:00Z",
  end: "2026-03-01T00:00:00Z",
  initial_equity: 100000,
  final_equity: 112500,
  sharpe_ratio: 1.42,
  max_drawdown: 0.08,
  max_drawdown_duration_secs: 86400,
  win_rate: 0.62,
  profit_factor: 1.85,
  cagr: 0.15,
  calmar_ratio: 1.875,
  total_trades: 50,
  started_at: "2026-05-01T09:00:00Z",
  finished_at: "2026-05-01T09:45:00Z",
  equity_curve: [
    ["2026-01-01T00:00:00Z", 100000],
    ["2026-02-01T00:00:00Z", 105000],
    ["2026-03-01T00:00:00Z", 112500],
  ],
  trades: [
    {
      symbol: "INFY",
      side: "BUY",
      qty: 10,
      entry_price: 2500,
      exit_price: 2600,
      pnl: 1000,
      entry_time: "2026-01-05T09:15:00Z",
      exit_time: "2026-01-05T15:30:00Z",
    },
  ],
};

export const mockMonteCarloReport: MonteCarloReport = {
  session_type: "monte_carlo",
  session_id: "mc-test-001",
  n_trials: 1000,
  method: "bootstrap",
  probability_of_ruin: 0.02,
  percentile_5_return: -0.05,
  percentile_95_return: 0.18,
  median_drawdown: 0.07,
  started_at: "2026-05-02T10:00:00Z",
  finished_at: "2026-05-02T10:05:00Z",
  return_distribution: Array.from({ length: 1000 }, (_, i) => (i - 500) / 5000),
  drawdown_distribution: Array.from({ length: 1000 }, (_, i) => i / 10000),
};

export const mockSessions: ReportSessionMeta[] = [
  {
    session_id: "bt-test-001",
    session_type: "backtest",
    algo_name: "ema_crossover",
    started_at: "2026-05-01T09:00:00Z",
    finished_at: "2026-05-01T09:45:00Z",
  },
  {
    session_id: "mc-test-001",
    session_type: "monte_carlo",
    algo_name: null,
    started_at: "2026-05-02T10:00:00Z",
    finished_at: "2026-05-02T10:05:00Z",
  },
];

export const handlers = [
  http.get("/api/reports/sessions", () => HttpResponse.json(mockSessions)),
  http.get("/api/reports/bt-test-001", () => HttpResponse.json(mockBacktestReport)),
  http.get("/api/reports/mc-test-001", () => HttpResponse.json(mockMonteCarloReport)),
  http.get("/api/positions", () => HttpResponse.json([])),
  http.get("/api/health", () => HttpResponse.json([])),
  http.get("/api/algos", () => HttpResponse.json([])),
  http.get("/api/signals", () => HttpResponse.json([])),
];
