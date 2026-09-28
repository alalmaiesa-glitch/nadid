import type { Metadata } from "next";
import "./globals.css";

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
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Alexandria:wght@400;500;600;700;800&family=Cairo:wght@600;700;800&family=Readex+Pro:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
