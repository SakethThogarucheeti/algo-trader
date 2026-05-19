"use client";

import { T } from "@/lib/echarts";
import { formatRupee } from "@/lib/format";
import type { PnlSummary } from "@/lib/api";

interface PnlSummaryStripProps {
  summary: PnlSummary;
}

export function PnlSummaryStrip({ summary }: PnlSummaryStripProps) {
  const netColor = summary.net >= 0 ? T.pos : T.neg;

  return (
    <div
      style={{
        display: "flex",
        gap: 24,
        padding: "8px 12px",
        backgroundColor: T.surface,
        borderRadius: 6,
        fontFamily: "ui-monospace, monospace",
        fontSize: 12,
        flexWrap: "wrap",
      }}
    >
      <span>
        <span style={{ color: T.muted }}>Gross </span>
        <span style={{ color: summary.gross >= 0 ? T.pos : T.neg }}>{formatRupee(summary.gross)}</span>
      </span>
      <span>
        <span style={{ color: T.muted }}>Costs </span>
        <span style={{ color: T.neg }}>{formatRupee(summary.costs)}</span>
      </span>
      <span>
        <span style={{ color: T.muted }}>Net </span>
        <span style={{ color: netColor, fontWeight: 700 }}>{formatRupee(summary.net)}</span>
      </span>
      {summary.nifty_pct != null && (
        <span>
          <span style={{ color: T.muted }}>Nifty 50 </span>
          <span style={{ color: summary.nifty_pct >= 0 ? T.pos : T.neg }}>
            {summary.nifty_pct >= 0 ? "+" : ""}
            {summary.nifty_pct.toFixed(2)}%
          </span>
        </span>
      )}
    </div>
  );
}
