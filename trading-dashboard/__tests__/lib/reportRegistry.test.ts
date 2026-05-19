import { describe, it, expect } from "vitest";
import { REPORT_VIEWS } from "@/lib/reportRegistry";

describe("REPORT_VIEWS", () => {
  it("contains backtest view", () => {
    expect(REPORT_VIEWS["backtest"]).toBeDefined();
  });

  it("contains monte_carlo view", () => {
    expect(REPORT_VIEWS["monte_carlo"]).toBeDefined();
  });

  it("contains walk_forward view", () => {
    expect(REPORT_VIEWS["walk_forward"]).toBeDefined();
  });

  it("returns undefined for unknown type", () => {
    expect(REPORT_VIEWS["unknown_type"]).toBeUndefined();
  });
});
