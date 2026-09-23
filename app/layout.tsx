import type { Metadata } from "next";
import {
  Alexandria,
  Readex_Pro
} from "next/font/google";
import "./globals.css";

const interfaceFont = Alexandria({
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-interface"
});

const readingFont = Readex_Pro({
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-reading"
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
      <body
        className={[
          interfaceFont.variable,
          readingFont.variable
        ].join(" ")}
      >
        {children}
      </body>
    </html>
  );
}
