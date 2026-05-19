import "@testing-library/jest-dom";
import React from "react";
import { vi } from "vitest";

vi.mock("echarts-for-react", () => ({
  default: ({ option, "data-testid": tid }: { option: unknown; "data-testid"?: string }) =>
    React.createElement("div", {
      "data-testid": tid ?? "echarts",
      "data-option": JSON.stringify(option),
    }),
}));
