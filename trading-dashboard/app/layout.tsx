import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { T } from "@/lib/echarts";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Algo Trading Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ backgroundColor: T.bg, color: T.text, minHeight: "100vh" }}>
        <Providers>
          <nav
            style={{
              backgroundColor: T.surface,
              borderBottom: `1px solid ${T.border}`,
              padding: "10px 24px",
              display: "flex",
              gap: 24,
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: 700, fontSize: 15, color: T.text }}>Algo Trading</span>
            <Link href="/" style={{ fontSize: 12 }}>
              Live
            </Link>
            <Link href="/reports" style={{ fontSize: 12 }}>
              Reports
            </Link>
          </nav>
          <main style={{ padding: 24 }}>{children}</main>
        </Providers>
      </body>
    </html>
  );
}
