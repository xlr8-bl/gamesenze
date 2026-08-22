"use client";

import type { GoalEvent, LiveMatch } from "@/lib/supabase";
import { ClubBadge } from "./sport";
import { competitionIdentity } from "@/lib/identity";
import { confidenceLabel } from "@/lib/analysis";

/** LIVE / HT flag with the pulsing dot. Colour carries the state, the word backs it. */
export function LiveFlag({ phase, minute }: { phase: "live" | "ht"; minute: number | null }) {
  if (phase === "ht") {
    return (
      <span className="live" style={{ color: "var(--caution)" }}>
        <span className="live-dot" style={{ background: "var(--caution)" }} />
        Half time
      </span>
    );
  }
  return (
    <span className="live">
      <span className="live-dot" />
      Live{minute !== null ? ` · ${minute}'` : ""}
    </span>
  );
}

/**
 * The scoreboard row: two crests, two names, the score in the middle at
 * broadcast scale. The score is the only thing here at that size, because on a
 * live match the score is the whole story.
 */
export function ScoreLine({
  m,
  size = "lg",
}: {
  m: LiveMatch;
  size?: "lg" | "sm";
}) {
  const big = size === "lg";
  return (
    <div
      className="row"
      style={{ gap: "var(--s-3)", flexWrap: "nowrap", alignItems: "center" }}
    >
      <Side name={m.home_team} align="right" size={size} />
      <div
        className="cond num"
        style={{
          fontWeight: 700,
          fontSize: big ? "clamp(2rem, 1.4rem + 2vw, 2.75rem)" : "1.5rem",
          lineHeight: 1,
          letterSpacing: "0.02em",
          whiteSpace: "nowrap",
          padding: big ? "0 var(--s-3)" : "0 var(--s-2)",
        }}
      >
        {m.home_score}
        <span style={{ color: "var(--ink-3)", margin: big ? "0 8px" : "0 4px" }}>-</span>
        {m.away_score}
      </div>
      <Side name={m.away_team} align="left" size={size} />
    </div>
  );
}

function Side({
  name,
  align,
  size,
}: {
  name: string | null;
  align: "left" | "right";
  size: "lg" | "sm";
}) {
  const big = size === "lg";
  return (
    <div
      className="cluster grow"
      style={{
        gap: "var(--s-2)",
        flexWrap: "nowrap",
        justifyContent: align === "right" ? "flex-end" : "flex-start",
        flexDirection: align === "right" ? "row" : "row-reverse",
        minWidth: 0,
      }}
    >
      <span
        className="cond"
        style={{
          fontWeight: 700,
          fontSize: big ? "clamp(0.95rem, 0.8rem + 0.5vw, 1.2rem)" : "0.9rem",
          textTransform: "uppercase",
          letterSpacing: "0.01em",
          textAlign: align,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {name}
      </span>
      <ClubBadge name={name} size={big ? 44 : 28} />
    </div>
  );
}

/** The goals so far, on the clock, each attributed to a side. */
export function GoalTimeline({ goals }: { goals: GoalEvent[] }) {
  if (!goals.length) {
    return (
      <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
        No goals yet.
      </div>
    );
  }
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
      {goals.map((g, i) => (
        <li
          key={i}
          className="cluster"
          style={{
            gap: "var(--s-3)",
            flexWrap: "nowrap",
            flexDirection: g.side === "away" ? "row-reverse" : "row",
            justifyContent: g.side === "away" ? "flex-start" : "flex-start",
          }}
        >
          <span
            className="cond num"
            style={{ color: "var(--brand)", fontWeight: 700, minWidth: 34, textAlign: "center" }}
          >
            {g.minute}&apos;
          </span>
          <span style={{ fontSize: "var(--t-small)" }}>
            {g.player ?? "Goal"}
            {g.kind === "pen_goal" && <span style={{ color: "var(--ink-3)" }}> (pen)</span>}
            {g.kind === "own_goal" && <span style={{ color: "var(--ink-3)" }}> (OG)</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A full live-match card for the hub. */
export function LiveCard({ m, index = 0 }: { m: LiveMatch; index?: number }) {
  const c = competitionIdentity(m.competition);
  return (
    <article
      className="panel rise"
      style={{ ["--i" as string]: index, overflow: "hidden" }}
    >
      <div aria-hidden style={{ height: 3, background: `linear-gradient(90deg, ${c.accent}, transparent 70%)` }} />
      <div style={{ padding: "var(--s-4)" }}>
        <div className="row" style={{ marginBottom: "var(--s-4)" }}>
          <span className="label" style={{ marginBottom: 0 }}>{c.name}</span>
          <LiveFlag phase={m.phase} minute={m.minute} />
        </div>

        <ScoreLine m={m} />

        {m.selection && (
          <div
            className="row"
            style={{
              marginTop: "var(--s-4)",
              paddingTop: "var(--s-3)",
              borderTop: "1px solid var(--line)",
              gap: "var(--s-3)",
            }}
          >
            <div>
              <div className="label">Our pick</div>
              <div className="cond" style={{ fontWeight: 700, textTransform: "uppercase" }}>
                {m.selection} <span style={{ color: "var(--ink-3)" }}>· {m.market}</span>
              </div>
            </div>
            <span className="chip chip-outline-brand">{confidenceLabel(m.confidence_tag)}</span>
          </div>
        )}

        {m.goals.length > 0 && (
          <div style={{ marginTop: "var(--s-4)" }}>
            <div className="label" style={{ marginBottom: 6 }}>Goals</div>
            <GoalTimeline goals={m.goals} />
          </div>
        )}
      </div>
    </article>
  );
}
