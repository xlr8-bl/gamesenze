"use client";

import { useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { fetchBoard, isConfigured, type Pick } from "@/lib/supabase";
import { competitionIdentity, competitionSurface } from "@/lib/identity";
import { ClubBadge, CompetitionMark, Countdown, Drift, KickoffLine } from "./sport";

/**
 * The hero, and the strip under it.
 *
 * The headline of this site is whatever match is next, so the hero is built
 * from live data rather than from copy. Until the board answers it renders a
 * placeholder of the same height, so the page does not jump when the data
 * lands: the alternative is a hero that reflows under the reader's thumb.
 */
export default function HomeLive() {
  const [picks, setPicks] = useState<Pick[] | null>(null);

  useEffect(() => {
    if (!isConfigured) {
      setPicks([]);
      return;
    }
    let live = true;
    fetchBoard()
      .then((rows) => live && setPicks(rows))
      .catch(() => live && setPicks([]));
    return () => {
      live = false;
    };
  }, []);

  const open = (picks ?? [])
    .filter((p) => new Date(p.kickoff_at).getTime() > Date.now())
    .sort((a, b) => a.kickoff_at.localeCompare(b.kickoff_at));
  const feature = open[0];
  const rest = open.slice(1, 5);
  const identity = competitionIdentity(feature?.competition);

  return (
    <section style={{ position: "relative" }}>
      {/* Poster ground. It runs behind the header, so the nav floats on art. */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: "-68px 0 auto 0",
          height: "min(760px, 92vh)",
          ...competitionSurface(identity),
          maskImage: "linear-gradient(180deg, #000 55%, transparent 100%)",
          WebkitMaskImage: "linear-gradient(180deg, #000 55%, transparent 100%)",
        }}
      />

      <div className="shell" style={{ position: "relative", paddingTop: "var(--s-7)" }}>
        {feature ? (
          <>
            <div className="cluster" style={{ gap: "var(--s-3)", marginBottom: "var(--s-4)" }}>
              <CompetitionMark competition={feature.competition} size={30} />
              <span
                className="cond"
                style={{
                  fontWeight: 700,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  fontSize: "var(--t-small)",
                }}
              >
                {identity.name}
              </span>
              <span className="chip chip-outline-brand">Next up</span>
            </div>

            <h1
              className="poster rise"
              style={{ fontSize: "var(--t-poster)", maxWidth: "13ch" }}
            >
              {feature.home_team}
              <span style={{ color: "var(--brand)" }}> v </span>
              {feature.away_team}
            </h1>

            <div
              className="cluster rise"
              style={{ ["--i" as string]: 1, gap: "var(--s-5)", marginTop: "var(--s-5)" }}
            >
              <div>
                <div className="label">Kicks off in</div>
                <Countdown to={feature.kickoff_at} />
              </div>
              <div>
                <div className="label">Our pick</div>
                <div className="cond" style={{ fontWeight: 700, fontSize: "1.125rem" }}>
                  {feature.selection}
                  <span style={{ color: "var(--ink-3)", fontWeight: 500 }}> · {feature.market}</span>
                </div>
              </div>
              <div>
                <div className="label">Best price</div>
                <div className="cluster" style={{ gap: "var(--s-2)" }}>
                  <span
                    className="cond num"
                    style={{ fontWeight: 700, fontSize: "1.6rem", lineHeight: 1, color: "var(--brand)" }}
                  >
                    {(feature.latest_odds ?? feature.capture_odds ?? 0).toFixed(2)}
                  </span>
                  <Drift from={feature.capture_odds} to={feature.latest_odds} />
                </div>
              </div>
            </div>

            <div className="cluster rise" style={{ ["--i" as string]: 2, gap: "var(--s-3)", marginTop: "var(--s-6)" }}>
              <a href="/board/" className="btn btn-lg">
                See the full board
                <ArrowRight size={17} weight="bold" aria-hidden />
              </a>
              <a href="/record/" className="btn btn-ghost btn-lg">
                Read the record
              </a>
            </div>
          </>
        ) : (
          <>
            <h1 className="poster" style={{ fontSize: "var(--t-poster)", maxWidth: "13ch" }}>
              {picks === null ? "Loading the board" : "No picks on the board"}
            </h1>
            <p style={{ color: "var(--ink-2)", marginTop: "var(--s-4)", maxWidth: "46ch" }}>
              {picks === null
                ? "One moment."
                : "A quiet board is a normal day. If today's data did not clear verification we publish nothing rather than publish something we cannot stand behind."}
            </p>
            <a href="/record/" className="btn btn-lg" style={{ marginTop: "var(--s-5)" }}>
              Read the record
            </a>
          </>
        )}

        {/* The rest of today, as a scrolling rail. */}
        {rest.length > 0 && (
          <div style={{ marginTop: "var(--s-8)" }}>
            <div className="row" style={{ marginBottom: "var(--s-3)" }}>
              <span className="label">Also on the board</span>
              <a
                href="/board/"
                className="cond"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  minHeight: 28,
                  color: "var(--brand)",
                  fontSize: "var(--t-small)",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  textDecoration: "none",
                }}
              >
                All {open.length}
              </a>
            </div>
            <div
              style={{
                display: "grid",
                gap: "var(--s-3)",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
              }}
            >
              {rest.map((p, i) => (
                <a
                  key={p.id}
                  href="/board/"
                  className="panel panel-pad rise"
                  style={{ ["--i" as string]: i, textDecoration: "none", display: "block" }}
                >
                  <div className="cluster" style={{ justifyContent: "space-between", marginBottom: "var(--s-3)" }}>
                    <CompetitionMark competition={p.competition} size={22} />
                    <Countdown to={p.kickoff_at} compact />
                  </div>
                  <div className="cluster" style={{ gap: "var(--s-2)", flexWrap: "nowrap", marginBottom: "var(--s-2)" }}>
                    <ClubBadge name={p.home_team} size={24} />
                    <ClubBadge name={p.away_team} size={24} />
                  </div>
                  <div className="cond" style={{ fontWeight: 600, fontSize: "1rem", lineHeight: 1.2 }}>
                    {p.home_team} v {p.away_team}
                  </div>
                  <div style={{ marginTop: "var(--s-2)" }}>
                    <KickoffLine at={p.kickoff_at} />
                  </div>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
