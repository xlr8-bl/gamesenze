import { Notice } from "@/components/ui";
import TodayStrip from "@/components/TodayStrip";

/**
 * The home page has one job: tell someone what the number on the board means
 * before they read one. Everything on it is either a real fact about how the
 * pipeline works or a live reading from it. There is no illustration, because
 * there is nothing here a picture would explain better than the data itself.
 */
export default function Home() {
  return (
    <main className="stack" style={{ gap: "var(--s-7)" }}>
      {/*
        Hero. The right column is not decoration: it is the live state of the
        product, which is the most honest thing this page can put next to a
        claim about the product. It collapses under the text on a phone.
      */}
      <section className="hero-grid" style={{ paddingTop: "var(--s-5)" }}>
        <div>
          <h1
            style={{
              fontSize: "var(--t-display)",
              fontWeight: 650,
              letterSpacing: "-0.035em",
              maxWidth: "17ch",
            }}
          >
            The picks, and the gaps in them.
          </h1>
          <p
            style={{
              color: "var(--ink-2)",
              fontSize: "1.0625rem",
              maxWidth: "46ch",
              margin: "var(--s-4) 0 var(--s-5)",
            }}
          >
            At most four football picks a day, each priced against the market
            and published with the gaps in its own evidence named on the card.
          </p>
          <div className="cluster" style={{ gap: "var(--s-3)" }}>
            <a href="/board/" className="btn">
              See today&apos;s board
            </a>
            <a href="/record/" className="btn btn-ghost">
              Read the record
            </a>
          </div>
        </div>
        <TodayStrip />
      </section>

      {/* Layout family: ordered ledger. */}
      <section>
        <h2>How a pick reaches the board</h2>
        <ol className="panel panel-flush ledger" style={{ margin: "var(--s-4) 0 0", padding: 0, listStyle: "none", counterReset: "step" }}>
          {[
            [
              "Fixtures and prices are synced",
              "Schedules from football-data.org, prices from a shared odds feed. Every team name resolves to one canonical club or the fixture is held back rather than guessed at.",
            ],
            [
              "The model prices the match",
              "Team form, expected goals and defensive pressure produce a probability. That number exists before any bookmaker's price is looked at.",
            ],
            [
              "The market is compared, not followed",
              "A pick is drafted only where our probability beats the implied probability of the best available price by a margin worth the variance.",
            ],
            [
              "A person reads it, or it does not publish",
              "Anything carrying an unresolved data flag is blocked at this gate. A day with no picks is a normal day and happens often.",
            ],
          ].map(([title, body], i) => (
            <li key={title} className="ledger-row">
              <div
                className="cluster"
                style={{ gap: "var(--s-3)", alignItems: "baseline", flexWrap: "nowrap" }}
              >
                <span
                  className="num"
                  style={{ color: "var(--ink-3)", fontSize: "var(--t-small)", flex: "none" }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3>{title}</h3>
              </div>
              <p style={{ color: "var(--ink-2)", margin: "var(--s-2) 0 0", paddingLeft: 30 }}>
                {body}
              </p>
            </li>
          ))}
        </ol>
      </section>

      {/* Layout family: prose beside a live artifact. */}
      <section
        style={{
          display: "grid",
          gap: "var(--s-5)",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          alignItems: "start",
        }}
      >
        <div>
          <h2>Where the evidence ran out</h2>
          <p style={{ color: "var(--ink-2)", marginTop: "var(--s-3)" }}>
            Most factors in a football model rest on a sample too small to
            trust. When one of ours does, we do not quietly drop it and publish
            the rest. It appears on the pick itself, with the sample we
            actually had. Two examples of the wording:
          </p>
        </div>
        <div className="stack-s">
          <Notice tone="caution">
            Referee tendency excluded: 6 matches at this level, below the
            20-match minimum. The pick does not use it.
          </Notice>
          <Notice>
            Prices last captured 34 minutes ago. Confirm at your book before
            staking.
          </Notice>
        </div>
      </section>

      {/* Layout family: closing prose, single column, no card. */}
      <section>
        <h2>Stacking picks</h2>
        <p style={{ color: "var(--ink-2)", marginTop: "var(--s-3)", maxWidth: "60ch" }}>
          Stack two to five published picks and see the combined price, what a
          stake returns, and how combos that size have actually settled.
        </p>
        <p style={{ color: "var(--ink-2)", maxWidth: "60ch" }}>
          Two legs on one fixture are correlated, so the builder says so rather
          than printing a confident number it cannot defend. It places nothing:
          you copy the slip to your own book.
        </p>
        <a href="/combo-builder/" className="btn btn-ghost" style={{ marginTop: "var(--s-4)" }}>
          Open the combo builder
        </a>
      </section>
    </main>
  );
}
