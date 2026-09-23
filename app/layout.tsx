import type { Metadata } from "next";
import { Noto_Sans_Arabic } from "next/font/google";
import "./globals.css";

const arabic = Noto_Sans_Arabic({
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-arabic"
});

export const metadata: Metadata = {
  title: "نَضِيد | محرر العربية الذكي",
  description:
    "نَضِيد يراجع اللغة والصياغة والسياق والاتساق في المستندات العربية الطويلة، مع حماية المعنى والحقائق."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ar" dir="rtl">
      <body className={arabic.variable}>{children}</body>
    </html>
  );
}
