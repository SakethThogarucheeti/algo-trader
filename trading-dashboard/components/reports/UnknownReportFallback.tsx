"use client";

import { T } from "@/lib/echarts";

export function UnknownReportFallback({
  type,
  report,
}: {
  type: string;
  report: unknown;
}) {
  return (
    <div>
      <p style={{ color: T.neutral, marginBottom: 12 }}>
        Unknown report type: <strong>{type}</strong>
      </p>
      <pre
        style={{
          backgroundColor: T.surface,
          border: `1px solid ${T.border}`,
          borderRadius: 6,
          padding: 16,
          fontSize: 12,
          color: T.text,
          overflowX: "auto",
          whiteSpace: "pre-wrap",
        }}
      >
        {JSON.stringify(report, null, 2)}
      </pre>
    </div>
  );
}
