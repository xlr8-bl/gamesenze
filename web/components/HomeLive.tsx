"use client";

import { useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { fetchBoard, isConfigured, type Pick } from "@/lib/supabase";
import { competitionIdentity } from "@/lib/identity";
import { fixturePhoto } from "@/lib/media";
import {
  ClubBadge,
  CompetitionMark,
  Countdown,
  Drift,
  KickoffLine,
} from "./sport";

/**
 * The hero, and the ticker under it.
 *
 * The headline of this site is whatever match is next, so the hero is a
 * photograph of the ground it is being played at, with the fixture set over
 * it at poster scale. It is built from live data rather than copy: if the
 * board is empty the hero says so instead of showing a stock headline over
 * nothing.
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
  const identity = competitionIdentity(feature?.competition);
  const photo = feature
    ? fixturePhoto(feature.home_team, feature.away_team, 0, identity.key)
    : null;

  return (
    <>
      <section
        className="photo"
        style={{
          marginTop: -68,
          paddingTop: 68,
          minHeight: "min(84vh, 760px)",
          display: "flex",
          alignItems: "flex-end",
          borderBottom: "1px solid var(--line)",
        }}
      >
        {photo ? (
          <img src={photo} alt="" aria-hidden fetchPriority="high" />
        ) : (
          <div
            aria-hidden
            style={{
              position: "absolute",
              inset: 0,
              zIndex: -2,
              backgroundColor: identity.accent2,
              backgroundImage: `radial-gradient(120% 90% at 12% -20%, ${identity.accent}66 0%, transparent 58%)`,
            }}
          />
        )}

        <div className="shell" style={{ paddingBottom: "var(--s-7)", paddingTop: "var(--s-8)" }}>
          {feature ? (
            <>
              <div className="cluster" style={{ gap: "var(--s-3)", marginBottom: "var(--s-4)" }}>
                <CompetitionMark competition={feature.competition} size={34} />
                <span
                  className="cond"
                  style={{
                    fontWeight: 700,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    fontSize: "var(--t-small)",
                  }}
                >
                  {identity.name}
                </span>
                <span className="chip chip-brand">Next up</span>
              </div>

              {/* Crests overlapping the headline, the way a match graphic
                  stacks them, rather than a tidy row above it. */}
              <div
                className="cluster rise"
                style={{ gap: "var(--s-2)", marginBottom: "var(--s-3)", flexWrap: "nowrap" }}
              >
                <ClubBadge name={feature.home_team} size={64} />
                <span
                  className="poster"
                  style={{ fontSize: "2rem", color: "var(--brand)", margin: "0 2px" }}
                >
                  v
                </span>
                <ClubBadge name={feature.away_team} size={64} />
              </div>

              <h1
                className="poster rise"
                style={{ ["--i" as string]: 1, fontSize: "var(--t-poster)", maxWidth: "15ch" }}
              >
                {feature.home_team}
                <br />
                <span style={{ color: "var(--brand)" }}>v </span>
                {feature.away_team}
              </h1>

              <div
                className="cluster rise"
                style={{ ["--i" as string]: 2, gap: "var(--s-6)", marginTop: "var(--s-5)" }}
              >
                <div>
                  <div className="label">Kicks off in</div>
                  <Countdown to={feature.kickoff_at} />
                </div>
                <div>
                  <div className="label">Our pick</div>
                  <div className="cond" style={{ fontWeight: 700, fontSize: "1.25rem", lineHeight: 1.1 }}>
                    {feature.selection}
                  </div>
                  <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
                    {feature.market}
                  </div>
                </div>
                <div>
                  <div className="label">Best price</div>
                  <div className="cluster" style={{ gap: "var(--s-2)" }}>
                    <span
                      className="cond num"
                      style={{ fontWeight: 700, fontSize: "2rem", lineHeight: 1, color: "var(--brand)" }}
                    >
                      {(feature.latest_odds ?? feature.capture_odds ?? 0).toFixed(2)}
                    </span>
                    <Drift from={feature.capture_odds} to={feature.latest_odds} />
                  </div>
                </div>
              </div>

              <div
                className="cluster rise"
                style={{ ["--i" as string]: 3, gap: "var(--s-3)", marginTop: "var(--s-6)" }}
              >
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
        </div>
      </section>

      {open.length > 1 && <Ticker picks={open} />}
    </>
  );
}

/**
 * The price ticker.
 *
 * The one marquee on the site, and it carries live prices rather than logos.
 * The track is duplicated so the loop has no seam, and the copy is hidden from
 * assistive technology so a screen reader hears each fixture once.
 */
function Ticker({ picks }: { picks: Pick[] }) {
  const row = picks.map((p) => (
    <span key={p.id} className="cluster" style={{ gap: "var(--s-2)", flexWrap: "nowrap" }}>
      <ClubBadge name={p.home_team} size={20} />
      <span className="cond" style={{ fontWeight: 600, whiteSpace: "nowrap", letterSpacing: "0.02em" }}>
        {p.home_team} v {p.away_team}
      </span>
      <span className="cond num" style={{ color: "var(--brand)", fontWeight: 700 }}>
        {(p.latest_odds ?? p.capture_odds ?? 0).toFixed(2)}
      </span>
      <Drift from={p.capture_odds} to={p.latest_odds} />
    </span>
  ));

  return (
    <div className="ticker" aria-label="Current prices on the board">
      <div className="ticker-track">
        <span className="cluster" style={{ gap: "var(--s-6)", flexWrap: "nowrap", paddingLeft: "var(--s-4)" }}>
          {row}
        </span>
        <span
          className="cluster"
          aria-hidden
          style={{ gap: "var(--s-6)", flexWrap: "nowrap", paddingLeft: "var(--s-6)" }}
        >
          {row}
        </span>
      </div>
    </div>
  );
}
