"use client";

import type { MonteCarloReport } from "@/lib/api";
import { T } from "@/lib/echarts";
import { formatPct } from "@/lib/format";
import { ReturnDistHistogram } from "@/components/charts/ReturnDistHistogram";
import { DrawdownDistHistogram } from "@/components/charts/DrawdownDistHistogram";
import { RuinGauge } from "@/components/charts/RuinGauge";

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      style={{
        backgroundColor: T.surface,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        padding: "12px 16px",
      }}
    >
      <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color: color ?? T.text, fontSize: 20, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

export function MonteCarloView({ report }: { report: MonteCarloReport }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          backgroundColor: T.surface,
          border: `1px solid ${T.border}`,
          borderRadius: 8,
          display: "flex",
          gap: 32,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Trials</div>
          <div style={{ color: T.text, fontWeight: 600 }}>{report.n_trials.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Method</div>
          <div style={{ color: T.text }}>{report.method}</div>
        </div>
        <div>
          <div style={{ color: T.muted, fontSize: 11, textTransform: "uppercase" }}>Session</div>
          <div style={{ color: T.text, fontFamily: "monospace" }}>{report.session_id}</div>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <StatCard label="5th Pct Return" value={formatPct(report.percentile_5_return)} color={T.neg} />
        <StatCard label="95th Pct Return" value={formatPct(report.percentile_95_return)} color={T.pos} />
        <StatCard label="Median Drawdown" value={formatPct(report.median_drawdown)} color={T.neutral} />
        <StatCard
          label="Ruin Probability"
          value={formatPct(report.probability_of_ruin)}
          color={report.probability_of_ruin > 0.05 ? T.neg : report.probability_of_ruin > 0.01 ? T.neutral : T.pos}
        />
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 300px", gap: 16 }}>
        <ReturnDistHistogram
          returnDistribution={report.return_distribution}
          percentile5={report.percentile_5_return}
          percentile95={report.percentile_95_return}
          height={280}
        />
        <DrawdownDistHistogram drawdownDistribution={report.drawdown_distribution} height={280} />
        <RuinGauge probabilityOfRuin={report.probability_of_ruin} height={280} />
      </div>
    </div>
  );
}
