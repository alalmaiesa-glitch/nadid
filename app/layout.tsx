import type { Metadata } from "next";
import {
  Alexandria,
  Almarai,
  Cairo,
  IBM_Plex_Sans_Arabic,
  Readex_Pro
} from "next/font/google";
import "./globals.css";

const cairo = Cairo({
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-display"
});

const alexandria = Alexandria({
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-heading"
});

const almarai = Almarai({
  weight: ["400", "700", "800"],
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-short"
});

const ibmPlex = IBM_Plex_Sans_Arabic({
  weight: ["400", "500", "600", "700"],
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-ui"
});

const readex = Readex_Pro({
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-body"
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
          cairo.variable,
          alexandria.variable,
          almarai.variable,
          ibmPlex.variable,
          readex.variable
        ].join(" ")}
      >
        {children}
      </body>
    </html>
  );
}
