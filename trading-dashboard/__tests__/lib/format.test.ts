import { describe, it, expect } from "vitest";
import { toIST, formatTimeIST, formatRupee, formatRupeeShort, formatPct } from "@/lib/format";

describe("toIST", () => {
  it("adds 5.5 hours to UTC", () => {
    const d = toIST("2026-05-19T04:30:00Z");
    expect(d.getUTCHours()).toBe(10);
    expect(d.getUTCMinutes()).toBe(0);
  });

  it("handles midnight UTC → 05:30 IST", () => {
    const d = toIST("2026-05-19T00:00:00Z");
    expect(d.getUTCHours()).toBe(5);
    expect(d.getUTCMinutes()).toBe(30);
  });
});

describe("formatTimeIST", () => {
  it("returns HH:MM by default", () => {
    expect(formatTimeIST("2026-05-19T04:00:00Z")).toBe("09:30");
  });

  it("includes seconds when includeSecs=true", () => {
    expect(formatTimeIST("2026-05-19T04:00:15Z", true)).toBe("09:30:15");
  });
});

describe("formatRupee", () => {
  it("formats with ₹ symbol", () => {
    expect(formatRupee(1234.56)).toContain("1,234.56");
    expect(formatRupee(1234.56)).toContain("₹");
  });

  it("returns dash for null/undefined", () => {
    expect(formatRupee(null)).toBe("—");
    expect(formatRupee(undefined)).toBe("—");
  });
});

describe("formatRupeeShort", () => {
  it("formats crores", () => {
    expect(formatRupeeShort(1_00_00_000)).toBe("₹1.0Cr");
  });

  it("formats lakhs", () => {
    expect(formatRupeeShort(1_00_000)).toBe("₹1.0L");
  });

  it("formats thousands", () => {
    expect(formatRupeeShort(5_000)).toBe("₹5.0K");
  });

  it("handles negatives", () => {
    expect(formatRupeeShort(-1_00_000)).toBe("-₹1.0L");
  });
});

describe("formatPct", () => {
  it("converts fraction to percentage string", () => {
    expect(formatPct(0.15)).toBe("15.00%");
    expect(formatPct(-0.08)).toBe("-8.00%");
  });
});
