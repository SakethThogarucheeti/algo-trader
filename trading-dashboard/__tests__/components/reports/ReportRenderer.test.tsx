import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportRenderer } from "@/components/reports/ReportRenderer";
import type { BacktestReport, MonteCarloReport } from "@/lib/api";

// Mock view components to isolate ReportRenderer dispatch logic
vi.mock("@/components/reports/views/BacktestView", () => ({
  BacktestView: ({ report }: { report: BacktestReport }) => (
    <div data-testid="backtest-view">{report.session_id}</div>
  ),
}));

vi.mock("@/components/reports/views/MonteCarloView", () => ({
  MonteCarloView: ({ report }: { report: MonteCarloReport }) => (
    <div data-testid="montecarlo-view">{report.session_id}</div>
  ),
}));

vi.mock("@/components/reports/views/WalkForwardView", () => ({
  WalkForwardView: () => <div data-testid="walkforward-view" />,
}));

describe("ReportRenderer", () => {
  it("renders BacktestView for session_type=backtest", () => {
    const report = { session_type: "backtest", session_id: "bt-001" } as BacktestReport;
    render(<ReportRenderer report={report} />);
    expect(screen.getByTestId("backtest-view")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-view").textContent).toBe("bt-001");
  });

  it("renders MonteCarloView for session_type=monte_carlo", () => {
    const report = { session_type: "monte_carlo", session_id: "mc-001" } as MonteCarloReport;
    render(<ReportRenderer report={report} />);
    expect(screen.getByTestId("montecarlo-view")).toBeInTheDocument();
  });

  it("renders UnknownReportFallback for unregistered type", () => {
    const report = { session_type: "future_type", session_id: "ft-001" } as unknown as BacktestReport;
    render(<ReportRenderer report={report} />);
    // Fallback shows the type in a <strong> tag
    expect(screen.getByText("future_type")).toBeInTheDocument();
  });
});
