import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "GameSenze",
  description:
    "Curated football and NBA analysis. We show the maths; you place the bets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="wrap">
          <header className="site">
            <h1>GameSenze</h1>
            <nav>
              <a href="/board/">Board</a>
              <a href="/combo-builder/">Combo builder</a>
            </nav>
          </header>
          {children}
          <p className="footnote">
            Analytics and visualisation only. We don&apos;t hold funds or
            execute wagers; you place bets at your sportsbook. 18+. Odds shown
            with the time they were captured, not live quotes.
          </p>
        </div>
      </body>
    </html>
  );
}
