const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

export function toIST(isoStr: string): Date {
  const d = new Date(isoStr);
  return new Date(d.getTime() + IST_OFFSET_MS);
}

export function formatTimeIST(isoStr: string, includeSecs = false): string {
  const d = toIST(isoStr);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  if (includeSecs) {
    const ss = String(d.getUTCSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }
  return `${hh}:${mm}`;
}

export function formatRupee(value: number | null | undefined): string {
  if (value == null) return "—";
  return "₹" + value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatRupeeShort(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(1)}Cr`;
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(1)}L`;
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)}K`;
  return `${sign}₹${abs.toFixed(2)}`;
}

export function formatPct(value: number): string {
  return (value * 100).toFixed(2) + "%";
}
