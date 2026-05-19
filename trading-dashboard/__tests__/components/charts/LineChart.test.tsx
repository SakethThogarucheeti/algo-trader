import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { LineChart } from "@/components/charts/LineChart";

describe("LineChart timestamp alignment", () => {
  it("builds a unified axis across two series of different lengths", () => {
    const { getByTestId } = render(
      <LineChart
        data-testid="chart"
        series={[
          {
            name: "EMA9",
            data: [
              { ts: "2026-05-19T04:00:00Z", value: 100 },
              { ts: "2026-05-19T04:05:00Z", value: 101 },
            ],
          },
          {
            name: "EMA21",
            data: [{ ts: "2026-05-19T04:05:00Z", value: 99 }],
          },
        ]}
      />
    );

    const raw = getByTestId("chart").getAttribute("data-option");
    const option = JSON.parse(raw!);

    // Unified axis should have 2 timestamps (not 3)
    expect(option.xAxis.data).toHaveLength(2);

    // EMA9 series: both slots filled
    expect(option.series[0].data[0]).toBe(100);
    expect(option.series[0].data[1]).toBe(101);

    // EMA21 series: first slot is null (no data at 04:00), second is 99
    expect(option.series[1].data[0]).toBeNull();
    expect(option.series[1].data[1]).toBe(99);
  });

  it("handles a single series without null filling", () => {
    const { getByTestId } = render(
      <LineChart
        data-testid="chart"
        series={[
          {
            name: "Price",
            data: [
              { ts: "2026-05-19T04:00:00Z", value: 200 },
              { ts: "2026-05-19T04:05:00Z", value: 210 },
              { ts: "2026-05-19T04:10:00Z", value: 205 },
            ],
          },
        ]}
      />
    );

    const option = JSON.parse(getByTestId("chart").getAttribute("data-option")!);
    expect(option.xAxis.data).toHaveLength(3);
    expect(option.series[0].data).toEqual([200, 210, 205]);
  });

  it("sets connectNulls: false", () => {
    const { getByTestId } = render(
      <LineChart data-testid="chart" series={[{ name: "A", data: [{ ts: "T", value: 1 }] }]} />
    );
    const option = JSON.parse(getByTestId("chart").getAttribute("data-option")!);
    expect(option.series[0].connectNulls).toBe(false);
  });
});
