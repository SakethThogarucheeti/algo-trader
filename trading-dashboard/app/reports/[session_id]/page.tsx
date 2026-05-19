import { T } from "@/lib/echarts";
import { fetchReport } from "@/lib/api";
import { ReportRenderer } from "@/components/reports/ReportRenderer";
import Link from "next/link";

export default async function ReportDetailPage({
  params,
}: {
  params: Promise<{ session_id: string }>;
}) {
  const { session_id } = await params;

  let report;
  try {
    report = await fetchReport(session_id);
  } catch {
    return (
      <div>
        <Link
          href="/reports"
          style={{ color: T.muted, fontSize: 12, textDecoration: "none", display: "block", marginBottom: 16 }}
        >
          ← Back to Reports
        </Link>
        <div
          style={{
            padding: 40,
            textAlign: "center",
            color: T.neg,
            backgroundColor: T.surface,
            border: `1px solid ${T.border}`,
            borderRadius: 8,
          }}
        >
          Report not found: <code>{session_id}</code>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Link
        href="/reports"
        style={{ color: T.muted, fontSize: 12, textDecoration: "none", display: "block", marginBottom: 16 }}
      >
        ← Back to Reports
      </Link>
      <ReportRenderer report={report} />
    </div>
  );
}
