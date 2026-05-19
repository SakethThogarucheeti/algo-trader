import { T } from "@/lib/echarts";
import { fetchReportSessions } from "@/lib/api";
import type { ReportSessionMeta } from "@/lib/api";
import Link from "next/link";

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    backtest: T.accent,
    monte_carlo: T.neutral,
    walk_forward: T.pos,
  };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        backgroundColor: colors[type] ?? T.muted,
        color: "#fff",
        textTransform: "uppercase",
      }}
    >
      {type.replace("_", " ")}
    </span>
  );
}

export default async function ReportsPage() {
  let sessions: ReportSessionMeta[] = [];
  try {
    sessions = await fetchReportSessions();
  } catch {
    // backend may be unreachable — show empty state
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 24,
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 700, color: T.text }}>Reports</h1>
        <div style={{ display: "flex", gap: 8 }}>
          {(["day", "week", "month"] as const).map((p) => (
            <Link
              key={p}
              href={`/reports/live?period=${p}`}
              style={{
                padding: "6px 14px",
                backgroundColor: T.surface,
                border: `1px solid ${T.border}`,
                borderRadius: 6,
                color: T.text,
                fontSize: 12,
                textDecoration: "none",
              }}
            >
              Live {p}
            </Link>
          ))}
        </div>
      </div>

      {sessions.length === 0 ? (
        <div
          style={{
            padding: 40,
            textAlign: "center",
            color: T.muted,
            backgroundColor: T.surface,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
          }}
        >
          No reports found. Run a backtest to generate reports.
        </div>
      ) : (
        <div
          style={{
            backgroundColor: T.surface,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ backgroundColor: T.grid }}>
                {["Type", "Algo", "Session ID", "Started", "Finished"].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "10px 16px",
                      color: T.muted,
                      fontWeight: 500,
                      fontSize: 11,
                      textTransform: "uppercase",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr
                  key={s.session_id}
                  style={{ borderTop: `1px solid ${T.border}` }}
                >
                  <td style={{ padding: "10px 16px" }}>
                    <TypeBadge type={s.session_type} />
                  </td>
                  <td style={{ padding: "10px 16px", color: T.text }}>
                    {s.algo_name ?? "—"}
                  </td>
                  <td style={{ padding: "10px 16px" }}>
                    <Link
                      href={`/reports/${encodeURIComponent(s.session_id)}`}
                      style={{ color: T.accent, textDecoration: "none", fontFamily: "monospace" }}
                    >
                      {s.session_id}
                    </Link>
                  </td>
                  <td style={{ padding: "10px 16px", color: T.muted }}>
                    {s.started_at ? new Date(s.started_at).toLocaleString() : "—"}
                  </td>
                  <td style={{ padding: "10px 16px", color: T.muted }}>
                    {s.finished_at ? new Date(s.finished_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
