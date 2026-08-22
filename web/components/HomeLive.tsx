"use client";

import { useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { fetchBoard, isConfigured, type Pick } from "@/lib/supabase";
import { competitionIdentity, fixtureColours } from "@/lib/identity";
import { fixturePhoto, teamMedia } from "@/lib/media";
import { CountUp } from "./motion";
import { ClubBadge, CompetitionMark, Countdown, Drift } from "./sport";

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

  const kit = fixtureColours(feature?.home_team, feature?.away_team);
  const homeCrest = teamMedia(feature?.home_team)?.badge;
  const awayCrest = teamMedia(feature?.away_team)?.badge;

  return (
    <>
      {/*
        The VS graphic: two clubs' colours meeting on a diagonal, their crests
        at poster scale and half out of frame. It is the most recognisable
        composition in football and it is precisely what a grid of cards will
        never give you, which is the point.
      */}
      <section
        className={`vs grain ${photo ? "photo" : ""}`}
        style={{ marginTop: -68, paddingTop: 68 }}
      >
        {photo && <img src={photo} alt="" aria-hidden fetchPriority="high" />}

        {feature && (
          <>
            <div className="vs-half vs-home" style={{ ["--club" as string]: kit.home }}>
              {homeCrest && <img className="vs-crest" src={homeCrest} alt="" aria-hidden />}
            </div>
            <div className="vs-half vs-away" style={{ ["--club" as string]: kit.away }}>
              {awayCrest && <img className="vs-crest" src={awayCrest} alt="" aria-hidden />}
            </div>
          </>
        )}

        <div className="shell" style={{ position: "relative", paddingBottom: "var(--s-7)", paddingTop: "var(--s-8)" }}>
          {feature ? (
            <>
              <div className="cluster" style={{ gap: "var(--s-3)", marginBottom: "var(--s-4)" }}>
                <CompetitionMark competition={feature.competition} size={40} />
                <span
                  className="cond"
                  style={{ fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", fontSize: "var(--t-small)" }}
                >
                  {identity.name}
                </span>
                <span className="chip chip-brand">Next up</span>
              </div>

              {/*
                Home filled, "versus" knocked out, away filled: two weights
                from one typeface. The pieces are separate elements for the
                sake of the layout, which leaves the accessible name running
                the three together, so the h1 carries its own label.
              */}
              <h1
                className="poster"
                style={{ fontSize: "var(--t-poster)", maxWidth: "16ch" }}
                aria-label={`${feature.home_team} versus ${feature.away_team}`}
              >
                <span style={{ display: "block" }}>{feature.home_team}</span>
                <span
                  className="poster-outline"
                  style={{ display: "block", fontSize: "0.62em", letterSpacing: "0.02em" }}
                >
                  versus
                </span>
                <span style={{ display: "block" }}>{feature.away_team}</span>
              </h1>

              <div className="cluster" style={{ gap: "var(--s-6)", marginTop: "var(--s-5)" }}>
                <div>
                  <div className="label">Kicks off in</div>
                  <Countdown to={feature.kickoff_at} />
                </div>
                <div>
                  <div className="label">Our pick</div>
                  <div className="cond" style={{ fontWeight: 700, fontSize: "1.25rem", lineHeight: 1.1 }}>
                    {feature.selection}
                  </div>
                  <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>{feature.market}</div>
                </div>
                <div>
                  <div className="label">Best price</div>
                  <div className="cluster" style={{ gap: "var(--s-2)" }}>
                    <CountUp
                      to={feature.latest_odds ?? feature.capture_odds ?? 0}
                      className="cond num"
                      style={{ fontWeight: 700, fontSize: "2.25rem", lineHeight: 1, color: "var(--brand)" }}
                    />
                    <Drift from={feature.capture_odds} to={feature.latest_odds} />
                  </div>
                </div>
              </div>

              <div className="cluster" style={{ gap: "var(--s-3)", marginTop: "var(--s-6)" }}>
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
