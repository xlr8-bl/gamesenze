import "./globals.css";
import type { Metadata } from "next";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "GameSenze",
  description:
    "Football and NBA picks with the working shown, including what the data could not tell us.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* The two faces that carry every page. Preloaded because they are
            render-blocking in effect: a numbers page reflowing from a fallback
            metric is worse than a few hundred milliseconds of nothing. */}
        <link
          rel="preload"
          as="font"
          type="font/woff2"
          href="/fonts/Archivo-400-650-latin.woff2"
          crossOrigin=""
        />
        <link
          rel="preload"
          as="font"
          type="font/woff2"
          href="/fonts/IBMPlexMono-400-latin.woff2"
          crossOrigin=""
        />
        <meta name="theme-color" content="#121211" />
      </head>
      <body>
        <Nav />
        <div className="shell">{children}</div>
        <footer
          className="shell"
          style={{ marginTop: "auto", paddingTop: "var(--s-6)" }}
        >
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: "var(--s-4)" }}>
            <p
              style={{
                color: "var(--ink-3)",
                fontSize: "var(--t-small)",
                maxWidth: "72ch",
              }}
            >
            Analysis and visualisation only. We do not hold funds or place
            wagers; you place bets at your own sportsbook. Odds are shown with
            the time they were captured, and are not live quotes. 18+.
              Gambling can be addictive: in the UK, help is at
              BeGambleAware.org.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
