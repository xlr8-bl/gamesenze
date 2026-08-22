import HomeLive from "@/components/HomeLive";
import { Notice } from "@/components/ui";
import { COMPETITIONS, competitionSurface } from "@/lib/identity";
import { competitionPhoto } from "@/lib/media";
import { CompetitionMark } from "@/components/sport";

/**
 * The home page.
 *
 * The hero is the next real fixture on the board, rendered as a poster in its
 * competition's colours. Everything above the fold is live: if the board is
 * empty the hero says so rather than showing a stock headline over nothing.
 */
/** The broadcast slab, used wherever a section opens. */
function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: "var(--s-4)" }}>
      <h2 className="slab slab-brand" style={{ fontSize: "1.25rem" }}>
        {children}
      </h2>
      <span aria-hidden style={{ flex: 1, height: 1, background: "var(--line)" }} />
    </div>
  );
}

export default function Home() {
  return (
    <>
      <HomeLive />

      {/* Competition rail. The calendar is the product's texture, so it gets
          its own band rather than a line of grey text. */}
      <section className="shell" style={{ paddingTop: "var(--s-7)" }}>
        <SectionHead>What we cover</SectionHead>
        <div className="rail">
          {COMPETITIONS.map((c, i) => {
            const photo = competitionPhoto(c.key);
            return (
              <div
                key={c.key}
                className={`rise ${photo ? "photo photo-deep" : ""}`}
                style={{
                  ...(photo ? {} : competitionSurface(c, 0.45)),
                  ["--i" as string]: Math.min(i, 8),
                  borderRadius: "var(--r-3)",
                  border: "1px solid var(--line)",
                  padding: "var(--s-4)",
                  minWidth: 210,
                  minHeight: 150,
                  scrollSnapAlign: "start",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: "var(--s-3)",
                  overflow: "hidden",
                }}
              >
                {photo && <img src={photo} alt="" aria-hidden loading="lazy" decoding="async" />}
                <span
                  aria-hidden
                  style={{
                    position: "absolute",
                    left: 0,
                    top: 0,
                    bottom: 0,
                    width: 4,
                    background: c.accent,
                    boxShadow: `0 0 20px -2px ${c.accent}`,
                  }}
                />
                <div style={{ position: "relative" }}>
                  <CompetitionMark competition={c.name} size={32} />
                </div>
                <div style={{ position: "relative" }}>
                  <div
                    className="cond"
                    style={{
                      fontWeight: 700,
                      fontSize: "1.0625rem",
                      lineHeight: 1.1,
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                    }}
                  >
                    {c.name}
                  </div>
                  <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>{c.country}</div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* How a pick gets made. A real sequence, so it is numbered, and laid
          out along a single rule rather than as four identical boxes: four
          equal cards in a row is the most template-shaped thing a page can
          do. */}
      <section className="shell" style={{ paddingTop: "var(--s-8)" }}>
        <SectionHead>How a pick reaches the board</SectionHead>
        <ol className="steps">
          {[
            ["Sync", "Fixtures from football-data.org, prices from a shared odds feed. Every club name resolves to one canonical team or the fixture is held back rather than guessed at."],
            ["Price", "Team form, expected goals and defensive pressure produce our own probability. That number exists before any bookmaker's price is looked at."],
            ["Compare", "A pick is drafted only where our number beats the price's implied probability by a margin worth the variance."],
            ["Gate", "A person reads it. Anything carrying an unresolved data flag never publishes. A day with no picks is a normal day."],
          ].map(([title, body], i) => (
            <li key={title} className="step rise" style={{ ["--i" as string]: i }}>
              <span className="step-dot" aria-hidden />
              <span className="poster step-num">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="cond" style={{ textTransform: "uppercase", letterSpacing: "0.06em", fontSize: "1.125rem" }}>
                {title}
              </h3>
              <p style={{ color: "var(--ink-3)", fontSize: "var(--t-small)", marginTop: "var(--s-2)", marginBottom: 0 }}>
                {body}
              </p>
            </li>
          ))}
        </ol>
      </section>

      {/* The differentiator, shown rather than described. */}
      <section className="shell" style={{ paddingTop: "var(--s-8)" }}>
        <div
          style={{
            display: "grid",
            gap: "var(--s-5)",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            alignItems: "center",
          }}
        >
          <div>
            <h2
              className="poster"
              style={{ fontSize: "clamp(1.75rem, 1.2rem + 2.6vw, 3rem)", maxWidth: "14ch" }}
            >
              Where the evidence ran out
            </h2>
            <p style={{ color: "var(--ink-2)", marginTop: "var(--s-4)" }}>
              Most factors in a football model rest on a sample too small to
              trust. When one of ours does, we do not quietly drop it and
              publish the rest. It appears on the pick itself, with the sample
              we actually had. Two examples of the wording:
            </p>
            <a href="/record/" className="btn btn-ghost" style={{ marginTop: "var(--s-4)" }}>
              See the record
            </a>
          </div>
          <div className="stack-s">
            <Notice tone="caution">
              Referee tendency excluded: 6 matches at this level, below the
              20-match minimum. This pick does not use it.
            </Notice>
            <Notice tone="caution">
              Striker finishing variance is provisional: 8 qualifying
              appearances against a 10-match minimum. It is weighted down
              rather than dropped.
            </Notice>
            <Notice>
              Reduced odds cadence today. Prices outside the final three hours
              are updating half as often.
            </Notice>
          </div>
        </div>
      </section>
    </>
  );
}
