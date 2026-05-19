"use client";

import { T } from "@/lib/echarts";
import { formatTimeIST } from "@/lib/format";
import { useDecisionStream } from "@/hooks/useDecisionStream";
import { useDashboardStore } from "@/store";
import { StatusDot } from "@/components/ui/StatusDot";

const STEP_COLOR: Record<string, string> = {
  SIGNAL_ACCEPTED: T.pos,
  SIGNAL_REJECTED: T.neg,
  SIGNAL_GENERATED: T.neutral,
  CANDLE_EMITTED: T.muted,
};

function ctxSnippet(ctx: Record<string, unknown>): string {
  if (ctx.reason) return String(ctx.reason);
  if (ctx.qty) return `qty=${ctx.qty}`;
  const entries = Object.entries(ctx).slice(0, 2);
  return entries.map(([k, v]) => `${k}=${v}`).join(" ");
}

export function DecisionFeed() {
  const sessionId = useDashboardStore((s) => s.sessionId);
  const { events, status } = useDecisionStream(sessionId);

  return (
    <div style={{ fontFamily: "ui-monospace, monospace" }}>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 6 }}>
        <StatusDot status={status} />
      </div>
      <div
        style={{
          height: 280,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column-reverse",
          gap: 2,
        }}
      >
        {[...events].reverse().map((ev) => (
          <div key={ev.id} style={{ fontSize: 11, display: "flex", gap: 8, alignItems: "baseline" }}>
            <span style={{ color: T.muted, minWidth: 56 }}>{formatTimeIST(ev.ts, true)}</span>
            <span style={{ color: T.text, fontWeight: 600, minWidth: 56 }}>{ev.symbol}</span>
            <span style={{ color: STEP_COLOR[ev.step] ?? T.text, minWidth: 140 }}>{ev.step}</span>
            <span style={{ color: T.muted }}>{ctxSnippet(ev.context)}</span>
          </div>
        ))}
        {events.length === 0 && (
          <span style={{ color: T.muted, fontSize: 11 }}>Waiting for events…</span>
        )}
      </div>
    </div>
  );
}
