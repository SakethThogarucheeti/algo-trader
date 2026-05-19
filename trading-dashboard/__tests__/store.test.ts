import { describe, it, expect, beforeEach } from "vitest";
import { useDashboardStore } from "@/store";

describe("DashboardStore", () => {
  beforeEach(() => {
    // Reset to defaults
    useDashboardStore.setState({ sessionId: "", symbol: "INFY", interval: "5min" });
  });

  it("has correct initial state", () => {
    const { sessionId, symbol, interval } = useDashboardStore.getState();
    expect(sessionId).toBe("");
    expect(symbol).toBe("INFY");
    expect(interval).toBe("5min");
  });

  it("setSessionId updates sessionId", () => {
    useDashboardStore.getState().setSessionId("bt-test-001");
    expect(useDashboardStore.getState().sessionId).toBe("bt-test-001");
  });

  it("setSymbol updates symbol", () => {
    useDashboardStore.getState().setSymbol("TCS");
    expect(useDashboardStore.getState().symbol).toBe("TCS");
  });

  it("setInterval updates interval", () => {
    useDashboardStore.getState().setInterval("15min");
    expect(useDashboardStore.getState().interval).toBe("15min");
  });
});
