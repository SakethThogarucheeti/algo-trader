"use client";

import type { AnyReport } from "@/lib/api";
import { REPORT_VIEWS } from "@/lib/reportRegistry";
import { UnknownReportFallback } from "./UnknownReportFallback";

export function ReportRenderer({ report }: { report: AnyReport }) {
  const View = REPORT_VIEWS[(report as { session_type: string }).session_type];
  if (!View) {
    return (
      <UnknownReportFallback
        type={(report as { session_type: string }).session_type}
        report={report}
      />
    );
  }
  return <View report={report} />;
}
