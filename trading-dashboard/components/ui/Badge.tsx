import { T } from "@/lib/echarts";

type Variant = "green" | "red" | "amber" | "muted" | "accent";

const COLORS: Record<Variant, { bg: string; text: string }> = {
  green: { bg: T.pos + "26", text: T.pos },
  red: { bg: T.neg + "26", text: T.neg },
  amber: { bg: T.neutral + "26", text: T.neutral },
  muted: { bg: T.border, text: T.muted },
  accent: { bg: T.accent + "26", text: T.accent },
};

interface BadgeProps {
  label: string;
  variant?: Variant;
}

export function Badge({ label, variant = "muted" }: BadgeProps) {
  const { bg, text } = COLORS[variant];
  return (
    <span
      style={{
        backgroundColor: bg,
        color: text,
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        fontFamily: "ui-monospace, monospace",
      }}
    >
      {label}
    </span>
  );
}
