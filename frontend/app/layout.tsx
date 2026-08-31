import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "FinContract AI", description: "금융 계약 검토 보조" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ko"><body>{children}</body></html>;
}
