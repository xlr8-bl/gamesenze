import "./globals.css";
import type { Metadata } from "next";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "GameSenze",
  description:
    "Football picks with the working shown. Every price against our own number, and every gap in the evidence named on the card.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preload" as="font" type="font/woff2" href="/fonts/Anton-400-latin.woff2" crossOrigin="" />
        <link rel="preload" as="font" type="font/woff2" href="/fonts/BarlowCondensed-700-latin.woff2" crossOrigin="" />
        <link rel="preload" as="font" type="font/woff2" href="/fonts/Barlow-400-latin.woff2" crossOrigin="" />
        <meta name="theme-color" content="#080B10" />
      </head>
      <body>
        <Nav />
        <main style={{ flex: 1 }}>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
