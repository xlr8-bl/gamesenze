"use client";

import { useEffect, useState } from "react";
import { fetchBoard, isConfigured, type Pick } from "@/lib/supabase";

/**
 * A live reading of the board, on the home page.
 *
 * It renders nothing at all until it knows the answer. A strip that flashes
 * "0 picks" for a moment and then corrects itself has told the reader
 * something false, and this is the one page where the first impression is the
 * whole point.
 */
export default function TodayStrip() {
  const [picks, setPicks] = useState<Pick[] | null>(null);

  useEffect(() => {
    if (!isConfigured) return;
    let live = true;
    fetchBoard()
      .then((rows) => live && setPicks(rows))
      .catch(() => live && setPicks([]));
    return () => {
      live = false;
    };
  }, []);

  if (picks === null) return null;

  // The same filter the board applies. v_published_picks carries settled picks
  // too, and counting those here would advertise a board that is not there.
  const open = picks
    .filter((p) => new Date(p.kickoff_at).getTime() > Date.now())
    .sort((a, b) => a.kickoff_at.localeCompare(b.kickoff_at));
  const next = open[0];

  return (
    <section className="panel enter stack-s" aria-label="Live board summary">
      <div>
        <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
          On the board now
        </div>
        <div className="num num-xl">{open.length}</div>
        <div style={{ color: "var(--ink-3)", fontSize: "var(--t-micro)" }}>
          {open.length === 1 ? "pick still open" : "picks still open"}
        </div>
      </div>

      <div style={{ borderTop: "1px solid var(--line)", paddingTop: "var(--s-3)" }}>
        <div style={{ color: "var(--ink-3)", fontSize: "var(--t-small)" }}>
          Next kickoff
        </div>
        {next ? (
          <div style={{ marginTop: 2 }}>
            <div>
              {next.home_team} v {next.away_team}
            </div>
            <div className="num" style={{ color: "var(--ink-2)", fontSize: "var(--t-small)" }}>
              {new Date(next.kickoff_at).toISOString().slice(0, 10)}{" "}
              {new Date(next.kickoff_at).toISOString().slice(11, 16)} UTC
            </div>
          </div>
        ) : (
          <p className="p-full" style={{ color: "var(--ink-2)", marginTop: 2 }}>
            Nothing open. A quiet board is a normal day.
          </p>
        )}
      </div>
    </section>
  );
}
