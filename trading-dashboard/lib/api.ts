// All fetch wrappers for the FastAPI backend.
// Relative URLs go through Next.js rewrites → process.env.API_URL.

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export interface Position {
  symbol: string;
  instrument_type: string;
  net_qty: number;
  avg_price: number;
  updated_at: string | null;
}

export interface Heartbeat {
  module: string;
  last_seen: string;
  stale: boolean;
}

export interface Signal {
  created_at: string;
  symbol: string;
  algo_name: string;
  step: "SIGNAL_GENERATED" | "SIGNAL_ACCEPTED" | "SIGNAL_REJECTED";
  context: string;
}

export interface AlgoConfig {
  name: string;
  strategy_id: string;
  warmup_candles: number;
  candle_intervals: string[];
  equity: number;
  enabled: boolean;
  params: Record<string, unknown>;
  state: Record<string, unknown>;
  updated_at: string | null;
}

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Tick {
  ts: string;
  price: number;
}

export interface PnlPoint {
  ts: string;
  cumulative_gross: number;
  cumulative_net: number;
  side: string;
  qty: number;
  price: number;
  cost: number;
  symbol: string;
  signal_type: string;
}

export interface PnlSummary {
  gross: number;
  costs: number;
  net: number;
  nifty_pct: number | null;
  nifty_open: number | null;
  nifty_close: number | null;
  algo_pct?: number | null;
}

export interface PnlResponse {
  points: PnlPoint[];
  summary: PnlSummary;
}

export type IndicatorSeriesPoint = { ts: string; value: number };
// { chart_name: { series_name: [{ts, value}] } }
export type ChartsResponse = Record<string, Record<string, IndicatorSeriesPoint[]>>;

export interface DecisionEvent {
  id: number;
  tick_log_id: number;
  step: string;
  symbol: string;
  algo: string | null;
  ts: string;
  context: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Report types
// ---------------------------------------------------------------------------

export interface TradeRecord {
  symbol: string;
  side: string;
  qty: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  entry_time: string;
  exit_time: string;
}

export interface BacktestReport {
  session_type: "backtest";
  session_id: string;
  algo_name: string;
  start: string;
  end: string;
  initial_equity: number;
  final_equity: number;
  sharpe_ratio: number;
  max_drawdown: number;
  max_drawdown_duration_secs: number;
  win_rate: number;
  profit_factor: number;
  cagr: number;
  calmar_ratio: number;
  total_trades: number;
  equity_curve: [string, number][];
  trades: TradeRecord[];
  started_at: string;
  finished_at: string;
}

export interface MonteCarloReport {
  session_type: "monte_carlo";
  session_id: string;
  n_trials: number;
  method: string;
  probability_of_ruin: number;
  percentile_5_return: number;
  percentile_95_return: number;
  median_drawdown: number;
  return_distribution: number[];
  drawdown_distribution: number[];
  started_at: string;
  finished_at: string;
}

export interface WalkForwardReport {
  session_type: "walk_forward";
  session_id: string;
  aggregate_sharpe: number;
  aggregate_max_drawdown: number;
  aggregate_win_rate: number;
  combined_equity_curve: [string, number][];
  windows: BacktestReport[];
  started_at: string;
  finished_at: string;
}

export type AnyReport = BacktestReport | MonteCarloReport | WalkForwardReport;

export interface ReportSessionMeta {
  session_id: string;
  session_type: string;
  algo_name: string | null;
  started_at: string;
  finished_at: string;
}

export interface LiveReportFunnel {
  candles_emitted: number;
  signals_generated: number;
  signals_accepted: number;
  signals_rejected: number;
  acceptance_rate: number;
  rejection_reasons: Record<string, number>;
}

export interface LiveReportOrderFunnel {
  placed: number;
  filled: number;
  rejected: number;
  cancelled: number;
  fill_rate: number;
}

export interface LiveReportBenchmark {
  nifty_open: number | null;
  nifty_close: number | null;
  pct_return: number | null;
  algo_pct: number | null;
  alpha: number | null;
}

export interface LiveReport {
  period: string | null;
  start?: string;
  end?: string;
  title?: string;
  signal_funnel: LiveReportFunnel;
  order_funnel: LiveReportOrderFunnel;
  pnl_summary: PnlSummary;
  trades_by_symbol: { symbol: string; buys: number; sells: number; volume: number; cash_flow: number }[];
  benchmark: LiveReportBenchmark | null;
  algo_configs: AlgoConfig[];
  system_health: Heartbeat[];
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${url} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Live dashboard endpoints
// ---------------------------------------------------------------------------

export const fetchPositions = (sessionId = "") =>
  get<Position[]>(`/api/positions${sessionId ? `?session_id=${sessionId}` : ""}`);

export const fetchHealth = () => get<Heartbeat[]>("/api/health");

export const fetchAlgos = () => get<AlgoConfig[]>("/api/algos");

export const fetchSignals = (sessionId = "") =>
  get<Signal[]>(`/api/signals${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`);

export const fetchCandles = (symbol: string, interval: string, limit = 200) =>
  get<Candle[]>(`/api/candles?symbol=${symbol}&interval=${interval}&limit=${limit}`);

export const fetchTicks = (symbol: string, limit = 500) =>
  get<Tick[]>(`/api/ticks?symbol=${symbol}&limit=${limit}`);

export const fetchPnl = (sessionId = "") =>
  get<PnlResponse>(`/api/pnl${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`);

export const fetchCharts = (sessionId = "", limit = 500) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (sessionId) params.set("session_id", sessionId);
  return get<ChartsResponse>(`/api/charts?${params}`);
};

export const fetchSessions = () => get<(string | null)[]>("/api/sessions");

// ---------------------------------------------------------------------------
// Report endpoints
// ---------------------------------------------------------------------------

export const fetchReportSessions = () => get<ReportSessionMeta[]>("/api/reports/sessions");

export const fetchReport = (sessionId: string) =>
  get<AnyReport>(`/api/reports/${encodeURIComponent(sessionId)}`);

export const fetchLiveReport = (period: "day" | "week" | "month", date?: string) => {
  const params = new URLSearchParams({ period });
  if (date) params.set("date", date);
  return get<LiveReport>(`/api/reports/live?${params}`);
};
