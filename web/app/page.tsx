import HomeLive from "@/components/HomeLive";
import { Notice } from "@/components/ui";
import { COMPETITIONS, competitionSurface } from "@/lib/identity";
import { competitionPhoto } from "@/lib/media";
import { CompetitionMark } from "@/components/sport";
import { Reveal } from "@/components/motion";

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
          its own band, cut across the page on a slant rather than stacked
          under a horizontal rule. */}
      <section
        className="cut-top grain"
        style={{ position: "relative", background: "var(--surface)", paddingBottom: "var(--s-7)" }}
      >
      <div className="shell">
        <SectionHead>What we cover</SectionHead>
        <div className="rail">
          {COMPETITIONS.map((c, i) => {
            const photo = competitionPhoto(c.key);
            return (
              <div
                key={c.key}
                className={`reveal is-in ${photo ? "photo photo-deep" : ""}`}
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
      </div>
      </section>

      {/* How a pick gets made. A real sequence, so it is numbered, and laid
          out along a single rule rather than as four identical boxes: four
          equal cards in a row is the most template-shaped thing a page can
          do. */}
      <section className="shell" style={{ paddingTop: "var(--s-8)" }}>
        <SectionHead>The bar every pick clears</SectionHead>
        <ol className="steps">
          {[
            ["Modelled", "Every fixture is priced by our own model before a single bookmaker line is looked at, so the number we work from is ours, not the market's echo."],
            ["Only where it's wrong", "A pick is drafted only where the price is wrong in our favour by a margin that survives the variance. Fair prices get no pick."],
            ["Read by a person", "Nothing auto-publishes. A person signs off every pick, and anything the data can't stand behind is pulled before it reaches you."],
            ["Quiet when it should be", "A day with two picks and a day with none are both normal. We would rather post nothing than post filler."],
          ].map(([title, body], i) => (
            <Reveal as="li" key={title} className="step" delay={i * 90}>
              <span className="step-dot" aria-hidden />
              <span className="poster step-num">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="cond" style={{ textTransform: "uppercase", letterSpacing: "0.06em", fontSize: "1.125rem" }}>
                {title}
              </h3>
              <p style={{ color: "var(--ink-3)", fontSize: "var(--t-small)", marginTop: "var(--s-2)", marginBottom: 0 }}>
                {body}
              </p>
            </Reveal>
          ))}
        </ol>
      </section>

      {/* The differentiator, shown rather than described. */}
      <section
        className="cut-both grain"
        style={{ position: "relative", background: "var(--surface)", marginTop: "var(--s-8)" }}
      >
      <div className="shell">
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
              style={{ fontSize: "clamp(1.9rem, 1.2rem + 3vw, 3.5rem)", maxWidth: "13ch" }}
              aria-label="Where the evidence ran out"
            >
              Where the
              <br />
              <span className="poster-outline">evidence</span>
              <br />
              ran out
            </h2>
            <p style={{ color: "var(--ink-2)", marginTop: "var(--s-4)" }}>
              Early in a season, half the numbers are noise. We say so on the
              pick rather than dress a thin sample up as a signal. Where a
              factor is not ready to lean on, the card tells you, and the read
              leans on last season's baselines until this one has caught up.
            </p>
            <a href="/record/" className="btn btn-ghost" style={{ marginTop: "var(--s-4)" }}>
              See the record
            </a>
          </div>
          <div className="stack-s">
            <Notice tone="caution">
              <strong>Referee tendency</strong> is on too thin a sample at this
              level to lean on yet. This pick leaves it out.
            </Notice>
            <Notice tone="caution">
              <strong>Finishing variance</strong> is provisional this early, so
              it is weighted down rather than leaned on.
            </Notice>
            <Notice>
              <strong>Prices</strong> outside the final hours before kickoff are
              refreshing less often today. Each carries the time it was read.
            </Notice>
          </div>
        </div>
      </div>
      </section>
    </>
  );
}
