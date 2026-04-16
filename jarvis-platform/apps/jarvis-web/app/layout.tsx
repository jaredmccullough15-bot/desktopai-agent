import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Bill Platform",
  description: "Bill Platform Dashboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
