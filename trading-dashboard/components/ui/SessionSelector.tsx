"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchSessions } from "@/lib/api";
import { useDashboardStore } from "@/store";
import { T } from "@/lib/echarts";

export function SessionSelector() {
  const { sessionId, setSessionId } = useDashboardStore();
  const { data: sessions = [] } = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
    refetchInterval: 60_000,
  });

  return (
    <select
      value={sessionId}
      onChange={(e) => setSessionId(e.target.value)}
      style={{
        backgroundColor: T.surface,
        color: T.text,
        border: `1px solid ${T.border}`,
        borderRadius: 4,
        padding: "4px 8px",
        fontSize: 12,
        fontFamily: "ui-monospace, monospace",
        cursor: "pointer",
      }}
    >
      <option value="">live</option>
      {sessions
        .filter((s): s is string => s !== null)
        .map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
    </select>
  );
}
